# CollabHub — Asset Service

> File uploads, downloads, and metadata via presigned object-storage URLs.
> Read [Platform Conventions](./00-platform-conventions.md) first.

**Status:** Draft · **Runtime:** Python 3.12 / FastAPI (Uvicorn)
**Owns:** asset metadata, presigned URL issuance, bucket layout
**Depends on:** PostgreSQL (own DB), Garage (S3-compatible object storage), Redis Streams (R3)

---

## 1. Purpose & Responsibilities

Handles all binary assets — images, fonts, exports, avatars, attachments. The defining design
choice: **large blobs never transit the service**. Clients upload and download **directly to
Garage using presigned URLs**; the service only issues URLs and tracks metadata.

**Owns:** asset metadata (owner, type, size, status), presigned URL generation, bucket/key
layout, post-upload confirmation, enqueuing processing jobs.
**Produces:** thumbnail/optimisation jobs to `jobs:thumbnail` (R3), consumed by the Worker.
**Does NOT own:** actual image processing (Worker does it), referencing logic (Messaging/Canvas
store asset IDs and decide what an asset belongs to).

---

## 2. Runtime & Dependencies
- FastAPI REST only (no Socket.IO).
- S3-compatible client (`boto3` pointed at Garage) **behind an `ObjectStore` protocol/ABC**
  so Garage ↔ Azure Blob is a config/implementation swap, not a code change (Conventions §8).
  Use no Garage-specific APIs — only the S3 subset Garage implements.
- SQLAlchemy 2.0 (async) + asyncpg; Alembic migrations.
- `redis-py` (`redis.asyncio`) for R3.

---

## 3. Public Interface (REST `/api/v1`)

The upload is a three-step handshake so the blob goes client → Garage directly.

| Method | Path | Auth | Purpose | Built |
|--------|------|------|---------|-------|
| POST | `/assets/upload-url` | member | Reserve an asset; return presigned **PUT** URL + asset id. | ✅ 201 |
| POST | `/assets/{id}/confirm` | owner | HEAD the object, mark the asset `ready` or `failed`. | ✅ 200 |
| GET | `/assets/{id}` | viewer | Metadata (type, size, status, variants). | not built |
| GET | `/assets/{id}/download-url` | viewer | Presigned **GET** URL (time-limited). | **not built, and not planned** — see below |
| GET | `/assets/{id}/thumbnail-url?size=` | viewer | Presigned GET for a generated variant. | not built |
| DELETE | `/assets/{id}` | owner — **fail-closed** | Soft-delete metadata; schedule blob deletion via retention job. | not built (register D16) |

**There is no public download route (register D43).** "Viewer" cannot mean anything Asset can
check: an attachment is visible to whoever can see the *message* it is on, and that is
Messaging's to decide. So Asset never mints a read URL for a user. A client asks Messaging
(`GET /messages/{messageId}/attachments/{assetId}/download-url`, doc 02 §3.1.4), which checks
channel visibility and calls Asset's internal `download-url` below. `GET /assets/{id}`
returns nothing a message does not already carry, and arrives with the first feature that
needs it.

`upload-url` answers 400 with the rule's message under `errors.<field>` (`fileName`,
`contentType`, `sizeBytes` or `purpose`). `confirm` is **idempotent**: an asset that is no
longer `pending` is returned as it is. An asset that is another user's or another workspace's
is `404 "No such asset."`, worded as one that does not exist. A Garage that cannot be reached
is 503 and leaves the status alone.

`DELETE /assets/{id}` is in the **fail-closed** denylist set (Conventions §5.2, register D1):
it takes `require_user_sensitive` and returns 503 rather than proceed on a token whose
revocation status cannot be checked. It is the only endpoint in this service that does —
deletion is destructive and hard to undo, whereas refusing a read whenever R1 blinks would be
an outage for nothing.

**Internal** (`/api/v1/internal/`, service token only — Conventions §5.5; never reachable
from the public ingress, and never carrying `require_user`). **The workspace is in the body**,
put there by the caller from its own user's `wsp` claim, because a service token carries none.

| Method | Path | Scope | Purpose |
|--------|------|-------|---------|
| POST | `/internal/assets/claim` | `assets:claim` | **Messaging.** Put assets on a message: `{workspaceId, userId, messageId, assetIds[1..10]}` → `{items: [{assetId, fileName, contentType, sizeBytes}]}` in request order. **All or none:** if any asset cannot be claimed the answer is `409` with `errors` keyed by asset id, each one reason — `not-found` (another workspace's asset reads as this), `not-yours`, `not-ready`, `already-attached` — and nothing is claimed. Claiming for the message that already holds an asset is fine, which makes a retry idempotent. |
| POST | `/internal/assets/{id}/download-url` | `assets:download` | **Messaging.** `{workspaceId, messageId}` → `{url, expiresAt}`. 404 unless the asset is `ready` and claimed by exactly that message in that workspace. |
| POST | `/internal/assets/{id}/variants` | `assets:write-variants` | The Worker reports generated variants. 🟢 Register D14 — see the [ADR](../adr/260727-service-tokens-for-internal-calls.md). Not built. |
| POST | `/internal/assets/sweep` | `assets:retention` | Delete `pending` assets past their TTL and soft-deleted blobs. The Worker calls this; it deletes nothing itself (register D25). Not built. |

`claim` locks the rows `FOR UPDATE` in id order, judges every one, then writes — so two
sends racing for one asset serialize (the loser reads `already-attached`) and the same
assets in a different order cannot deadlock.

**Every asset is scoped to the workspace in the token's `wsp` claim.** `assets.workspace_id`
comes from the claim, never from the request — Conventions §5.4.

`POST /assets/upload-url`
```json
// request
{ "fileName": "logo.png", "contentType": "image/png", "sizeBytes": 482113, "purpose": "attachment" }
// response
{
  "assetId": "uuid",
  "uploadUrl": "https://objects/collabhub-uploads/...&X-Amz-Signature=...",
  "method": "PUT",
  "headers": { "Content-Type": "image/png" },
  "expiresAt": "2026-06-03T10:20:00Z"
}
```

Flow (matches the architecture sequence): client requests URL → uploads bytes straight to
Garage → calls `confirm` → service verifies the object and writes the outcome. Until
confirmed, the asset is `status = 'pending'` and not downloadable. **`confirm` enqueues no
`jobs:thumbnail` yet** — thumbnails are not built; §4.2 and §5 describe where they will go.

`confirm` decides `ready` or `failed` from what the store holds: no object is `failed` ("The
upload did not arrive."), a size other than the one declared is `failed`, and a stored size
over `ASSET_MAX_UPLOAD_BYTES` is `failed` even when declared honestly. Only an object that
arrived at exactly the declared size, within the limit, is `ready`.

**Allowed types** are PNG, JPEG, GIF, WebP and PDF, compared whole (`image/png; x=1` is not
`image/png`), up to 50 MiB, with a file name of 1–255 characters. **SVG is not allowed**: it
runs script when opened. The list is a constant in `asset/rules.py`, not a setting, because
it is the entire mitigation for the missing virus scan (D15).

---

## 4. Data Model (PostgreSQL)

```sql
CREATE TABLE assets (
    id            uuid PRIMARY KEY,
    workspace_id  uuid NOT NULL,
    owner_id      uuid NOT NULL,
    file_name     text NOT NULL,
    content_type  text NOT NULL,
    size_bytes    bigint NOT NULL,
    purpose       text NOT NULL,            -- 'attachment' is the only one accepted so far
    bucket        text NOT NULL,
    object_key    text NOT NULL,            -- {workspaceId}/{purpose}/{assetId}: no file name
    status        text NOT NULL DEFAULT 'pending',  -- pending | ready | failed
    failure_reason text NULL,               -- why `failed`, in words for the person
    checksum      text NULL,                -- ETag / sha256 after confirm (not yet written)
    message_id    uuid NULL,                -- Messaging's; the claim — set once, no FK
    created_at    timestamptz NOT NULL DEFAULT now(),
    confirmed_at  timestamptz NULL,
    claimed_at    timestamptz NULL,
    deleted_at    timestamptz NULL,
    UNIQUE (bucket, object_key)
);

-- Generated variants (thumbnails, optimised renditions) produced by the Worker.
CREATE TABLE asset_variants (
    id            uuid PRIMARY KEY,
    asset_id      uuid NOT NULL REFERENCES assets(id),
    kind          text NOT NULL,            -- thumb-128 | thumb-512 | webp | ...
    object_key    text NOT NULL,
    size_bytes    bigint NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (asset_id, kind)
);
```

`asset_variants` is not built. `workspace_id`, `owner_id` and `message_id` carry no foreign
keys: they name rows in Auth's and Messaging's databases (Conventions §2). `message_id` is
the claim: a download URL is only ever minted for the message that holds it.

### 4.1 Object storage layout
- Bucket `collabhub-assets` (one bucket; per-purpose buckets are register D13, still open).
  Object key **`{workspaceId}/{purpose}/{assetId}`** — *no file name*, so nothing a user
  chose reaches a key; the name is metadata and travels in `Content-Disposition`. Variants
  under `{...}/{assetId}/variants/{kind}` when built.
- Presigned PUT/GET expiry short (900 s). **The `Content-Type` is part of the PUT's
  signature**, so a URL issued for `image/png` refuses `text/plain`. A GET is signed with
  `response-content-disposition`: images `inline`, PDFs `attachment`, the name as an RFC 5987
  `filename*`.
- **Two endpoints.** A presigned URL's host is part of its signature, so URLs are signed for
  `OBJECT_STORE_PUBLIC_ENDPOINT`, the host a *browser* reaches, while Asset's own HEAD goes
  to `OBJECT_STORE_ENDPOINT`. Compose uses `http://localhost:3900`, the test stack
  `http://localhost:3910`, and k3d `s3.<host>` on the instance's own port, set by
  `scripts/deploy.sh` from `APP_ORIGIN`.
- **CORS.** The browser PUTs and GETs across origins, so the bucket's CORS rules allow the
  app's origin — and only it — for `PUT GET HEAD` with `content-type`, exposing `ETag`. The
  bootstrap (`charts/collabhub-deps/files/garage-bootstrap.py`) sets them through Garage's
  admin API from `GARAGE_CORS_ORIGINS`. Garage matches `AllowedHeader` against the
  browser's lower-case header names as written, so it is `content-type`.
- **Nothing sweeps** unsent `pending` assets, or the blobs of a deleted message (register
  D16, still open).

### 4.2 Redis usage
- **R3:** `jobs:thumbnail` — `{ assetId, objectKey, variants: ["thumb-128","thumb-512"] }`
  enqueued on confirm. Worker stores variants back in Garage and inserts `asset_variants` rows
  by calling back via the internal endpoint (Conventions §5.5).

---

## 5. Internal Design — Upload & Process
1. `POST /assets/upload-url`: insert `assets` row (`pending`), generate presigned PUT
   (via `boto3.generate_presigned_url`), return.
2. Client `PUT`s bytes directly to Garage.
3. `POST /assets/{id}/confirm`: HEAD the object to confirm existence/size/ETag, set
   `status='ready'`, `confirmed_at`, `checksum`.
4. `XADD jobs:thumbnail` with the variants to generate. *(Not built: `confirm` enqueues
   nothing, and steps 4–5 wait for the thumbnail slice.)*
5. Worker consumes, generates variants (Pillow), stores them in Garage, records
   `asset_variants`.

Orphan cleanup: `pending` assets older than a TTL (no confirm) are swept by a retention job
(Worker) which deletes both the row and any stray object.

---

## 6. Configuration
Common vars (Conventions §8). Plus:

| Var | Notes |
|-----|-------|
| `OBJECT_STORE_ENDPOINT` | Garage endpoint (or Azure Blob S3 endpoint) as Asset reaches it, for `HEAD`. |
| `OBJECT_STORE_PUBLIC_ENDPOINT` | The same store as a **browser** reaches it. URLs are signed for this host. Required. |
| `OBJECT_STORE_ACCESS_KEY` / `_SECRET_KEY` | Secret. Garage's own key format (`GK` + 24 hex, 64 hex). |
| `OBJECT_STORE_BUCKET` | Default bucket. |
| `OBJECT_STORE_PRESIGN_TTL_SECONDS` | Default 900. |
| `ASSET_MAX_UPLOAD_BYTES` | Default 52 428 800 (50 MiB). |
| `REDIS_CACHE_URL` | R1, for the token denylist `require_user` reads (Conventions §5.2). Required. |
| `CORS_ALLOWED_ORIGINS` | Empty installs no CORS middleware. Compose sets the SPA's origin; behind the one ingress it is empty. |

There is no `ASSET_ALLOWED_CONTENT_TYPES`: the allow-list is a constant (§3), because widening
the only defence against an unscanned upload should be a code change someone reviews, not an
environment variable. To restore the setting, re-add it and intersect it with the constant.

## 7. Cross-Cutting
Auth, errors, health, observability per Conventions. Metrics: `assets_uploaded_total`,
`asset_bytes_total`, `presign_issued_total{kind}`.

## 8. Non-Functional & Limits
- Service never streams blob bodies (memory-flat regardless of file size).
- Max upload size; content-type allow-list; **no virus scan** (register D15, §9).
- Download URLs are short-lived and per-request, minted through Messaging (D43); no public buckets.
- Readiness covers Postgres and R3. **Object storage is not a readiness check**, as
  Elasticsearch is not in Messaging's: a Garage blip makes `confirm` answer 503 rather than
  taking Asset out of rotation, which would stop every other route too.

## 9. Open Decisions
- ~~**Worker → variants callback**~~ — 🟢 **Decided 2026-07-27 (register D14).** The Worker
  calls `POST /api/v1/internal/assets/{id}/variants`, authenticated with an Auth-issued
  service token scoped `assets:write-variants`. See Conventions §5.5 and the
  [ADR](../adr/260727-service-tokens-for-internal-calls.md).
- Whether avatars/exports use the same bucket or dedicated buckets (register D13, 🔴). One bucket
  today.
- ~~Virus/malware scanning of uploads before marking `ready`~~ — 🟢 **Decided 2026-10 (register
  D15): no scan.** The allow-list (PNG, JPEG, GIF, WebP, PDF; no SVG) is the mitigation.
  Adding a scan hook later means a new state between `pending` and `ready`.
- ~~Who authorizes a download~~ — 🟢 **Decided 2026-10 (register D43):** Messaging, for anyone who
  can see the message. See the [ADR](../adr/261002-attachment-downloads-follow-message-visibility.md).
- Direct Azure Blob SDK vs. S3-compat layer for the Azure phase (Conventions favours S3-compat).
