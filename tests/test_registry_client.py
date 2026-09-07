"""RealRegistryClient interpolates a Sighting's candidate-controlled package_name
(a manifest dependency key) straight into a registry lookup URL. Unencoded, this
lets a crafted name either be resolved to a different, unintended path by URL
dot-segment/fragment handling (B6) or crash on a raw control character, since
`httpx.InvalidURL` isn't a subclass of the `httpx.HTTPError` these call sites
catch (B21).
"""

import httpx

from skillproof.registry_client import RealRegistryClient, _gem_url, _npm_url, _pip_url


def test_exists_never_lets_a_dot_segment_resolve_to_a_different_package(monkeypatch):
    """`lodash/../../left-pad` must not be sent as a request that resolves to
    `/left-pad` — that would confirm existence of a package that was never
    actually the one checked."""
    captured = {}

    def fake_get(url, timeout=None):
        captured["raw_path"] = httpx.URL(url).raw_path
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "get", fake_get)

    RealRegistryClient().exists("npm", "lodash/../../left-pad")

    assert captured["raw_path"] != b"/left-pad"


def test_exists_does_not_crash_on_a_control_character_in_the_package_name(monkeypatch):
    """A raw '\\n' in the built URL makes httpx's own request construction raise
    `InvalidURL`, which `except httpx.HTTPError` does not catch."""

    def fake_get(url, timeout=None):
        httpx.URL(url)  # mirrors the validation httpx.get itself performs
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "get", fake_get)

    assert RealRegistryClient().exists("npm", "pkg\nname") is False


def test_npm_url_percent_encodes_a_fragment_delimiter():
    url = _npm_url("lodash#fake-suffix")

    assert httpx.URL(url).fragment == ""
    assert "fake-suffix" in url


def test_pip_url_percent_encodes_a_query_delimiter():
    url = _pip_url("lodash?x=1")

    assert httpx.URL(url).query == b""


def test_gem_url_percent_encodes_a_path_separator():
    url = _gem_url("lodash/../left-pad")

    assert httpx.URL(url).raw_path == b"/api/v1/gems/lodash%2F..%2Fleft-pad.json"


def test_npm_url_still_reaches_the_real_registry_for_a_scoped_package():
    """Scoped npm names (`@scope/name`) legitimately contain '/' — npm's own
    registry accepts it percent-encoded, so encoding must not silently break
    every scoped-package lookup."""
    url = _npm_url("@angular/core")

    assert url == "https://registry.npmjs.org/%40angular%2Fcore"
