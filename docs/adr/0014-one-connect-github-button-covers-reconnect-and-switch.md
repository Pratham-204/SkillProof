# Reconnect and account-switch collapse into one GitHub OAuth button, with no visible sign-out

The Candidate Dashboard needed both a manual way to reconnect a revoked GitHub token and a way to authorize as a different GitHub account. Since both are literally the same request — a fresh `/auth/github/login` redirect, with the outcome decided by whichever identity authorizes on GitHub's side — we built one "Connect GitHub Account" button instead of two differently-labeled controls for the same mechanism. Switching identity has no confirmation step and no separate sign-out: clicking the button and authorizing as someone else on GitHub silently replaces the active session, consistent with round 10's decision to keep sign-out out of scope.

## Considered Options

Two separate buttons ("Reconnect" vs. "Use a different account") — rejected, since they'd fire the identical request and only differ in label, inviting drift once one path changes and the other doesn't. A visible sign-out control as a prerequisite to switching — rejected, since it would reverse round 10's sign-out-out-of-scope decision for a control that adds a step without changing the outcome (the new OAuth authorization already replaces the session regardless).

## Consequences

A Candidate who clicks the button while still logged into the same GitHub account in their browser gets silently re-authorized as themselves with no visible change — GitHub's OAuth flow has no forced account-picker parameter. The Dashboard button's copy explains this rather than leaving it as a silent no-op.
