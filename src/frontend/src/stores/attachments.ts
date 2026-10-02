/**
 * The composer's chips — client state (register D24), keyed by channel so an
 * upload belongs to the draft it was started in (issue 4 R15).
 *
 * A chip is a file on its way to being attached: it is `uploading` until Asset
 * has confirmed it, then `ready` with an `assetId` (what a send names) or
 * `failed` with the reason. **Nothing server-shaped lives here** — a message, a
 * download URL, an uploaded asset's record are TanStack Query's or the server's;
 * this is what the browser alone knows.
 *
 * Two rules are easy to get wrong, and both are here:
 *
 * * **A late write to a chip that is gone is a no-op** (decision 37). Uploading
 *   runs outside React in three awaited steps, and a ✕ or a workspace switch can
 *   land between any two; the step that finishes later must not bring the chip
 *   back.
 * * **Restoring never drops anything** (decision 33). A refused send puts its
 *   chips back *in front of* what is attached now, even past ten — the composer
 *   refuses to send until some are removed, which is better than losing a file
 *   somebody chose.
 */

import { create } from 'zustand'

export interface Chip {
  /** Local to this browser tab; `assetId` is the server's. */
  localId: string
  fileName: string
  contentType: string
  sizeBytes: number
  status: 'uploading' | 'ready' | 'failed'
  /** The PUT's progress, 0 to 1. */
  progress: number
  /** Set when Asset has confirmed the upload; what a send names. */
  assetId: string | null
  /** Why it failed, in words for the person. */
  error: string | null
}

interface AttachmentState {
  chips: Record<string, Chip[]>
  add: (channelId: string, chip: Chip) => void
  update: (localId: string, patch: Partial<Chip>) => void
  remove: (channelId: string, localId: string) => void
  restore: (channelId: string, chips: Chip[]) => void
  clear: (channelId: string) => void
  reset: () => void
}

export const useAttachmentStore = create<AttachmentState>((set) => ({
  chips: {},

  add: (channelId, chip) =>
    set((state) => ({ chips: { ...state.chips, [channelId]: [...(state.chips[channelId] ?? []), chip] } })),

  update: (localId, patch) =>
    set((state) => {
      const channelId = Object.keys(state.chips).find((id) =>
        state.chips[id].some((chip) => chip.localId === localId),
      )
      // Gone: removed, cleared, or reset since the step that is writing began.
      if (channelId === undefined) return state
      return {
        chips: {
          ...state.chips,
          [channelId]: state.chips[channelId].map((chip) =>
            chip.localId === localId ? { ...chip, ...patch } : chip,
          ),
        },
      }
    }),

  remove: (channelId, localId) =>
    set((state) => ({
      chips: {
        ...state.chips,
        [channelId]: (state.chips[channelId] ?? []).filter((chip) => chip.localId !== localId),
      },
    })),

  restore: (channelId, chips) =>
    set((state) => ({
      chips: { ...state.chips, [channelId]: [...chips, ...(state.chips[channelId] ?? [])] },
    })),

  clear: (channelId) =>
    set((state) => {
      const { [channelId]: _cleared, ...rest } = state.chips
      return { chips: rest }
    }),

  reset: () => set({ chips: {} }),
}))
