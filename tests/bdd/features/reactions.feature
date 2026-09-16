@bdd
Feature: Reactions

  Sometimes the useful answer to a message is not another message. Anyone who
  can see a channel can react to what was said in it, choosing from a small
  fixed set of emoji, and everyone in the channel sees the same counts.

  A reaction is yours or it is not: reacting twice the same way is still one
  reaction, and clicking a reaction you have already given takes it back.
  Somebody else reacting the same way adds to the count beside yours rather
  than replacing it.

  Reactions arrive while you are looking at the channel, without a reload, the
  same way messages do.

  Background:
    Given Ada is signed in

  # The one journey a browser is needed for: two people, one count. The
  # allowlist, the idempotency, the ordering and the per-caller highlight are
  # all proven lower down — unit tests for the rules, Messaging's integration
  # tests for the routes and the broadcast, Vitest for the cache.
  Scenario: Grace sees Ada's reaction without reloading
    Given Ada has created a public channel named "general"
    And Ada has sent "the eagle has landed" in "general"
    And Grace is watching the "general" channel
    When Ada reacts to "the eagle has landed" with "tada"
    Then Grace sees "the eagle has landed" with 1 "tada" reaction
    And Ada sees "the eagle has landed" with 1 "tada" reaction
