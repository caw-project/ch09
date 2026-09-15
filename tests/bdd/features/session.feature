@bdd
Feature: Sessions

  Signing in is something people do once and then stop thinking about. A
  session outlives a reload, and it is a session in one workspace rather than in
  the app as a whole: everything someone sees belongs to the workspace they are
  in. Somebody who belongs to more than one can move between them, and the move
  is complete — the channels of the workspace they left are not in the list of
  the one they moved to, and coming back later puts them where they left off.

  Signing out is the opposite promise, and it is kept just as firmly. A browser
  that has signed out has no session left in it, so reloading does not quietly
  sign the person back in. And a link into CollabHub is only a link: someone who
  follows one without being signed in is asked to sign in, and is shown nothing
  of what is behind it first.

  # Signing out and switching workspace both change the session itself, so Ada
  # has a browser of her own in these scenarios rather than the one the other
  # features share — signing her out of that one would sign her out of all of
  # them.

  Scenario: Ada signs out and stays signed out after reloading
    Given Ada is signed in
    When Ada signs out
    Then Ada is asked to sign in
    When Ada reloads CollabHub
    Then Ada is asked to sign in

  Scenario: Following a channel link without signing in asks for sign-in
    Given Ada is signed in
    And Ada has created a public channel named "general"
    When someone who is not signed in opens the link to that channel
    Then they are asked to sign in

  # Every account has a workspace of its own as well as the demo one, named for
  # the account — Ada's is "ada's Workspace".
  Scenario: Ada switches workspace and leaves the demo channels behind
    Given Ada is signed in
    And Ada has created a public channel named "general"
    When Ada switches to the "ada's Workspace" workspace
    Then Ada sees the "ada's Workspace" workspace
    And "general" is not in Ada's channel list
    When Ada reloads CollabHub
    Then Ada sees the "ada's Workspace" workspace
    And "general" is not in Ada's channel list
