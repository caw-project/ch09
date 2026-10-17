@bdd
Feature: Settings

  Everyone has one name across CollabHub, and it is theirs to change. Somebody
  who renames themselves sees the new name at once; everyone else sees it the
  next time their copy of the workspace's people is fetched — reloading is enough.

  Background:
    Given Ada is signed in

  # Alan's name is never put back: renaming him to the name he already has is a
  # no-op, so a rerun against a kept stack still passes.
  Scenario: Grace sees the name Alan gives himself on his message
    Given Ada has created a public channel named "general"
    And Alan has sent "the machine is thinking" in "general"
    When Alan changes his display name to "Alan Turing"
    Then Alan's sidebar shows him as "Alan Turing"
    When Grace reloads CollabHub
    And Grace opens the "general" channel
    Then Grace sees "the machine is thinking" written by "Alan Turing"
