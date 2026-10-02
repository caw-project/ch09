@bdd
Feature: File attachments

  A message can carry files: images to look at and PDFs to download. They go
  straight from the sender's browser to storage and back, and anyone who can
  see the message can open them.

  Background:
    Given Ada is signed in

  # The one journey a browser is needed for: the upload, storage's CORS, the
  # claim, the broadcast and a download of the same bytes. The limits, the
  # claim rules, paste, freshness and restore are proven lower down.
  Scenario: Grace sees the image and the PDF Ada sends
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    When Ada attaches "diagram.png" and "notes.pdf"
    And Ada sends "the plans"
    Then Grace sees "the plans" in the channel without reloading
    And Grace sees "diagram.png" shown inline with "the plans"
    And Grace sees "notes.pdf" as a download with "the plans"
    And the "notes.pdf" Grace downloads is the file Ada attached
    And "the plans" appears in Ada's channel exactly once
