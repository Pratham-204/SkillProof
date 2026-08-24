"""Drives the full SkillProof pipeline through the public HTTP API, per the
spec's testing decisions: one seam at the FastAPI boundary, GitHub and Groq
faked with fixture/canned data, embeddings and scoring run for real.
"""

import pytest

from skillproof import taxonomy, verify_service
from skillproof.models import Candidate, EvidenceCard, Sighting
from tests.fixtures.github_fixtures import OWNED_REPO, wire_verified_candidate


def _connect(client, *, login="octodev", github_user_id=42, code="test-code") -> dict:
    """Drives the OAuth callback (which now redirects and sets a session cookie,
    ADR-0006) then reads the resulting identity back via /auth/github/me, so
    callers get the same {candidate_id, github_login, ...} shape as before."""
    response = client.get(f"/auth/github/callback?code={code}", follow_redirects=False)
    assert response.status_code in (302, 307)

    me = client.get("/auth/github/me")
    assert me.status_code == 200
    return me.json()


def test_connect_creates_then_reuses_candidate_identity(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")

    first = _connect(client)
    second = _connect(client)

    assert first["candidate_id"] == second["candidate_id"]
    assert first["github_login"] == "octodev"


def test_verify_rejects_unknown_skill_tag(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    _connect(client)

    response = client.post("/verify", json={"skills": ["Not A Real Skill"]})

    assert response.status_code == 400


def test_verify_rejects_skill_removed_from_taxonomy(client, fake_github):
    """System design has no authorable Detection Pattern (ticket 01) and was
    removed from the taxonomy; it must be rejected the same way an unknown
    skill is, with no separate rejection path."""
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    _connect(client)

    response = client.post("/verify", json={"skills": ["System design"]})

    assert response.status_code == 400


def test_verify_scores_qualifying_evidence_and_excludes_low_signal(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate = _connect(client)
    candidate_id = candidate["candidate_id"]

    verify_response = client.post(
        "/verify",
        json={"skills": ["FastAPI", "Rust"], "searchable": True},
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


def test_verify_excludes_external_repo_commit_not_part_of_any_merged_pr(client, fake_github):
    """The fixture's external repo has an author-matching commit
    ('e2-not-in-any-merged-pr') that isn't part of the Candidate's merged PR
    there — ticket 03's fork-and-fake defense must never let it count."""
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]

    client.post("/verify", json={"skills": ["FastAPI"]})

    card = client.get(f"/evidence-card/{candidate_id}").json()["cards"][0]
    refs = {r["ref"] for r in card["source_commits"]}
    assert "e2-not-in-any-merged-pr" not in refs


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

    client.post("/verify", json={"skills": ["FastAPI"]})
    first = client.get(f"/evidence-card/{candidate_id}").json()["cards"]
    assert len(first) == 1

    client.post("/verify", json={"skills": ["FastAPI"]})
    second = client.get(f"/evidence-card/{candidate_id}").json()["cards"]

    assert len(second) == 1  # overwritten in place, not duplicated
    assert second[0]["confidence_score"] == first[0]["confidence_score"]
    assert second[0]["taxonomy_version"] == taxonomy.taxonomy_version()


def test_reverify_under_bumped_taxonomy_version_forks_a_new_card(client, fake_github, db_session_factory, monkeypatch):
    """A re-verify under an unchanged taxonomy_version overwrites in place (see above);
    one under a newer taxonomy_version must fork instead, so the old card stays
    traceable to the taxonomy it was actually scored under (ADR-0005/ticket 04)."""
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]
    original_version = taxonomy.taxonomy_version()

    client.post("/verify", json={"skills": ["FastAPI"]})
    first = client.get(f"/evidence-card/{candidate_id}").json()["cards"]
    assert len(first) == 1
    assert first[0]["taxonomy_version"] == original_version

    monkeypatch.setattr(taxonomy, "taxonomy_version", lambda: original_version + 1)

    client.post("/verify", json={"skills": ["FastAPI"]})
    second = client.get(f"/evidence-card/{candidate_id}").json()["cards"]

    # GET returns only the latest taxonomy_version per skill by default.
    assert len(second) == 1
    assert second[0]["taxonomy_version"] == original_version + 1

    db = db_session_factory()
    try:
        rows = db.query(EvidenceCard).filter_by(candidate_id=candidate_id, skill="FastAPI").all()
        assert len(rows) == 2  # old card forked off, not mutated
        assert {r.taxonomy_version for r in rows} == {original_version, original_version + 1}
    finally:
        db.close()


def test_verify_with_revoked_token_prompts_reconnect(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]
    fake_github.revoked_tokens.add("token-for-test-code")

    client.post("/verify", json={"skills": ["FastAPI"]})

    body = client.get(f"/evidence-card/{candidate_id}").json()
    assert body["needs_reconnect"] is True
    assert body["cards"][0]["status"] == "failed"
    assert "reconnect" in body["cards"][0]["error"].lower()


def test_verify_with_undecryptable_token_prompts_reconnect(client, fake_github, db_session_factory):
    """Same remedy as a revoked token, but a different cause: the stored ciphertext
    no longer decrypts under the current SKILLPROOF_TOKEN_ENCRYPTION_KEY — e.g. the
    key changed since the token was stored, which the fresh-key-per-process default
    makes trivial to hit in a real deploy (ticket 09) and which this session actually
    hit live against a real GitHub account after restarting the backend process."""
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]

    # A validly-formatted Fernet token, just encrypted under a different key than
    # the app's current one — exactly what a key rotation/regeneration produces,
    # as opposed to a malformed string (which would raise a different, unwrapped
    # exception from the base64 layer rather than cryptography's InvalidToken).
    from cryptography.fernet import Fernet

    bogus_token = Fernet(Fernet.generate_key()).encrypt(b"github-token").decode()

    db = db_session_factory()
    try:
        candidate = db.get(Candidate, candidate_id)
        candidate.github_token_encrypted = bogus_token
        db.commit()
    finally:
        db.close()

    client.post("/verify", json={"skills": ["FastAPI"]})

    body = client.get(f"/evidence-card/{candidate_id}").json()
    assert body["needs_reconnect"] is True
    assert body["cards"][0]["status"] == "failed"
    assert "reconnect" in body["cards"][0]["error"].lower()


def test_explain_generates_then_caches(client, fake_github, fake_groq):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]
    client.post("/verify", json={"skills": ["FastAPI"]})

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
    client.post("/verify", json={"skills": ["FastAPI"]})

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

    # Identity now comes from whichever session is currently active (ADR-0006),
    # so each candidate must be the active session at the moment they /verify.
    opted_in = _connect(client, login="octodev", github_user_id=42, code="code-a")
    client.post("/verify", json={"skills": ["FastAPI"], "searchable": True})

    opted_out = _connect(client, login="privatedev", github_user_id=99, code="code-b")
    client.post("/verify", json={"skills": ["FastAPI"], "searchable": False})

    results = client.get("/search?skill=FastAPI").json()["results"]

    result_ids = [r["candidate_id"] for r in results]
    assert opted_in["candidate_id"] in result_ids
    assert opted_out["candidate_id"] not in result_ids
    assert all(r["matches"] for r in results)

    top_result = next(r for r in results if r["candidate_id"] == opted_in["candidate_id"])
    assert top_result["github_profile_url"] == "https://github.com/octodev"
    assert top_result["evidence_card_url"].startswith("http")
    assert top_result["evidence_card_url"].endswith(f"/evidence-card/{opted_in['candidate_id']}")
    assert top_result["matches"] == [
        {"skill": "FastAPI", "confidence_score": top_result["average_score"], "evidence_type": "verified"}
    ]

    # Opting out of search never breaks the direct Evidence Card link.
    direct = client.get(f"/evidence-card/{opted_out['candidate_id']}")
    assert direct.status_code == 200


def test_search_and_semantics_requires_every_selected_skill(client, fake_github):
    """AND semantics (ADR-0007): a candidate must have a qualifying card for
    every selected skill to appear. Django is manifest-declared but never
    touched in the fixture, proving declared_only still counts as a match."""
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="code-a")
    wire_verified_candidate(fake_github, login="onlyfastapi", github_user_id=43, code="code-b")

    full_stack = _connect(client, login="octodev", github_user_id=42, code="code-a")
    client.post("/verify", json={"skills": ["FastAPI", "Django"], "searchable": True})

    partial = _connect(client, login="onlyfastapi", github_user_id=43, code="code-b")
    client.post("/verify", json={"skills": ["FastAPI"], "searchable": True})

    results = client.get("/search?skill=FastAPI&skill=Django").json()["results"]
    result_ids = [r["candidate_id"] for r in results]

    assert full_stack["candidate_id"] in result_ids
    assert partial["candidate_id"] not in result_ids

    match = next(r for r in results if r["candidate_id"] == full_stack["candidate_id"])
    matches_by_skill = {m["skill"]: m for m in match["matches"]}
    assert matches_by_skill["FastAPI"]["evidence_type"] == "verified"
    assert matches_by_skill["Django"]["evidence_type"] == "declared_only"
    assert 0 < matches_by_skill["Django"]["confidence_score"] < matches_by_skill["FastAPI"]["confidence_score"]


def test_search_average_score_only_covers_selected_skills(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="code-a")
    _connect(client, login="octodev", github_user_id=42, code="code-a")
    client.post("/verify", json={"skills": ["FastAPI", "Django"], "searchable": True})

    fastapi_only = client.get("/search?skill=FastAPI").json()["results"][0]
    combined = client.get("/search?skill=FastAPI&skill=Django").json()["results"][0]

    fastapi_score = next(m["confidence_score"] for m in combined["matches"] if m["skill"] == "FastAPI")
    django_score = next(m["confidence_score"] for m in combined["matches"] if m["skill"] == "Django")

    # A single-skill query's average must equal that skill's own score, even
    # though the candidate has a second claimed skill — proves the average
    # never folds in a skill outside the query.
    assert fastapi_only["average_score"] == fastapi_score
    assert combined["average_score"] == pytest.approx((fastapi_score + django_score) / 2)


def test_search_rejects_more_than_eight_skills(client, fake_github):
    too_many = "&".join(f"skill=Skill{i}" for i in range(9))
    response = client.get(f"/search?{too_many}")
    assert response.status_code == 400

    exactly_eight = "&".join(f"skill=Skill{i}" for i in range(8))
    response = client.get(f"/search?{exactly_eight}")
    assert response.status_code == 200


def test_search_deduplicates_a_repeated_skill_value(client, fake_github):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="code-a")
    _connect(client, login="octodev", github_user_id=42, code="code-a")
    client.post("/verify", json={"skills": ["FastAPI"], "searchable": True})

    body = client.get("/search?skill=FastAPI&skill=FastAPI").json()
    assert body["skills"] == ["FastAPI"]

    result = body["results"][0]
    assert result["matches"] == [
        {"skill": "FastAPI", "confidence_score": result["average_score"], "evidence_type": "verified"}
    ]


def test_verify_produces_declared_only_for_a_manifest_dependency_never_touched(client, fake_github):
    """Django is declared in the fixture's requirements.txt but never touched by
    any commit, proving the declared_only path (issue 02) end to end."""
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]

    client.post("/verify", json={"skills": ["Django"]})

    card = client.get(f"/evidence-card/{candidate_id}").json()["cards"][0]
    assert card["evidence_type"] == "declared_only"
    assert 0 < card["confidence_score"] < 0.3
    assert card["source_commits"] == []


def test_verify_records_a_sighting_for_an_unrecognized_manifest_package(client, fake_github, db_session_factory):
    """The fixture's requirements.txt declares 'gunicorn', which matches no Skill
    Tag's Detection Pattern — round 8's Sighting recording must pick it up, while
    'Django' (an already-known Skill Tag) produces no Sighting."""
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]

    client.post("/verify", json={"skills": ["FastAPI"]})

    db = db_session_factory()
    try:
        sightings = db.query(Sighting).filter_by(candidate_id=candidate_id).all()
        assert [(s.ecosystem, s.package_name) for s in sightings] == [("pip", "gunicorn")]
        assert sightings[0].repo == OWNED_REPO.full_name
    finally:
        db.close()


def test_reverify_does_not_duplicate_an_already_recorded_sighting(client, fake_github, db_session_factory):
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]

    client.post("/verify", json={"skills": ["FastAPI"]})
    client.post("/verify", json={"skills": ["FastAPI"]})

    db = db_session_factory()
    try:
        sightings = db.query(Sighting).filter_by(candidate_id=candidate_id).all()
        assert len(sightings) == 1
    finally:
        db.close()


def test_search_dedupes_a_candidate_forked_across_taxonomy_versions(client, fake_github, monkeypatch):
    """A candidate with cards for the same skills under two taxonomy_versions
    (ticket 04's fork) must appear once in /search, at their latest version —
    not once per stale + current card. Exercised with a 2-skill AND query so
    the per-skill dedup must hold independently for each skill being
    intersected, not just in the single-skill case."""
    wire_verified_candidate(fake_github, login="octodev", github_user_id=42, code="test-code")
    candidate_id = _connect(client)["candidate_id"]
    original_version = taxonomy.taxonomy_version()

    client.post("/verify", json={"skills": ["FastAPI", "Django"], "searchable": True})

    monkeypatch.setattr(taxonomy, "taxonomy_version", lambda: original_version + 1)
    client.post("/verify", json={"skills": ["FastAPI", "Django"], "searchable": True})

    results = client.get("/search?skill=FastAPI&skill=Django").json()["results"]
    matches = [r for r in results if r["candidate_id"] == candidate_id]

    assert len(matches) == 1


def test_search_is_rate_limited_per_ip(client, fake_github):
    for _ in range(60):
        response = client.get("/search?skill=FastAPI")
        assert response.status_code == 200

    throttled = client.get("/search?skill=FastAPI")
    assert throttled.status_code == 429
