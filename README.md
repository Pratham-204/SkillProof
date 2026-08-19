# SkillProof

Verifies a developer's self-reported skills against their public GitHub activity, producing a public Evidence Card per claimed skill instead of a self-reported resume line. See `.scratch/skillproof-mvp/spec.md` for the product spec and `CONTEXT.md` / `docs/adr/` for domain language and architecture decisions.

## Setup

```
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"   # Windows
# source .venv/bin/activate && pip install -e ".[dev]"   # macOS/Linux
```

Configure via environment variables (see `src/skillproof/config.py` for the full list and defaults), most importantly:

- `SKILLPROOF_GITHUB_CLIENT_ID` / `SKILLPROOF_GITHUB_CLIENT_SECRET` — a GitHub OAuth App's credentials.
- `SKILLPROOF_TOKEN_ENCRYPTION_KEY` — a Fernet key (`Fernet.generate_key()`); without one set, a fresh key is generated per process, which is fine for local dev but means stored tokens won't decrypt across restarts.
- `SKILLPROOF_GROQ_API_KEY` — a Groq API key for the `/explain` endpoint (free tier). Explanations fall back to a deterministic template if unset or unavailable.

## Run

```
.venv/Scripts/uvicorn skillproof.main:app --reload
```

## Test

```
.venv/Scripts/pytest
```

Tests drive the full pipeline (connect → verify → poll → evidence card → explain → search) through the HTTP API, with GitHub and Groq faked and embeddings/scoring running for real — see `tests/conftest.py` and `tests/test_api_flow.py`.