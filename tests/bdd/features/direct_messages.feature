@bdd
Feature: Direct messages

  Any two people in a workspace can talk privately. The + beside Direct messages in the
  sidebar lists everyone else in the workspace; picking someone opens the conversation the
  two of you share, and it is named after them. It shows up in both sidebars as soon as
  something is said in it, with the same unread count a channel has.

  Background:
    Given Ada is signed in

  # The one journey a browser is needed for: two people, one conversation, and a sidebar row
  # that arrives by an event. The pair key, the listing rule, the 404s and every refused edit
  # are proven lower down.
  Scenario: Grace sees the direct message Ada starts, and replies
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    When Ada starts a direct message with Grace
    And Ada sends "hi"
    Then Ada appears in Grace's direct messages with 1 unread message without reloading
    When Grace opens her direct message with Ada
    Then Grace sees "hi" in the channel
    When Grace sends "hello back"
    Then Ada sees "hello back" in the channel without reloading
