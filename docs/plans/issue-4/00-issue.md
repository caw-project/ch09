Issue: 4

# Issue 4 — File attachments

## Summary

Anyone who can post in a channel can attach files to a message — from a picker, by dropping
them on the composer, or by pasting a screenshot. Images show inline; PDFs show as a chip to
download. Files go straight from the browser to Garage and back, never through a service, and
who may download one follows who may see the message it is on.

## Services touched

**Asset, Messaging, the SPA, Auth's config, Compose, both charts and testkit.** Read
`docs/design/04-asset-service.md` §1–§6, `docs/design/02-messaging-service.md` §3.1.3–§3.1.4,
§3.2 and §6, `docs/design/06-frontend-spa.md` §6 and §8, and Conventions §5.2, §5.5 and §7.
The Worker and search are untouched.

## What exists already

- **Asset is a scaffold**: `asset/main.py` (health only), `asset/settings.py` (`object_store_*`,
  `asset_max_upload_bytes`, `asset_allowed_content_types`, no `redis_cache_url`). No routes,
  tables, Alembic, `ObjectStore` or boto3. The `collabhub_asset` database exists (`init.sql`).
- **Messaging ships the column ahead of the feature**: `messages.attachments uuid[]`
  (`0002_messages.py`), `MessageResponse.attachments: list[UUID]`, always `[]`;
  `SendMessageRequest` and `SendMessagePayload` take `body` only and ignore extra keys;
  `messaging_max_attachments = 10` is read by nothing. Messaging makes no service-token call today.
- **Shared**: `require_service(scope)`, `require_user_sensitive`, `JobQueue`; no `ObjectStore`.
  `contracts/indexing.py` is the template for a payload two services share.
- **Garage**: in Compose (`dxflrs/garage:v2.3.0`, no healthcheck, bootstrap is a manual README
  step, no CORS); in `charts/collabhub-deps` with an idempotent `garage-bootstrap` Job
  (`files/garage-bootstrap.py`, Python 3.12, stdlib only, grants the key `owner: False`). The
  test stack runs `asset` and `garage` but publishes neither. The Ingress allow-list says
  "Canvas and Asset have no public API yet".
- **SPA**: `MessageComposer.tsx` (draft in `useChatStore.drafts`, cleared before the ack,
  restored in a per-call `onError`), `useSendMessage` (`SEND_TIMEOUT_MS` 5000, optimistic
  `temp:` row, no retry), `MessageItem.tsx` renders no attachments. Only `openapi/messaging.json`
  is generated. No XHR or upload code anywhere.
- **Templates**: reactions (`c02dcd7`) for a new Messaging table, DTO field and SPA component;
  `contracts/indexing.py` for a shared payload.

## Requirements

1. **Upload handshake.** For purpose `attachment` only: `POST /api/v1/assets/upload-url`
   reserves a `pending` asset and returns a presigned PUT; the browser PUTs the bytes to Garage;
   `POST /api/v1/assets/{id}/confirm` HEADs the object and marks it `ready`, or `failed`.
2. **Limits.** At most 10 attachments per message; each 1 byte to 50 MB; content type one of
   `image/png`, `image/jpeg`, `image/gif`, `image/webp`, `application/pdf`; file name at most 255
   characters. The SPA checks before any upload starts and says which rule refused; the server
   checks again at `upload-url`, and at `confirm` the stored size must equal the declared size.
3. **Three ways in.** The paperclip picker, a drop on the composer, and paste. A paste whose
   clipboard has `text/plain` pastes the text and attaches nothing; otherwise every file in it
   is attached. A pasted image is named `Pasted image <yyyy-mm-dd hh.mm.ss>.png`, local time.
4. **All of a batch or none.** A pick, drop or paste that would take the message over 10 attaches
   none of it, and says so: "At most 10 files per message — 3 attached, 12 added."
5. **Chips.** Each file is a chip with its name, a progress bar while uploading, a remove ✕, and
   on failure the reason. Send is enabled only when every chip is `ready`.
6. **Send.** `send_message` (socket) and `POST /channels/{id}/messages` accept `attachmentIds`.
   The body may be empty when there is at least one attachment.
7. **Strict claim.** Before inserting, Messaging claims the assets from Asset with a service
   token. The whole send is refused unless every asset is `ready`, in the caller's workspace,
   uploaded by the caller and claimed by no other message. Asset unreachable → 503, no message.
8. **What a message carries.** `attachments: [{assetId, fileName, contentType, sizeBytes}]`, in
   the order attached, on REST, history and `message_received`. The sender sees it once.
9. **Rendering.** PNG, JPEG, GIF and WebP render inline, size-capped, opening full size in a new
   tab on click; PDF renders as a chip with name, size and a download link.
10. **Downloads go through Messaging.** `GET /api/v1/messages/{messageId}/attachments/{assetId}/download-url`
    returns a presigned GET for a caller who can see the channel; Messaging gets it from an Asset
    internal endpoint. 404 for a channel the caller can't see, a deleted message, or an asset not
    on that message. PDFs download with `Content-Disposition: attachment`.
11. **Fresh on click.** Opening or downloading always uses a URL that is not stale; a stale one
    is refetched first. An `<img>` that fails to load refetches once, then shows "couldn't load —
    retry".
12. **Tombstones and edits.** A deleted message shows `attachments: []`. An edit never changes
    attachments.
13. **A refused send restores its own draft.** Its text and its chips come back to its own
    channel's composer, even when a later send is in flight. Timeout wording becomes "The server
    did not confirm that message — it may still arrive."
14. **Errors stay in their channel.** A send error shown in one channel's composer is not shown
    in another's.
15. **Pending uploads belong to the channel's draft.** They keep uploading on a channel switch
    and are there on return. A reload or sign-out loses them; a workspace switch clears them.
16. **Garage is reachable from the browser.** URLs are signed against a public endpoint, not
    `garage:3900`; bucket CORS allows `APP_ORIGIN` for PUT and GET; a bootstrap creates layout,
    bucket, key and CORS on Compose, the test stack and k3d with no manual step. In Compose the
    public endpoint is Garage's published port; on k3d it is a Garage host on the Ingress, `s3.`
    before `APP_ORIGIN`'s host.

## Where the rules meet

- **Limits and batches (R2, R4):** the count includes chips already attached, failed ones too
  until removed. Removing one makes room.
- **Send and the claim (R5, R7):** Send is disabled until every chip is ready, but the server
  never trusts that — a `pending` asset is refused by the claim.
- **A timeout and the claim (R7, R13):** a send whose ack is lost may have succeeded. Its retry
  is refused as already attached, the draft is restored, and the original arrives by broadcast.
- **Claim then insert (R7):** Messaging chooses the message id, claims with it, then inserts. If
  the insert fails after the claim, those assets stay claimed to no message — accepted as rare;
  the claim is idempotent for the same `(assetId, messageId)`.
- **Delete and downloads (R10, R12):** a delete while an image is loading — the URL already
  issued still works; any new request 404s; the tombstone drops the image.
- **The response and the echo (R8):** the sender's client gets the message from its ack and from
  `message_received`, in either order; one row, the same attachments.
- **Restore and pending uploads (R13, R15):** restored chips land in the draft of the channel
  the send was for, not the channel on screen.

## Paths each rule holds on

| Path | What must be true |
|---|---|
| First load of a channel | attachments come with history; each URL is fetched as its message renders |
| Return to a cached channel | stale URLs are refetched before an `<img>` loads; pending uploads are still there |
| Switch channel mid-upload | the upload carries on; its chip is in the first channel's draft only |
| Switch channel with a send error showing | the error stays with the first channel |
| Reconnect after a dropped socket | history refetch brings attachments; uploads (HTTP) are unaffected |
| A second tab or device | sees the message and its attachments live, fetches its own URLs |
| Losing access to a private channel | download-url 404s at once; a URL already in the browser lives ≤15 minutes |
| Asset down while viewing | messages and chips render from stored metadata; images show the retry placeholder |
| Asset down while sending | 503, nothing sent, draft and chips restored |

## What this assumes — check before building on it

- **Garage v2.3.0 enforces a signed `Content-Type` on a presigned PUT** (boto3 puts it in
  `X-Amz-SignedHeaders`) and **honours `response-content-disposition`** on a presigned GET.
  Read from source, not yet seen against a running Garage.
- **Garage adds CORS headers only to successful responses**, so a failed PUT reaches the SPA as
  an opaque network error with no status. The chip can only say "Upload failed"; `confirm` is
  where the server says why.
- **CORS can't be set with the app key** (PutBucketCors needs Owner) — the bootstrap sets it with
  the admin API's `UpdateBucket` `corsRules`.
- **A presigned URL signs the host.** boto3 needs `region_name='garage'`, `s3v4`, path style,
  and a client whose endpoint is the browser-facing one; HEAD on confirm uses the internal one.
- **Expiry is checked when a request starts**, so a long PUT is not cut off at 15 minutes.
- **TanStack Query v5 runs a per-call `mutate(…, {onError})` only for the latest call** — why
  R13 fails today with two sends in flight. The composer is not keyed by channel
  (`ChannelView.tsx`), which is why R14 fails today.
- **Clipboard images arrive as a `File` named `image.png`** with no `text/plain` beside them;
  Excel and Word put both on the clipboard.
- **testcontainers-python has no Garage module**; the fixture is a plain container plus the
  bootstrap's admin calls.

## Timing

Upload and confirm:
```
t=0    pick → client checks R2/R4 → POST upload-url → PUT starts, progress shown
t=n    PUT done → POST confirm → Asset HEADs → ready (or failed: size ≠ declared, > limit)
t=n+1  every chip ready → Send enabled
```
Download URLs (TTL 900 s; stale at 780 s):
```
t=0      Grace opens #general → URL for image A fetched; A renders
t=780s   URL stale; nothing refetches; A stays on screen
t=1000s  Grace clicks A → fresh URL fetched first, then opened
t=1000s  Grace leaves and returns → A remounts, stale → refetched before <img> loads
```
A lost ack:
```
t=0     Ada sends M with A1 → claim succeeds, M saved; the ack is lost
t=5s    timeout → draft and chip restored: "…it may still arrive"
t=5s+   message_received M reaches Ada → M shown once
t=8s    Ada sends again → refused, A1 already attached; draft stays
```

## Decided already

1. Scope is R1–R16; *Not in this issue* stays out.
2. **D15 is closed: no virus scan.** The allow-list (no SVG) is the mitigation.
3. Messaging decides who may download, as R10; Asset's public routes are `upload-url` and
   `confirm` only. Messaging gets its first service-token client, with its token reused until
   near expiry, never fetched per send.
4. The object key is `{workspaceId}/attachment/{assetId}` — no file name in it.
5. Messaging stores a snapshot of each attachment's metadata, from the claim's response, in a
   new table keyed by message and position; the unused `messages.attachments uuid[]` column is
   dropped in the same migration.
6. D13 (one bucket) and D16 (retention) stay 🔴: one bucket, `collabhub-assets`; nothing sweeps
   unsent `pending` assets or a deleted message's blobs.
7. Issues 2 and 3 are independent of this one and may land before or after it. Shared files:
   `MessageItem`, `MessageComposer`, `useMessages`, `useChannelSocket`, `stores/chat.ts`,
   `schemas.py`, `realtime_writes.py`, `routers/messages.py`, the generated OpenAPI types,
   `factories.ts`, `chat_page.py`. The migration takes the next free number when built.

Left to the plan, on purpose: table and column names in Asset and Messaging, scope and setting
names, status codes, the inline size cap, where the XHR upload helper lives.

## Tests

- **Unit, with no Garage and no fake of one**: limits, confirm's size check, the claim decision,
  the object key, Content-Disposition, paste naming, the batch count — as pure functions.
- **Integration against real Garage**: a `garage_server` fixture in testkit, in
  `CONTAINER_FIXTURES`, with its image pinned in `testkit/images.py`. It proves presign, the
  signed Content-Type, HEAD on confirm, Content-Disposition and the CORS preflight.
- **The Messaging↔Asset seam**: Asset's internal request and response models live in
  `contracts`. Messaging's integration tests stub Asset's internal HTTP with those models; Asset's
  own integration tests prove the real endpoints honour them.
- **Vitest**: MSW stubs for Asset typed from a new `openapi/asset.json`, and the Garage PUT
  stubbed in MSW. `test/api.ts`'s `record()` parses every body as JSON and needs a non-JSON path.
- **One BDD journey**, everything real: Ada attaches a PNG and a PDF and sends; Grace, already
  in the channel, sees the image inline and the PDF as a chip, and the download returns the same
  bytes. The harness probes Asset's readiness and truncates Asset's tables too.

## Record in this slice

- Doc 04: the routes built, the internal claim and download-url, the key layout, the public
  endpoint, CORS, that `viewer` means "can see the message". Doc 02: `attachmentIds`, the DTO,
  the download route, tombstone redaction. Doc 06 §6: the composer, paste, freshness.
- Register: D15 🟢 (no scan); new **D43** — attachment downloads follow message visibility,
  minted through Messaging — 🟢 once built; notes on D13, D16 (unsent and deleted blobs now
  accumulate) and D34 (the Garage fixture landed).
- An ADR for D43 and the strict claim.
- `.env.example`, Compose, `docker-compose.test.yml`, both charts: the public endpoint, Messaging's
  service client, the bootstrap with CORS, `/api/v1/assets` on the Ingress allow-list.

## Not in this issue

Thumbnails, `jobs:thumbnail` and the Worker · search over file names · `DELETE /assets/{id}` and
the retention sweep · avatars, exports, canvas images, fonts · a virus scan · adding or removing
attachments by edit · attachments on thread replies · deploying the lab.

## Acceptance — first real run on Compose

With Ada and Grace in two browsers:
- Ada pastes a screenshot and picks a PDF, sends; Grace sees both live, Ada sees the message once.
- Ada drops 11 files; none attach, and she reads why.
- Ada starts a large upload, switches channel and back: the chip is still there, still uploading.
- Grace is removed from a private channel; her download link for a file there now 404s.
- Ada deletes the message: both see the tombstone, no attachments.
- On k3d: one upload and one download through the Ingress.

## References

- `docs/design/04-asset-service.md`, `02-messaging-service.md`, `06-frontend-spa.md` §6
- Conventions §5.2, §5.5, §7 · register D13, D14, D15, D16, D25, D34
- Commit `c02dcd7` (reactions) · `contracts/indexing.py` · `charts/collabhub-deps/files/garage-bootstrap.py`
