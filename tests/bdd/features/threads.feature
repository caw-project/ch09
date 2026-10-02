@bdd
Feature: Threads

  A reply that answers one message shouldn't push the rest of the channel out of
  view. Anyone who can see a channel can reply to a message in a thread: the
  replies sit in a panel beside the channel, and the message they answer shows
  how many there are and when the last one came, for everyone, as it happens.

  Background:
    Given Ada is signed in

  # The one journey a browser is needed for: two people, one count, and a thread
  # opened from the server. Normalising a reply, the exclusions from history,
  # unread and search, the summary rules and the panel's scroll and draft rules
  # are proven lower down.
  Scenario: Grace sees Ada's reply in a thread without reloading
    Given Ada has created a public channel named "general"
    And Ada has sent "who is on call tonight?" in "general"
    And Grace is looking at the "general" channel
    When Ada replies "I am" in the thread on "who is on call tonight?"
    Then Grace sees 1 reply on "who is on call tonight?" without reloading
    When Grace opens the thread on "who is on call tonight?"
    Then Grace sees "I am" in the thread
