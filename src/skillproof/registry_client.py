"""Confirms a Sighting's package is a real, published one — the first guard in
`taxonomy_growth.publish_new_skill_tags`, run before any LLM call (round 8, ADR-0008).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx


class RegistryClient(ABC):
    @abstractmethod
    def exists(self, ecosystem: str, package_name: str) -> bool: ...


def _npm_url(name: str) -> str:
    return f"https://registry.npmjs.org/{name}"


def _pip_url(name: str) -> str:
    return f"https://pypi.org/pypi/{name}/json"


def _gem_url(name: str) -> str:
    return f"https://rubygems.org/api/v1/gems/{name}.json"


def _composer_url(name: str) -> str:
    return f"https://repo.packagist.org/p2/{name}.json"


def _hex_url(name: str) -> str:
    return f"https://hex.pm/api/packages/{name}"


def _pub_url(name: str) -> str:
    return f"https://pub.dev/api/packages/{name}"


_LOOKUP_URL_BY_ECOSYSTEM: dict[str, Callable[[str], str]] = {
    "npm": _npm_url,
    "pip": _pip_url,
    "gem": _gem_url,
    "composer": _composer_url,
    "hex": _hex_url,
    "pub": _pub_url,
}


class RealRegistryClient(RegistryClient):
    """Maven has no single-name lookup — coordinates are `groupId:artifactId`, and
    only `artifactId` survives `manifest_parsing.parse_pom_xml` — so it uses Maven
    Central's search API as a best-effort existence check instead of an exact
    registry GET."""

    def exists(self, ecosystem: str, package_name: str) -> bool:
        if ecosystem == "maven":
            return self._maven_exists(package_name)
        url_builder = _LOOKUP_URL_BY_ECOSYSTEM.get(ecosystem)
        if url_builder is None:
            return False
        try:
            response = httpx.get(url_builder(package_name), timeout=10)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def _maven_exists(self, artifact_id: str) -> bool:
        try:
            response = httpx.get(
                "https://search.maven.org/solrsearch/select",
                params={"q": f"a:{artifact_id}", "rows": 1, "wt": "json"},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()["response"]["numFound"] > 0
        except (httpx.HTTPError, KeyError, ValueError):
            return False


@dataclass
class FakeRegistryClient(RegistryClient):
    """Test double: a fixed set of (ecosystem, package_name) pairs that exist."""

    known: set[tuple[str, str]] = field(default_factory=set)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def exists(self, ecosystem: str, package_name: str) -> bool:
        self.calls.append((ecosystem, package_name))
        return (ecosystem, package_name) in self.known
