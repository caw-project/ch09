@bdd
Feature: Display names

  A name is what everyone else reads beside your words, so it is yours to change and
  nobody else's. The window that changes it shows the new name at once; everyone else
  sees it the next time their copy of the workspace's names is fetched, which a reload
  always does.

  Background:
    Given Ada is signed in
    And Ada has created a public channel named "general"

  Scenario: Alan renames himself and Grace sees it after reloading
    Given Alan has sent "the machine is thinking" in "general"
    When Alan changes his display name to "Alan Turing"
    Then Alan's own name reads "Alan Turing"
    When Grace reloads CollabHub
    And Grace opens the "general" channel
    Then Grace sees "the machine is thinking" written by "Alan Turing"
