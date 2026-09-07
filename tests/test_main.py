"""Tests for main.py's SPA-serving routes, isolated from whatever real
frontend/dist build (or lack of one) happens to exist on the machine running
the suite — each test builds its own throwaway FRONTEND_DIST/LANDING_PAGE via
monkeypatch, so this is deterministic in CI (which never runs `npm run build`
before the backend job) and locally alike.
"""

from fastapi.testclient import TestClient

from skillproof import main


def _build_app(tmp_path, monkeypatch, *, with_landing: bool = False):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    (dist / "index.html").write_text("<html>spa shell</html>", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")

    # A sibling directory OUTSIDE dist, holding a file that must never be
    # servable through the SPA route — this is exactly what a traversal
    # payload targets (in production: .env, source, an encryption key file).
    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    (secret_dir / "top-secret.txt").write_text("SKILLPROOF_TOKEN_ENCRYPTION_KEY=do-not-leak", encoding="utf-8")

    monkeypatch.setattr(main, "FRONTEND_DIST", dist)
    if with_landing:
        (dist / "landing.html").write_text("<html>landing</html>", encoding="utf-8")
        monkeypatch.setattr(main, "LANDING_PAGE", dist / "landing.html")
    else:
        monkeypatch.setattr(main, "LANDING_PAGE", dist / "landing.html")  # deliberately absent

    app = main.create_app()
    return TestClient(app), secret_dir


def test_serve_frontend_returns_a_real_asset(tmp_path, monkeypatch):
    client, _ = _build_app(tmp_path, monkeypatch)

    response = client.get("/favicon.svg")

    assert response.status_code == 200
    assert response.text == "<svg></svg>"


def test_serve_frontend_falls_back_to_index_for_an_unknown_spa_route(tmp_path, monkeypatch):
    client, _ = _build_app(tmp_path, monkeypatch)

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert response.text == "<html>spa shell</html>"


def test_serve_frontend_rejects_a_relative_path_traversal_read(tmp_path, monkeypatch):
    """Real production incident, confirmed via live exploitation against the
    running app before this fix: `candidate = FRONTEND_DIST / full_path` with
    no containment check let `GET /../../.env` (or any `..`-laden path) read
    any file the container process could see — outside FRONTEND_DIST
    entirely. This must fall back to the SPA shell, not serve the file."""
    client, secret_dir = _build_app(tmp_path, monkeypatch)

    response = client.get("/../secret/top-secret.txt")

    assert response.status_code == 200
    assert response.text == "<html>spa shell</html>"
    assert "do-not-leak" not in response.text


def test_serve_frontend_rejects_a_percent_encoded_traversal_read(tmp_path, monkeypatch):
    """The same guard must hold for a percent-encoded '..' segment, not just a
    raw one — Starlette decodes the path before this handler ever sees it, so
    a payload sent as %2e%2e must be rejected the same way."""
    client, secret_dir = _build_app(tmp_path, monkeypatch)

    response = client.get("/%2e%2e/secret/top-secret.txt")

    assert response.status_code == 200
    assert response.text == "<html>spa shell</html>"
    assert "do-not-leak" not in response.text


def test_serve_landing_page_is_unaffected(tmp_path, monkeypatch):
    client, _ = _build_app(tmp_path, monkeypatch, with_landing=True)

    response = client.get("/")

    assert response.status_code == 200
    assert response.text == "<html>landing</html>"
