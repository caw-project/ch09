/**
 * Server-shaped values for tests, typed from the generated schema (D23).
 *
 * Every field is filled, so a factory built value is exactly what the API
 * could send, and a test names only the fields its behaviour depends on.
 * Ids are fresh per call so two factory values never collide by accident.
 */

import type { Attachment, Channel, Message, MessagePage, ThreadPage } from '../lib/api/messaging'
import type { WorkspaceMember } from '../lib/auth/api'
import type { Session } from '../lib/auth/session'
import type { Chip } from '../stores/attachments'

const AT = '2026-09-15T09:00:00Z'

export const WORKSPACE_ID = '0199a000-0000-7000-8000-0000000000f0'

function id(): string {
  return crypto.randomUUID()
}

/**
 * A UUIDv7-shaped message id that sorts by `n`.
 *
 * `aMessage()` ids are UUIDv4, so their string order means nothing; the read
 * rules compare ids as strings (UUIDv7 is time order), so a test that needs
 * "older" and "newer" builds its ids with this. `messageIdAt(2) > messageIdAt(1)`.
 */
export function messageIdAt(n: number): string {
  return `0199a000-0000-7000-8000-${n.toString(16).padStart(12, '0')}`
}

export function aChannel(overrides: Partial<Channel> = {}): Channel {
  return {
    id: id(),
    name: 'general',
    topic: null,
    kind: 'public',
    createdBy: id(),
    createdAt: AT,
    updatedAt: AT,
    archivedAt: null,
    version: 0,
    myRole: null,
    lastReadId: null,
    unreadCount: 0,
    ...overrides,
  }
}

export function aMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: id(),
    channelId: id(),
    authorId: id(),
    threadRootId: null,
    body: 'hello',
    attachments: [],
    reactions: [],
    createdAt: AT,
    editedAt: null,
    deletedAt: null,
    version: 0,
    replyCount: 0,
    lastReplyAt: null,
    ...overrides,
  }
}

/** What a message carries for one file (R8), as the server sends it. */
export function anAttachment(overrides: Partial<Attachment> = {}): Attachment {
  return {
    assetId: id(),
    fileName: 'diagram.png',
    contentType: 'image/png',
    sizeBytes: 1234,
    ...overrides,
  }
}

/** A chip in the composer, already uploaded unless a test says otherwise. */
export function aChip(overrides: Partial<Chip> = {}): Chip {
  const localId = overrides.localId ?? id()
  return {
    localId,
    fileName: 'diagram.png',
    contentType: 'image/png',
    sizeBytes: 1234,
    status: 'ready',
    progress: 1,
    assetId: `asset-${localId}`,
    error: null,
    ...overrides,
  }
}

/** One page of history, newest first — the wire order. */
export function aMessagePage(items: Message[], nextCursor: string | null = null): MessagePage {
  return { items, nextCursor }
}

/**
 * One page of a thread, as `GET /messages/{id}/thread` serves it: the root on
 * every page, then replies newest first.
 */
export function aThreadPage(
  root: Message,
  items: Message[],
  nextCursor: string | null = null,
): ThreadPage {
  return { root, items, nextCursor }
}

export function aWorkspaceMember(
  overrides: { id?: string; displayName?: string; role?: string } = {},
): WorkspaceMember {
  const userId = overrides.id ?? id()
  const displayName = overrides.displayName ?? 'Ada Lovelace'
  return {
    user: {
      id: userId,
      email: `${displayName.split(' ')[0].toLowerCase()}@collabhub.dev`,
      displayName,
      avatarAsset: null,
    },
    role: overrides.role ?? 'member',
    joinedAt: AT,
  }
}

export function aSession(overrides: Partial<Session> = {}): Session {
  return {
    accessToken: 'test-token',
    profile: {
      id: id(),
      email: 'ada@collabhub.dev',
      displayName: 'Ada Lovelace',
      avatarAsset: null,
    },
    workspaces: [{ id: WORKSPACE_ID, name: 'CollabHub', role: 'owner' }],
    activeWorkspaceId: WORKSPACE_ID,
    ...overrides,
  }
}
