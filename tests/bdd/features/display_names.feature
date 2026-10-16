@bdd
Feature: Display names

  Alan changes the name everyone sees him by, on his Settings page.

  Display names are one per person across all of CollabHub, so the name Alan
  chooses is his alone; the rules for what a name may be, and for a name that is
  taken, are proven below the browser. What only a browser can show is that the
  change reaches other people: Alan sees it at once, and Grace, who had never
  heard of it, sees it on his message after a reload — because the name she reads
  comes from Auth, not from anything Alan's window remembers.

  Background:
    Given Alan is signed in

  Scenario: Grace sees the name Alan gives himself, after a reload
    Given Alan has created a public channel named "general"
    And Alan has sent "the bombe is running" in "general"
    When Alan renames himself to "Alan Turing" on Settings
    Then Alan sees his own name as "Alan Turing"
    When Grace reloads CollabHub
    And Grace opens the "general" channel
    Then Grace sees "the bombe is running" written by "Alan Turing"
