"""Drives the full SkillProof pipeline through the public HTTP API, per the
spec's testing decisions: one seam at the FastAPI boundary, GitHub and Groq
faked with fixture/canned data, embeddings and scoring run for real.
"""

from skillproof import verify_service
from skillproof.models import Candidate
from tests.fixtures.github_fixtures import wire_verified_candidate


def _connect(client, *, login="octodev", github_user_id=42, code="test-code") -> dict:
    response = client.get(f"/auth/github/callback?code={code}")
    assert response.status_code == 200
    return response.json()


def test_connect_creates_then_reuses_candidate_identity(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")

    first = _connect(client)
    second = _connect(client)

    assert first["candidate_id"] == second["candidate_id"]
    assert first["github_login"] == "octodev"


def test_verify_rejects_unknown_skill_tag(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate = _connect(client)

    response = client.post(
        "/verify", json={"candidate_id": candidate["candidate_id"], "skills": ["Not A Real Skill"]}
    )

    assert response.status_code == 400


def test_verify_rejects_skill_removed_from_taxonomy(client, fake_github):
    """System design has no authorable Detection Pattern (ticket 01) and was
    removed from the taxonomy; it must be rejected the same way an unknown
    skill is, with no separate rejection path."""
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate = _connect(client)

    response = client.post("/verify", json={"candidate_id": candidate["candidate_id"], "skills": ["System design"]})

    assert response.status_code == 400


def test_verify_scores_qualifying_evidence_and_excludes_low_signal(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate = _connect(client)
    candidate_id = candidate["candidate_id"]

    verify_response = client.post(
        "/verify",
        json={"candidate_id": candidate_id, "skills": ["FastAPI", "Rust"], "searchable": True},
    )
    assert verify_response.status_code == 202

    card_response = client.get(f"/evidence-card/{candidate_id}")
    assert card_response.status_code == 200
    body = card_response.json()
    cards = {c["skill"]: c for c in body["cards"]}

    fastapi_card = cards["FastAPI"]
    assert fastapi_card["status"] == "complete"
    assert fastapi_card["evidence_type"] == "verified"
    assert 0 < fastapi_card["confidence_score"] <= 1
    # The docs-only commit and the "LGTM" comment are dropped before scoring;
    # only the two qualifying commits + the substantive review comment remain.
    refs = {(r["kind"], r["ref"]) for r in fastapi_card["source_commits"]}
    assert refs == {("commit", "c1"), ("commit", "e1"), ("pr_comment", "1")}
    assert fastapi_card["temporal_span_days"] >= 90  # full temporal multiplier

    rust_card = cards["Rust"]
    assert rust_card["status"] == "complete"
    assert rust_card["confidence_score"] == 0
    assert rust_card["evidence_type"] == "none"
    assert rust_card["source_commits"] == []


def test_evidence_card_reflects_processing_state_before_background_job_completes(
    client, fake_github, db_session_factory
):
    """POST /verify returns immediately; GET /evidence-card must show "processing"
    for the window before the background job finishes scoring (issue 04). The
    TestClient runs BackgroundTasks synchronously within the request/response
    cycle, so this exercises the same transition `verify_service` performs,
    stopping short of the second (background) half of the pipeline.
    """
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]

    db = db_session_factory()
    try:
        candidate = db.get(Candidate, candidate_id)
        verify_service.start_verification(db, candidate, ["FastAPI"])
    finally:
        db.close()

    body = client.get(f"/evidence-card/{candidate_id}").json()
    assert body["cards"][0]["status"] == "processing"


def test_reverify_overwrites_existing_card_in_place(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]

    client.post("/verify", json={"candidate_id": candidate_id, "skills": ["FastAPI"]})
    first = client.get(f"/evidence-card/{candidate_id}").json()["cards"]
    assert len(first) == 1

    client.post("/verify", json={"candidate_id": candidate_id, "skills": ["FastAPI"]})
    second = client.get(f"/evidence-card/{candidate_id}").json()["cards"]

    assert len(second) == 1  # overwritten in place, not duplicated
    assert second[0]["confidence_score"] == first[0]["confidence_score"]


def test_verify_with_revoked_token_prompts_reconnect(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]
    fake_github.revoked_tokens.add("token-for-test-code")

    client.post("/verify", json={"candidate_id": candidate_id, "skills": ["FastAPI"]})

    body = client.get(f"/evidence-card/{candidate_id}").json()
    assert body["needs_reconnect"] is True
    assert body["cards"][0]["status"] == "failed"
    assert "reconnect" in body["cards"][0]["error"].lower()


def test_explain_generates_then_caches(client, fake_github, fake_groq):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]
    client.post("/verify", json={"candidate_id": candidate_id, "skills": ["FastAPI"]})

    first = client.post(f"/explain/{candidate_id}/FastAPI")
    assert first.status_code == 200
    assert first.json()["explanation_is_fallback"] is False
    assert len(fake_groq.calls) == 1

    second = client.post(f"/explain/{candidate_id}/FastAPI")
    assert second.json()["explanation"] == first.json()["explanation"]
    assert len(fake_groq.calls) == 1  # cached; LLM not re-triggered


def test_explain_falls_back_then_retries_transparently(client, fake_github, fake_groq):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]
    client.post("/verify", json={"candidate_id": candidate_id, "skills": ["FastAPI"]})

    fake_groq.should_fail = True
    fallback = client.post(f"/explain/{candidate_id}/FastAPI")
    assert fallback.status_code == 200
    assert fallback.json()["explanation_is_fallback"] is True
    assert "FastAPI" in fallback.json()["explanation"]

    fake_groq.should_fail = False
    retried = client.post(f"/explain/{candidate_id}/FastAPI")
    assert retried.json()["explanation_is_fallback"] is False
    assert retried.json()["explanation"] == fake_groq.canned_response


def test_search_returns_only_opted_in_candidates_sorted_by_score(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="code-a")
    wire_verified_candidate(fake_github, login="privatedev", github_user_id=99, code="code-b")

    opted_in = _connect(client, login="octodev", github_user_id=42, code="code-a")
    opted_out = _connect(client, login="privatedev", github_user_id=99, code="code-b")

    client.post("/verify", json={"candidate_id": opted_in["candidate_id"], "skills": ["FastAPI"], "searchable": True})
    client.post("/verify", json={"candidate_id": opted_out["candidate_id"], "skills": ["FastAPI"], "searchable": False})

    results = client.get("/search?skill=FastAPI&min_score=0.1").json()["results"]

    result_ids = [r["candidate_id"] for r in results]
    assert opted_in["candidate_id"] in result_ids
    assert opted_out["candidate_id"] not in result_ids

    top_result = next(r for r in results if r["candidate_id"] == opted_in["candidate_id"])
    assert top_result["github_profile_url"] == "https://github.com/octodev"
    assert top_result["evidence_card_url"].startswith("http")
    assert top_result["evidence_card_url"].endswith(f"/evidence-card/{opted_in['candidate_id']}")

    # Opting out of search never breaks the direct Evidence Card link.
    direct = client.get(f"/evidence-card/{opted_out['candidate_id']}")
    assert direct.status_code == 200


def test_search_is_rate_limited_per_ip(client, fake_github):
    for _ in range(60):
        response = client.get("/search?skill=FastAPI&min_score=0")
        assert response.status_code == 200

    throttled = client.get("/search?skill=FastAPI&min_score=0")
    assert throttled.status_code == 429
