from skillproof import taxonomy, taxonomy_growth
from skillproof.groq_client import FakeGroqClient, SkillTagDraft
from skillproof.models import Sighting, SightingDecision
from skillproof.registry_client import FakeRegistryClient


def _seed_sightings(db, ecosystem: str, package_name: str, n_candidates: int, repo: str = "octodev/lib") -> None:
    for i in range(n_candidates):
        db.add(Sighting(ecosystem=ecosystem, package_name=package_name, candidate_id=f"candidate-{i}", repo=repo))
    db.commit()


def test_below_threshold_sightings_produce_no_publish(db_session_factory, isolated_taxonomy_file, fake_embeddings):
    db = db_session_factory()
    _seed_sightings(db, "npm", "skillproof-test-widget", n_candidates=taxonomy_growth.MIN_DISTINCT_CANDIDATES - 1)

    published = taxonomy_growth.publish_new_skill_tags(
        db,
        FakeRegistryClient(known={("npm", "skillproof-test-widget")}),
        FakeGroqClient(draft_response=SkillTagDraft(name="Widget", category="tool", description="x")),
    )

    assert published == 0
    assert taxonomy.is_known_skill("Widget") is False


def test_eligible_sighting_publishes_a_working_skill_tag(db_session_factory, isolated_taxonomy_file, fake_embeddings):
    db = db_session_factory()
    _seed_sightings(db, "npm", "skillproof-test-widget", n_candidates=taxonomy_growth.MIN_DISTINCT_CANDIDATES)
    original_version = taxonomy.taxonomy_version()
    draft = SkillTagDraft(name="Widget", category="tool", description="Pads strings to a given length.")

    published = taxonomy_growth.publish_new_skill_tags(
        db, FakeRegistryClient(known={("npm", "skillproof-test-widget")}), FakeGroqClient(draft_response=draft)
    )

    assert published == 1
    assert taxonomy.taxonomy_version() == original_version + 1
    skill = taxonomy.get_skill("Widget")
    assert skill.category == "tool"
    assert skill.detection_pattern.manifest_packages == (
        taxonomy.ManifestPackage(ecosystem="npm", name="skillproof-test-widget"),
    )
    decision = db.query(SightingDecision).filter_by(ecosystem="npm", package_name="skillproof-test-widget").one()
    assert decision.decision == "published"


def test_nonexistent_package_is_skipped_without_deciding_or_calling_llm(
    db_session_factory, isolated_taxonomy_file, fake_embeddings
):
    db = db_session_factory()
    _seed_sightings(db, "npm", "totally-fake-pkg", n_candidates=taxonomy_growth.MIN_DISTINCT_CANDIDATES)
    groq = FakeGroqClient(draft_response=SkillTagDraft(name="x", category="tool", description="y"))

    published = taxonomy_growth.publish_new_skill_tags(db, FakeRegistryClient(known=set()), groq)

    assert published == 0
    assert groq.draft_calls == []
    assert db.query(SightingDecision).count() == 0


def test_exact_name_duplicate_is_skipped_before_the_llm_is_called(
    db_session_factory, isolated_taxonomy_file, fake_embeddings
):
    """'react' (npm) matches the existing 'React' Skill Tag case-insensitively."""
    db = db_session_factory()
    _seed_sightings(db, "npm", "react", n_candidates=taxonomy_growth.MIN_DISTINCT_CANDIDATES)
    groq = FakeGroqClient(draft_response=SkillTagDraft(name="React clone", category="tool", description="y"))

    published = taxonomy_growth.publish_new_skill_tags(db, FakeRegistryClient(known={("npm", "react")}), groq)

    assert published == 0
    assert groq.draft_calls == []
    decision = db.query(SightingDecision).filter_by(ecosystem="npm", package_name="react").one()
    assert decision.decision == "rejected_duplicate"


def test_llm_abstain_adds_no_entry(db_session_factory, isolated_taxonomy_file, fake_embeddings):
    db = db_session_factory()
    _seed_sightings(db, "npm", "skillproof-test-widget", n_candidates=taxonomy_growth.MIN_DISTINCT_CANDIDATES)

    published = taxonomy_growth.publish_new_skill_tags(
        db, FakeRegistryClient(known={("npm", "skillproof-test-widget")}), FakeGroqClient(draft_response=None)
    )

    assert published == 0
    assert taxonomy.is_known_skill("skillproof-test-widget") is False
    decision = db.query(SightingDecision).filter_by(ecosystem="npm", package_name="skillproof-test-widget").one()
    assert decision.decision == "abstained"


def test_llm_response_outside_fixed_categories_is_treated_as_abstain(
    db_session_factory, isolated_taxonomy_file, fake_embeddings
):
    db = db_session_factory()
    _seed_sightings(db, "npm", "skillproof-test-widget", n_candidates=taxonomy_growth.MIN_DISTINCT_CANDIDATES)
    bad_draft = SkillTagDraft(name="Widget", category="widgetry", description="x")

    published = taxonomy_growth.publish_new_skill_tags(
        db, FakeRegistryClient(known={("npm", "skillproof-test-widget")}), FakeGroqClient(draft_response=bad_draft)
    )

    assert published == 0
    decision = db.query(SightingDecision).filter_by(ecosystem="npm", package_name="skillproof-test-widget").one()
    assert decision.decision == "abstained"


def test_llm_failure_is_skipped_without_deciding(db_session_factory, isolated_taxonomy_file, fake_embeddings):
    db = db_session_factory()
    _seed_sightings(db, "npm", "skillproof-test-widget", n_candidates=taxonomy_growth.MIN_DISTINCT_CANDIDATES)

    published = taxonomy_growth.publish_new_skill_tags(
        db, FakeRegistryClient(known={("npm", "skillproof-test-widget")}), FakeGroqClient(draft_should_fail=True)
    )

    assert published == 0
    assert db.query(SightingDecision).count() == 0


def test_already_decided_pair_is_not_reprocessed(db_session_factory, isolated_taxonomy_file, fake_embeddings):
    db = db_session_factory()
    db.add(SightingDecision(ecosystem="npm", package_name="skillproof-test-widget", decision="abstained"))
    db.commit()
    _seed_sightings(db, "npm", "skillproof-test-widget", n_candidates=taxonomy_growth.MIN_DISTINCT_CANDIDATES)
    groq = FakeGroqClient(draft_response=SkillTagDraft(name="Widget", category="tool", description="x"))

    published = taxonomy_growth.publish_new_skill_tags(
        db, FakeRegistryClient(known={("npm", "skillproof-test-widget")}), groq
    )

    assert published == 0
    assert groq.draft_calls == []


def test_multiple_publishes_in_one_run_bump_version_exactly_once(
    db_session_factory, isolated_taxonomy_file, fake_embeddings
):
    db = db_session_factory()
    _seed_sightings(db, "npm", "skillproof-widget-one", n_candidates=taxonomy_growth.MIN_DISTINCT_CANDIDATES)
    _seed_sightings(db, "npm", "skillproof-widget-two", n_candidates=taxonomy_growth.MIN_DISTINCT_CANDIDATES)
    original_version = taxonomy.taxonomy_version()
    draft = SkillTagDraft(name="Widget", category="tool", description="A generic widget.")

    published = taxonomy_growth.publish_new_skill_tags(
        db,
        FakeRegistryClient(known={("npm", "skillproof-widget-one"), ("npm", "skillproof-widget-two")}),
        FakeGroqClient(draft_response=draft),
    )

    assert published == 2
    assert taxonomy.taxonomy_version() == original_version + 1
