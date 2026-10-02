@bdd
Feature: Search

  Ada can find something said in any channel she can see by searching for its
  words, and open it where it was said — scrolled to and highlighted, in the
  middle of the conversation around it.

  Background:
    Given Ada is signed in

  # The one journey a browser is needed for: posted, indexed by the Worker, found
  # through Messaging, opened in place. Rows, paging, the jump's cap and its
  # races are proven in Vitest.
  Scenario: Ada finds a message and opens it in its channel
    Given Ada has created a public channel named "general"
    And Ada has sent "the zeppelin lands at dawn" in "general"
    When Ada searches for "zeppelin"
    Then Ada sees "the zeppelin lands at dawn" in the search results
    When Ada opens the search result "the zeppelin lands at dawn"
    Then Ada sees "the zeppelin lands at dawn" highlighted
    And Ada is looking at the "general" channel
