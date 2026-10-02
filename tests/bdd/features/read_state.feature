@bdd
Feature: Read state

  Each channel in the sidebar counts other people's messages you haven't read.
  Looking at a channel's newest message — window in front, scrolled to the end —
  reads it, and the count stays clear wherever you open CollabHub next.

  Background:
    Given Ada is signed in

  # Rules are proven in Vitest; this proves the server's marker moved.
  Scenario: Grace's unread count clears once she has read the channel
    Given Ada has created a public channel named "general"
    And Ada has created a public channel named "random"
    And Ada has created a public channel named "design"
    And Grace is looking at the "general" channel
    When Ada opens the "random" channel
    And Ada sends "lunch is in the kitchen"
    And Grace opens the "design" channel
    Then Grace sees 1 unread message in "random"
    When Grace opens the "random" channel
    Then Grace sees "lunch is in the kitchen" in the channel
    When Grace opens the "general" channel
    And Grace reloads CollabHub
    Then Grace sees no unread messages in "random"
