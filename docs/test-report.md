# Test report

Written by `scripts/test.sh` after every layer it runs, so an edit by hand is lost. Revision `08552a6835c7-dirty`.

## Layers

| Layer | Result | Passed | Failed | Skipped | Revision |
|---|---|--:|--:|--:|---|
| Lint | ✅ passed | | | | `08552a6835c7-dirty` |
| Unit | ✅ passed | 1973 | 0 | 0 | `08552a6835c7-dirty` |
| Integration | ❌ failed | 613 | 3 | 0 | `08552a6835c7-dirty` |
| End-to-end | ✅ passed | 25 | 0 | 0 | `08552a6835c7-dirty` |

## Failures

### Integration · auth · `src.services.auth.tests.integration.test_name_migration::test_after_the_migration_every_key_is_set_and_unique`

```text
AssertionError: assert {1: 'sam 2', ...am', 3: 'ada'} == {1: 'sam', 2:... 2', 3: 'ada'}
  
  Omitting 1 identical items, use -vv to show
  Differing items:
  {1: 'sam 2'} != {1: 'sam'}
  {2: 'sam'} != {2: 'sam 2'}
  
  Full diff:
    {
  -     1: 'sam',
  -     2: 'sam 2',
  ?     ^
  +     1: 'sam 2',
  ?     ^
  +     2: 'sam',
        3: 'ada',
    }
```

### Integration · auth · `src.services.auth.tests.integration.test_name_migration::test_duplicates_only_normalising_reveals_are_renamed`

```text
AssertionError: assert 'José 2' == 'José'
  
  - José
  + José 2
  ?     ++
```

### Integration · auth · `src.services.auth.tests.integration.test_name_migration::test_every_duplicate_but_the_oldest_is_renamed`

```text
AssertionError: assert 'Sam 3' == 'Sam'
  
  - Sam
  + Sam 3
  ?    ++
```

## Journeys

### Channels

4 of 4 passed.

| Scenario | Result |
|---|---|
| Ada signs in and sees her workspace | ✅ passed |
| Ada creates a public channel and lands in it | ✅ passed |
| A new public channel appears for another member | ✅ passed |
| Ada creates a private channel and only she can see it | ✅ passed |

### Direct messages

1 of 1 passed.

| Scenario | Result |
|---|---|
| Grace sees the direct message Ada starts, and replies | ✅ passed |

### Display names

1 of 1 passed.

| Scenario | Result |
|---|---|
| Alan renames himself and Grace sees it after reloading | ✅ passed |

### File attachments

1 of 1 passed.

| Scenario | Result |
|---|---|
| Grace sees the image and the PDF Ada sends | ✅ passed |

### Messages

4 of 4 passed.

| Scenario | Result |
|---|---|
| Ada sends a message and sees it in the channel | ✅ passed |
| Grace sees Ada's message after reloading | ✅ passed |
| Ada edits her own message and it shows an edited marker | ✅ passed |
| Ada deletes her own message and a tombstone remains after reload | ✅ passed |

### Permissions

3 of 3 passed.

| Scenario | Result |
|---|---|
| An admin adds a member to a private channel and they can see it | ✅ passed |
| Removing a member revokes their view of the private channel | ✅ passed |
| A non-member cannot open a private channel by its URL | ✅ passed |

### Reactions

1 of 1 passed.

| Scenario | Result |
|---|---|
| Grace sees Ada's reaction without reloading | ✅ passed |

### Read state

1 of 1 passed.

| Scenario | Result |
|---|---|
| Grace's unread count clears once she has read the channel | ✅ passed |

### Real-time delivery

4 of 4 passed.

| Scenario | Result |
|---|---|
| Grace sees Ada's message without reloading | ✅ passed |
| Ada's edit propagates to Grace live | ✅ passed |
| Ada's delete propagates to Grace live | ✅ passed |
| The stream recovers after the connection drops | ✅ passed |

### Search

1 of 1 passed.

| Scenario | Result |
|---|---|
| Ada finds a message and opens it in its channel | ✅ passed |

### Sessions

3 of 3 passed.

| Scenario | Result |
|---|---|
| Ada signs out and stays signed out after reloading | ✅ passed |
| Following a channel link without signing in asks for sign-in | ✅ passed |
| Ada switches workspace and leaves the demo channels behind | ✅ passed |

### Threads

1 of 1 passed.

| Scenario | Result |
|---|---|
| Grace sees Ada's reply in a thread without reloading | ✅ passed |

## By service

| Service | Unit | Integration |
|---|---|---|
| asset | ✅ 39 passed | ✅ 34 passed |
| auth | ✅ 108 passed | ❌ 3 of 160 failed |
| canvas | ✅ 2 passed | — |
| messaging | ✅ 136 passed | ✅ 325 passed |
| other | ✅ 889 passed | ✅ 48 passed |
| shared | ✅ 94 passed | ✅ 26 passed |
| testkit | ✅ 130 passed | ✅ 6 passed |
| worker | ✅ 19 passed | ✅ 17 passed |
| frontend | ✅ 556 passed | — |

## Coverage

Unit tests only.

| Package | Lines | Branches |
|---|---|---|
| asset | `██████░░░░` 66% | `█████░░░░░` 54% |
| auth | `██████░░░░` 63% | `██░░░░░░░░` 28% |
| canvas | `█████████░` 96% | — |
| contracts | `██████████` 100% | — |
| messaging | `█████░░░░░` 56% | `███░░░░░░░` 31% |
| shared | `█████████░` 90% | `███████░░░` 75% |
| worker | `██████░░░░` 65% | `███░░░░░░░` 30% |
| frontend | `█████████░` 96% | `████████░░` 88% |
