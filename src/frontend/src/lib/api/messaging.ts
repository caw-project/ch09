/**
 * The Messaging service's REST surface (design doc 02 §3.1).
 *
 * The types are generated from the service's own OpenAPI document rather than
 * hand-written (register D23) — `npm run generate:api` regenerates
 * `src/types/messaging.ts` from `openapi/messaging.json`, which
 * `python -m messaging.openapi` produces without a running stack. A DTO copied
 * by hand is a DTO that drifts the first time a field is renamed.
 *
 * `openapi-fetch` returns `{ data, error }` rather than throwing. TanStack Query
 * wants a thrown error to mark a query failed, so each call converts once here
 * and nothing downstream sees the two-shaped result.
 */

import createClient from 'openapi-fetch'

import { problemFromBody, type ProblemError } from './client'
import { MESSAGING_URL } from '../config'
import type { components, paths } from '../../types/messaging'

export type Channel = components['schemas']['ChannelResponse']
export type ChannelPage = components['schemas']['ChannelListResponse']
export type ChannelKind = 'public' | 'private'
export type ChannelMember = components['schemas']['ChannelMemberResponse']
export type ChannelMemberPage = components['schemas']['ChannelMemberListResponse']
export type ChannelMemberRole = components['schemas']['AddChannelMemberRequest']['role']
export type Message = components['schemas']['MessageResponse']
export type MessagePage = components['schemas']['MessageListResponse']
export type Reaction = components['schemas']['ReactionSummary']
export type ThreadPage = components['schemas']['ThreadResponse']
export type Attachment = components['schemas']['Attachment']

const client = createClient<paths>({ baseUrl: MESSAGING_URL })

/**
 * `openapi-fetch` hands back the parsed error body, not the `Response`, so the
 * status comes from the caller. The builder itself lives in `client.ts`,
 * because a Socket.IO acknowledgement needs the same one and has no `Response`
 * either.
 */
function problem(status: number, body: unknown): ProblemError {
  return problemFromBody(status, body)
}

export async function listChannels(accessToken: string, cursor?: string): Promise<ChannelPage> {
  const { data, error, response } = await client.GET('/api/v1/channels', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { query: cursor ? { cursor } : {} },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function createChannel(
  accessToken: string,
  body: { name: string; topic?: string | null; kind: ChannelKind },
): Promise<Channel> {
  const { data, error, response } = await client.POST('/api/v1/channels', {
    headers: { Authorization: `Bearer ${accessToken}` },
    body,
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function getChannel(accessToken: string, channelId: string): Promise<Channel> {
  const { data, error, response } = await client.GET('/api/v1/channels/{channel_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId } },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/**
 * Rename a channel, or set its topic.
 *
 * `version` is the version the caller last read and is required: the server
 * refuses the write with a 409 if the row has moved on since. Sending an absent
 * `topic` leaves the topic alone; sending `null` clears it.
 */
export async function updateChannel(
  accessToken: string,
  channelId: string,
  body: { version: number; name?: string; topic?: string | null },
): Promise<Channel> {
  const { data, error, response } = await client.PATCH('/api/v1/channels/{channel_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId } },
    body,
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/** Archive a channel. One-way — nothing in this API brings it back. */
export async function archiveChannel(accessToken: string, channelId: string): Promise<Channel> {
  const { data, error, response } = await client.DELETE('/api/v1/channels/{channel_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId } },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function listChannelMembers(
  accessToken: string,
  channelId: string,
  cursor?: string,
): Promise<ChannelMemberPage> {
  const { data, error, response } = await client.GET('/api/v1/channels/{channel_id}/members', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId }, query: cursor ? { cursor } : {} },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/**
 * `role` is sent explicitly rather than left to the server's default. The
 * generated type treats a property with a `default` as always present, and
 * spelling it out here is cheaper than arguing with the generator — the value
 * is the same one the server would have picked.
 */
export async function addChannelMember(
  accessToken: string,
  channelId: string,
  body: { userId: string; role?: ChannelMemberRole },
): Promise<ChannelMember> {
  const { data, error, response } = await client.POST('/api/v1/channels/{channel_id}/members', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId } },
    body: { role: 'member', ...body },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function removeChannelMember(
  accessToken: string,
  channelId: string,
  userId: string,
): Promise<void> {
  const { error, response } = await client.DELETE(
    '/api/v1/channels/{channel_id}/members/{user_id}',
    {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { path: { channel_id: channelId, user_id: userId } },
    },
  )
  if (error !== undefined) throw problem(response.status, error)
}

/**
 * A page of history, newest first.
 *
 * Newest-first is the wire order, matching the index the query walks. The SPA
 * reverses once on the way to the DOM, in `useMessages`'s `select` — not here,
 * because a second flip somewhere else is how a list ends up in the right order
 * by accident and the wrong order after the next change.
 */
export async function listMessages(
  accessToken: string,
  channelId: string,
  cursor?: string,
): Promise<MessagePage> {
  const { data, error, response } = await client.GET('/api/v1/channels/{channel_id}/messages', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId }, query: cursor ? { cursor } : {} },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/**
 * Messages matching every word of `q`, newest first, in the channels the token's
 * workspace lets the caller see. A short page is not the last page — only a null
 * `nextCursor` is — because hydration can drop a hit whose row has gone.
 */
export async function searchMessages(
  accessToken: string,
  q: string,
  cursor?: string,
): Promise<MessagePage> {
  const { data, error, response } = await client.GET('/api/v1/search/messages', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { query: cursor ? { q, cursor } : { q } },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function sendMessage(
  accessToken: string,
  channelId: string,
  body: string,
): Promise<Message> {
  const { data, error, response } = await client.POST('/api/v1/channels/{channel_id}/messages', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId } },
    body: { body },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function getMessage(accessToken: string, messageId: string): Promise<Message> {
  const { data, error, response } = await client.GET('/api/v1/messages/{message_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { message_id: messageId } },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/**
 * A thread: its root, and a page of its replies, newest first.
 *
 * The root rides on every page — the panel needs it even when it is not in the
 * channel's loaded history — so a thread is one request and one loading state.
 * A reply's id is a 404 here ("No such thread."), and so is an id the caller
 * cannot see ("No such channel.").
 */
export async function getThread(
  accessToken: string,
  messageId: string,
  cursor?: string,
): Promise<ThreadPage> {
  const { data, error, response } = await client.GET('/api/v1/messages/{message_id}/thread', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { message_id: messageId }, query: cursor ? { cursor } : {} },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/**
 * Rewrite a message.
 *
 * `version` is a precondition, not a field being assigned — the server refuses
 * with a 409 if the row moved on since the caller read it. Both fields are
 * required: there is only one editable field on a message, so there is no
 * "leave this one alone" case to express.
 */
export async function editMessage(
  accessToken: string,
  messageId: string,
  body: { body: string; version: number },
): Promise<Message> {
  const { data, error, response } = await client.PATCH('/api/v1/messages/{message_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { message_id: messageId } },
    body,
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/**
 * Delete a message, and get the tombstone back.
 *
 * Deliberately not a 204. The row stays in the history with an empty body and
 * `deletedAt` set, and the client has to draw it — so the server returns what
 * to draw rather than making the client refetch a page it already holds.
 */
export async function deleteMessage(accessToken: string, messageId: string): Promise<Message> {
  const { data, error, response } = await client.DELETE('/api/v1/messages/{message_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { message_id: messageId } },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/**
 * React to a message, and get the message back with its new counts.
 *
 * Idempotent: reacting again with the same emoji leaves one reaction and still
 * answers 200. The whole message comes back rather than the reactions alone, so
 * the caller writes it through `upsertMessage` like any other change instead of
 * keeping a second cache keyed by message.
 *
 * `emoji` is a shortcode from the server's allowlist — `thumbsup`, never `👍`.
 * An unknown one is a 400 with the reason under `errors.emoji`.
 */
export async function addReaction(
  accessToken: string,
  messageId: string,
  emoji: string,
): Promise<Message> {
  const { data, error, response } = await client.POST('/api/v1/messages/{message_id}/reactions', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { message_id: messageId } },
    body: { emoji },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/**
 * A short-lived URL for one file on a message.
 *
 * Messaging mints it, and only for someone who can see the message: Asset has no
 * public download route, so this is the one way to a file's bytes (register D43).
 * The URL lasts 15 minutes; `useAttachmentUrl` decides when to ask for another.
 */
export async function getAttachmentUrl(
  accessToken: string,
  messageId: string,
  assetId: string,
): Promise<{ url: string; expiresAt: string }> {
  const { data, error, response } = await client.GET(
    '/api/v1/messages/{message_id}/attachments/{asset_id}/download-url',
    {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { path: { message_id: messageId, asset_id: assetId } },
    },
  )
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/** Take a reaction back. Removing one that is not there is a 200, not an error. */
export async function removeReaction(
  accessToken: string,
  messageId: string,
  emoji: string,
): Promise<Message> {
  const { data, error, response } = await client.DELETE(
    '/api/v1/messages/{message_id}/reactions/{emoji}',
    {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { path: { message_id: messageId, emoji } },
    },
  )
  if (error !== undefined) throw problem(response.status, error)
  return data
}
