"""Production-readiness fixes to the GitHub Actions pipeline and repo-root
deploy config, not application code — see .github/workflows/ci.yml,
.github/dependabot.yml, and .dockerignore.

Two overlapping pushes to main previously had no way to stop an older
commit's `railway up` from finishing after a newer one and silently staying
live; a hung job had no timeout-minutes and could occupy a runner for
GitHub's 6-hour default; the HuggingFace model cache used a fixed key that
could never self-heal from a poisoned entry; docker-smoke-test.yml was a
fully separate workflow file so it could never actually gate `deploy`
(cross-workflow `needs:` doesn't exist), and it only ever booted the
permissive development config against SQLite, never anything resembling
production; and `.dockerignore`'s bare `.env` line doesn't anchor the way a
.gitignore pattern would — it misses a nested file like `frontend/.env`.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPENDABOT_YML = REPO_ROOT / ".github" / "dependabot.yml"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"


def _ci_jobs() -> dict:
    doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    return doc["jobs"]


def test_every_ci_job_has_a_timeout():
    jobs = _ci_jobs()
    assert jobs, "expected at least one job in ci.yml"
    for name, job in jobs.items():
        timeout = job.get("timeout-minutes")
        assert isinstance(timeout, int) and timeout > 0, (
            f"job {name!r} has no timeout-minutes — a hang would occupy a "
            f"runner for GitHub's 6-hour default"
        )


def test_deploy_job_has_a_ref_scoped_cancel_in_progress_concurrency_group():
    deploy = _ci_jobs()["deploy"]
    concurrency = deploy.get("concurrency")
    assert concurrency is not None, "deploy job has no concurrency group"
    assert "github.ref" in concurrency.get("group", ""), (
        "concurrency group isn't scoped to the ref — it would serialize "
        "unrelated branches/PRs together instead of just overlapping pushes "
        "to the same ref"
    )
    assert concurrency.get("cancel-in-progress") is True, (
        "without cancel-in-progress, two overlapping deploys still both run "
        "to completion and an older commit's build can win the race"
    )


def test_railway_cli_install_is_pinned_to_an_explicit_version():
    deploy_steps = _ci_jobs()["deploy"]["steps"]
    install_step = next(s for s in deploy_steps if s.get("name") == "Install Railway CLI")
    run = install_step["run"]
    assert "@railway/cli@" in run, (
        f"Railway CLI install floats on latest instead of pinning a version: {run!r}"
    )
    version = run.split("@railway/cli@", 1)[1].split()[0]
    parts = version.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), (
        f"pinned Railway CLI version doesn't look like a real semver: {version!r}"
    )


def test_huggingface_cache_key_changes_with_pinned_dependencies():
    backend_steps = _ci_jobs()["backend"]["steps"]
    cache_step = next(s for s in backend_steps if s.get("name") == "Cache HuggingFace model")
    with_block = cache_step["with"]
    assert "hashFiles" in with_block["key"], (
        "cache key is a fixed string — it can never self-heal from a "
        "poisoned/corrupted entry even after the pinned model/dependencies "
        "change"
    )
    assert with_block.get("restore-keys"), "no restore-keys fallback prefix set"


def test_docker_smoke_test_workflow_file_no_longer_exists_standalone():
    # A separate workflow file has no way to gate ci.yml's deploy job —
    # GitHub Actions `needs:` cannot cross workflow files. Folded into ci.yml
    # as the `docker-smoke` job instead (see the next two tests).
    assert not (REPO_ROOT / ".github" / "workflows" / "docker-smoke-test.yml").exists()


def test_deploy_job_depends_on_the_docker_smoke_job():
    jobs = _ci_jobs()
    assert "docker-smoke" in jobs, "the docker build+boot smoke test isn't a job in ci.yml"
    needs = jobs["deploy"]["needs"]
    assert "docker-smoke" in needs, (
        "deploy doesn't need docker-smoke, so a broken Docker build/boot "
        "still reaches `railway up`"
    )


def test_docker_smoke_boots_against_a_production_shaped_config():
    docker_smoke = _ci_jobs()["docker-smoke"]
    boot_step = next(s for s in docker_smoke["steps"] if s.get("name") == "Boot container")
    run = boot_step["run"]
    assert "SKILLPROOF_ENVIRONMENT=production" in run, (
        "smoke test still boots the permissive development config, never "
        "the production config Railway actually runs"
    )
    assert "SKILLPROOF_TOKEN_ENCRYPTION_KEY" in run

    services = docker_smoke.get("services", {})
    assert "postgres" in services, (
        "smoke test never runs against Postgres, so it can't catch anything "
        "that only breaks against production's actual database engine"
    )


def test_dependabot_covers_pip_npm_and_github_actions_weekly():
    doc = yaml.safe_load(DEPENDABOT_YML.read_text(encoding="utf-8"))
    ecosystems = {u["package-ecosystem"]: u for u in doc["updates"]}
    for name in ("pip", "npm", "github-actions"):
        assert name in ecosystems, f"no dependabot config for the {name} ecosystem"
        assert ecosystems[name]["schedule"]["interval"] == "weekly"


@pytest.mark.skipif(shutil.which("docker") is None, reason="requires a docker daemon")
def test_dockerignore_excludes_a_nested_env_file_from_the_build_context():
    # Docker's .dockerignore matching is NOT gitignore-style: a bare pattern
    # like `.env` only matches that exact path at the root of the build
    # context, not `frontend/.env` — unlike git, which treats a slash-free
    # pattern as matching at any depth. Verified against the real docker
    # daemon rather than a hand-rolled matcher, since e.g. Python's fnmatch
    # doesn't reproduce Docker's `**` semantics either (it requires a literal
    # `/` in the path, so it disagrees with Docker on whether `**/.env`
    # matches a root-level `.env`).
    ignore_text = DOCKERIGNORE.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / ".dockerignore").write_text(ignore_text, encoding="utf-8")
        (tmp_path / "Dockerfile").write_text("FROM alpine:3.20\nCOPY . /ctx\n", encoding="utf-8")
        (tmp_path / ".env").write_text("root-secret", encoding="utf-8")
        nested = tmp_path / "frontend"
        nested.mkdir()
        (nested / ".env").write_text("nested-secret", encoding="utf-8")
        (nested / ".env.local").write_text("nested-local-secret", encoding="utf-8")

        tag = "skillproof-dockerignore-regression-test"
        subprocess.run(
            ["docker", "build", "-t", tag, "-q", str(tmp_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        try:
            result = subprocess.run(
                ["docker", "run", "--rm", tag, "find", "/ctx", "-iname", "*.env*"],
                check=True,
                capture_output=True,
                text=True,
            )
            leaked = result.stdout.strip()
            assert leaked == "", f"env file(s) leaked into the build context: {leaked}"
        finally:
            subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)
