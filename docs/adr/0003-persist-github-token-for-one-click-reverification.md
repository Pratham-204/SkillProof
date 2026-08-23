# Persist the Candidate's GitHub access token for one-click re-verification

Candidate identity is persistent across logins, and re-verification is meant to be a single action rather than a repeated OAuth redirect. We decided to store the Candidate's GitHub OAuth token (read-only public scope) encrypted at rest, tied to the Candidate record, and reuse it for background re-verification. A revoked token fails the next verify attempt gracefully and prompts the Candidate to reconnect.

## Consequences

This is the one place SkillProof takes on real credential-custody responsibility in MVP — encryption at rest and graceful revocation handling are load-bearing from day one, not something to defer.
