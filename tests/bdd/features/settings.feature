@bdd
Feature: Settings

  Everyone's name is their own to choose, and it is the same in every
  workspace. A change shows at once in the renamer's own window; everyone else
  sees it the next time their directory is fetched — a reload is enough.

  Background:
    Given Ada is signed in

  Scenario: Grace sees the name Alan gives himself
    Given Ada has created a public channel named "general"
    And Alan has sent "hello from Alan" in "general"
    When Alan changes his name to "Alan Turing"
    Then Alan sees his name as "Alan Turing"
    When Grace reloads CollabHub
    And Grace opens the "general" channel
    Then Grace sees "hello from Alan" written by "Alan Turing"
