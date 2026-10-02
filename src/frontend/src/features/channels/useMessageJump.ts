/**
 * Jumping to a message named in the URL (`/c/:channelId?message=<id>`): page
 * back through history until it is loaded, centre it, highlight it for two
 * seconds, and take the parameter off the URL.
 *
 * **Decide only while history is idle.** `nextJumpStep` answers `wait` whenever a
 * fetch is running, so the jump never looks at pages a refetch is about to
 * replace. Each page it asks for goes through the list's `loadOlder`, which never
 * cancels a refetch and fetches nothing while one is running.
 *
 * **`jumping` is true in the first render the parameter is present.** On a fresh
 * mount that is the state initialiser; on a list that is already mounted it is
 * the render-time adjustment below (React's "adjusting state when a prop
 * changes"), so the render that commits already holds reads and auto-scroll off —
 * a flag set in an effect would be one committed render late.
 *
 * **Who removes the parameter.** The hook, with `replace`, at each end: found,
 * the cap, a failed fetch. A parameter that disappears while the jump is still
 * seeking was removed by navigation, and abandons it; a different id restarts
 * it, so the latest target wins. Leaving the channel unmounts the list, and the
 * cleanups abandon whatever was pending.
 */

import { useEffect, useState, type RefObject } from 'react'
import { useSearchParams } from 'react-router-dom'

import type { Message } from '../../lib/api/messaging'
import { HIGHLIGHT_MS, JUMP_PARAM, nextJumpStep } from './jump'

/** What the jump needs to know about the channel's history. */
export interface JumpHistory {
  messages: readonly Message[]
  loadedPages: number
  hasNextPage: boolean
  isFetching: boolean
  isError: boolean
  isSuccess: boolean
  /** Fetch the next older page — only when there is one and history is idle now. */
  loadOlder: () => void
}

export interface Jump {
  /** Seeking or highlighting: reads and auto-scroll are held off. */
  jumping: boolean
  highlightedId: string | null
  /** The cap was reached (or history ran out) without finding the message. */
  tooFarBack: boolean
}

type Phase = 'idle' | 'seeking' | 'highlighting'

export function useMessageJump(
  history: JumpHistory,
  scroller: RefObject<HTMLElement | null>,
  onScrolled: () => void,
): Jump {
  const { messages, loadedPages, hasNextPage, isFetching, isError, isSuccess, loadOlder } = history
  const [params, setParams] = useSearchParams()
  const param = params.get(JUMP_PARAM)

  const [seenParam, setSeenParam] = useState(param)
  const [target, setTarget] = useState(param)
  const [phase, setPhase] = useState<Phase>(param === null ? 'idle' : 'seeking')
  const [highlightedId, setHighlightedId] = useState<string | null>(null)
  const [tooFarBack, setTooFarBack] = useState(false)

  if (param !== seenParam) {
    setSeenParam(param)
    if (param !== null) {
      setTarget(param)
      setPhase('seeking')
      setHighlightedId(null)
      setTooFarBack(false)
    } else if (phase === 'seeking') {
      setTarget(null)
      setPhase('idle')
    }
  }

  useEffect(() => {
    if (phase !== 'seeking' || target === null) return
    // Nothing to decide on until history has either arrived or failed.
    if (!isSuccess && !isError) return

    function removeParam() {
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous)
          next.delete(JUMP_PARAM)
          return next
        },
        { replace: true },
      )
    }

    const step = nextJumpStep({
      target,
      messages,
      loadedPages,
      hasNextPage,
      fetching: isFetching,
      failed: isError,
    })

    switch (step) {
      case 'wait':
        return
      case 'fetch':
        loadOlder()
        return
      case 'found': {
        const row = Array.from(
          scroller.current?.querySelectorAll<HTMLElement>('[data-message-id]') ?? [],
        ).find((element) => element.dataset.messageId === target)
        row?.scrollIntoView({ block: 'center' })
        onScrolled()
        setHighlightedId(target)
        setPhase('highlighting')
        removeParam()
        return
      }
      case 'give-up': {
        const element = scroller.current
        if (element) element.scrollTop = element.scrollHeight
        onScrolled()
        setTooFarBack(true)
        setPhase('idle')
        removeParam()
        return
      }
      case 'failed':
        setPhase('idle')
        removeParam()
        return
    }
  }, [
    phase,
    target,
    messages,
    loadedPages,
    hasNextPage,
    isFetching,
    isError,
    isSuccess,
    loadOlder,
    scroller,
    onScrolled,
    setParams,
  ])

  // The highlight lasts two seconds. A new target moves the phase off
  // `highlighting`, and the cleanup stops the old timer with it.
  useEffect(() => {
    if (phase !== 'highlighting') return
    const timer = setTimeout(() => {
      setHighlightedId(null)
      setPhase('idle')
    }, HIGHLIGHT_MS)
    return () => clearTimeout(timer)
  }, [phase, highlightedId])

  return { jumping: phase !== 'idle', highlightedId, tooFarBack }
}
