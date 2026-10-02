/**
 * Client-side chat state (register D24: Zustand for client state).
 *
 * The split this file exists to keep: **TanStack Query owns server state, this
 * owns client state.** No channel, message or membership lives here — those are
 * the server's and are cached by Query, where one fetch serves every component
 * and an invalidation refreshes all of them at once. What lives here is what
 * the server has no opinion about: which channel the user is looking at, and
 * what they have half-typed.
 *
 * Keeping a copy of the channel list here as well is the mistake this comment
 * is trying to prevent. Two copies of server state diverge, and the bug shows
 * up as a sidebar that is one action out of date.
 */

import { create } from 'zustand'

/**
 * Whether the live connection is up. A fact *about* a resource, which is client
 * state; the socket itself is the resource and lives in a React context.
 */
export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

interface ChatState {
  activeChannelId: string | null
  /** Per-channel composer text, so switching channels does not lose it. */
  drafts: Record<string, string>
  /**
   * Per-thread composer text, keyed by the root's id and apart from `drafts`, so
   * a half-typed reply can never be the channel's draft (R14) by construction.
   */
  threadDrafts: Record<string, string>
  connectionStatus: ConnectionStatus
  /**
   * The channel whose room the server has put this connection in — set when it
   * acknowledges the join, not when the join is sent. A connected socket is not
   * yet receiving a channel's broadcasts: the server enters the room only after
   * checking the channel is visible.
   */
  joinedChannelId: string | null
  /**
   * The channel being read right now — open, visible, focused and at the
   * bottom. A fact about the screen, shared between the list and the sidebar,
   * which the server has no opinion about; the sidebar hides that channel's
   * badge while it holds.
   */
  readingChannelId: string | null
  setActiveChannel: (channelId: string | null) => void
  setReadingChannel: (channelId: string | null) => void
  setDraft: (channelId: string, text: string) => void
  clearDraft: (channelId: string) => void
  setThreadDraft: (rootId: string, text: string) => void
  clearThreadDraft: (rootId: string) => void
  setConnectionStatus: (status: ConnectionStatus) => void
  setJoinedChannel: (channelId: string | null) => void
}

export const useChatStore = create<ChatState>((set) => ({
  activeChannelId: null,
  drafts: {},
  threadDrafts: {},
  connectionStatus: 'disconnected',
  joinedChannelId: null,
  readingChannelId: null,
  setActiveChannel: (channelId) => set({ activeChannelId: channelId }),
  setReadingChannel: (channelId) => set({ readingChannelId: channelId }),
  setConnectionStatus: (status) => set({ connectionStatus: status }),
  setJoinedChannel: (channelId) => set({ joinedChannelId: channelId }),
  setDraft: (channelId, text) =>
    set((state) => ({ drafts: { ...state.drafts, [channelId]: text } })),
  clearDraft: (channelId) =>
    set((state) => {
      const { [channelId]: _removed, ...rest } = state.drafts
      return { drafts: rest }
    }),
  setThreadDraft: (rootId, text) =>
    set((state) => ({ threadDrafts: { ...state.threadDrafts, [rootId]: text } })),
  clearThreadDraft: (rootId) =>
    set((state) => {
      const { [rootId]: _removed, ...rest } = state.threadDrafts
      return { threadDrafts: rest }
    }),
}))
