/**
 * The Asset service's public routes: the two halves of an upload (design doc 04 §3).
 *
 * `requestUploadUrl` reserves an asset and returns a presigned PUT; the file goes
 * straight to object storage (`lib/upload/xhrPut.ts`); `confirmUpload` then asks
 * Asset to check what arrived. Types are generated from Asset's OpenAPI document
 * (register D23): `npm run generate:api` regenerates `src/types/asset.ts`.
 *
 * Like `messaging.ts`, each call throws a `ProblemError` rather than returning
 * `openapi-fetch`'s two-shaped result. An aborted request rejects with the
 * `AbortError` the browser raises, and the upload runner treats it as a cancel.
 */

import createClient from 'openapi-fetch'

import { problemFromBody } from './client'
import { ASSET_URL } from '../config'
import type { components, paths } from '../../types/asset'

export type UploadUrl = components['schemas']['UploadUrlResponse']
export type Asset = components['schemas']['AssetResponse']

const client = createClient<paths>({ baseUrl: ASSET_URL })

export async function requestUploadUrl(
  accessToken: string,
  body: { fileName: string; contentType: string; sizeBytes: number },
  signal?: AbortSignal,
): Promise<UploadUrl> {
  const { data, error, response } = await client.POST('/api/v1/assets/upload-url', {
    headers: { Authorization: `Bearer ${accessToken}` },
    body: { ...body, purpose: 'attachment' },
    signal,
  })
  if (error !== undefined) throw problemFromBody(response.status, error)
  return data
}

/**
 * Ask Asset to check the upload. Idempotent, so a retry is harmless; the answer
 * is `ready` or `failed` with the reason in `failureReason`.
 */
export async function confirmUpload(
  accessToken: string,
  assetId: string,
  signal?: AbortSignal,
): Promise<Asset> {
  const { data, error, response } = await client.POST('/api/v1/assets/{asset_id}/confirm', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { asset_id: assetId } },
    signal,
  })
  if (error !== undefined) throw problemFromBody(response.status, error)
  return data
}
