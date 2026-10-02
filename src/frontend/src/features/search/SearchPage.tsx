/**
 * The results page at `/search?q=…`.
 *
 * Results are newest first, as the server serves them; "Load more" follows the
 * cursor until it is null. A failed first fetch shows the problem with a Retry; a
 * failed later page keeps the list and the banner, and clicking Load more again is
 * the retry. A blank or missing `q` fetches nothing and says how to search.
 */

import { useSearchParams } from 'react-router-dom'

import { ProblemBanner } from '../../components/ProblemBanner'
import { useWorkspaceMembers } from '../channels/useWorkspaceMembers'
import { SearchResult } from './SearchResult'
import { useChannelNames } from './useChannelNames'
import { useSearch } from './useSearch'

interface Props {
  accessToken: string
  workspaceId: string | null
}

export function SearchPage({ accessToken, workspaceId }: Props) {
  const [params] = useSearchParams()
  const q = (params.get('q') ?? '').trim()

  const search = useSearch(accessToken, workspaceId, q)
  const results = search.data ?? []
  const channelName = useChannelNames(
    accessToken,
    workspaceId,
    results.map((message) => message.channelId),
  )
  const directory = useWorkspaceMembers(accessToken, workspaceId)

  if (q === '') {
    return (
      <p className="p-6 text-sm text-ink-muted">Type in the search box to find messages.</p>
    )
  }

  if (search.isPending) {
    return <p className="p-6 text-sm text-ink-muted">Searching…</p>
  }

  if (search.data === undefined) {
    return (
      <div className="flex flex-col items-start gap-3 p-6">
        <ProblemBanner error={search.error} />
        <button
          type="button"
          onClick={() => void search.refetch()}
          className="rounded bg-accent px-3 py-1 text-sm font-medium text-accent-ink"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 p-6">
      {results.length === 0 ? (
        <p role="status" data-testid="search-empty" className="text-sm text-ink-muted">
          No messages match "{q}".
        </p>
      ) : (
        <ul aria-label="Search results" className="flex flex-col">
          {results.map((message) => (
            <li key={message.id}>
              <SearchResult
                message={message}
                channelName={channelName(message.channelId)}
                authorName={directory.nameFor(message.authorId)}
              />
            </li>
          ))}
        </ul>
      )}

      <ProblemBanner error={search.error} />

      {search.hasNextPage && (
        <button
          type="button"
          data-testid="search-load-more"
          disabled={search.isFetchingNextPage}
          onClick={() => void search.fetchNextPage()}
          className="self-start rounded border border-border px-3 py-1 text-sm text-ink"
        >
          Load more
        </button>
      )}
    </div>
  )
}
