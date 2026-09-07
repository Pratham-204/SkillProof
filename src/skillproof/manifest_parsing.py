"""Extracts declared package names from a manifest file's raw content, per ecosystem.

Scoped to the ecosystems the taxonomy's Detection Patterns already reference (see
`taxonomy.known_manifest_package_names`) — round 8's decision to start self-extension
with existing coverage rather than a broader first slice. A manifest filename with no
registered parser here (e.g. `setup.py`, `Package.swift`) simply contributes no
Sightings; that's not an error, just a format this pass doesn't parse.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable
from xml.etree import ElementTree

import yaml

_VERSION_SPECIFIER = re.compile(r"[<>=!~\[;].*")


def _strip_version(requirement: str) -> str:
    """'requests>=2.31,<3' -> 'requests'; also drops inline comments and extras."""
    return _VERSION_SPECIFIER.split(requirement, 1)[0].strip()


def parse_npm(content: str) -> set[str]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    names: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            names.update(section.keys())
    return names


_VCS_URL_PREFIXES = ("git+", "hg+", "svn+", "bzr+", "http://", "https://")


def _vcs_or_url_package_name(line: str) -> str | None:
    """The real package name for a VCS/direct-URL requirement line lives in an
    '#egg=' fragment or, for a PEP 508 'name @ url' direct reference, in the
    token before ' @ ' — never in the URL itself. Naive '#'-comment-stripping
    would destroy the '#egg=' fragment, and the version-stripping regex has
    nothing in a bare URL to split on, so this must run before either."""
    if "#egg=" in line:
        return line.split("#egg=", 1)[1].split("&", 1)[0].strip() or None
    if " @ " in line:
        return line.split(" @ ", 1)[0].strip() or None
    return None


def parse_pip_requirements(content: str) -> set[str]:
    names: set[str] = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(_VCS_URL_PREFIXES) or " @ " in line:
            name = _vcs_or_url_package_name(line)
            if name:
                names.add(name)
            continue
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = _strip_version(line)
        if name:
            names.add(name)
    return names


def parse_pyproject_toml(content: str) -> set[str]:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return set()
    names: set[str] = set()
    project = data.get("project", {})
    # [[project]] array-of-tables or a top-level `project = "..."` both parse
    # fine as TOML but leave `project` a list/str, not the table this expects.
    dependencies = project.get("dependencies", []) if isinstance(project, dict) else []
    for dep in dependencies:
        name = _strip_version(dep)
        if name:
            names.add(name)
    tool = data.get("tool", {})
    poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
    poetry_deps = poetry.get("dependencies", {}) if isinstance(poetry, dict) else {}
    if isinstance(poetry_deps, dict):
        names.update(k for k in poetry_deps if k.lower() != "python")
    return names


def parse_pipfile(content: str) -> set[str]:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return set()
    names: set[str] = set()
    for section in ("packages", "dev-packages"):
        section_data = data.get(section)
        if isinstance(section_data, dict):
            names.update(section_data.keys())
    return names


def parse_composer(content: str) -> set[str]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    names: set[str] = set()
    for key in ("require", "require-dev"):
        section = data.get(key)
        if isinstance(section, dict):
            names.update(section.keys())
    names.discard("php")
    return {n for n in names if not n.startswith("ext-")}


def parse_gemfile(content: str) -> set[str]:
    return set(re.findall(r"""^\s*gem\s+['"]([^'"]+)['"]""", content, re.MULTILINE))


def parse_mix_exs(content: str) -> set[str]:
    return set(re.findall(r"""^\s*\{:(\w+)\s*,""", content, re.MULTILINE))


def parse_pubspec(content: str) -> set[str]:
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        return set()
    if not isinstance(data, dict):
        return set()
    names: set[str] = set()
    for section in ("dependencies", "dev_dependencies"):
        section_data = data.get(section)
        if isinstance(section_data, dict):
            names.update(section_data.keys())
    names.discard("flutter")
    names.discard("flutter_test")
    return names


def parse_pom_xml(content: str) -> set[str]:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return set()
    # Scoped to <dependencies><dependency><artifactId> only (the "{*}" wildcard
    # matches any namespace, including a namespaced pom.xml's default xmlns) —
    # this excludes <parent>, <build>/<reporting> plugins, and the project's own
    # top-level <artifactId>, while still covering <dependencyManagement>, whose
    # <dependencies> is reachable by the same descendant search.
    return {
        el.text.strip()
        for el in root.findall(".//{*}dependencies/{*}dependency/{*}artifactId")
        if el.text and el.text.strip()
    }


_PARSERS_BY_FILENAME: dict[str, tuple[str, Callable[[str], set[str]]]] = {
    "package.json": ("npm", parse_npm),
    "requirements.txt": ("pip", parse_pip_requirements),
    "pyproject.toml": ("pip", parse_pyproject_toml),
    "Pipfile": ("pip", parse_pipfile),
    "Gemfile": ("gem", parse_gemfile),
    "composer.json": ("composer", parse_composer),
    "mix.exs": ("hex", parse_mix_exs),
    "pubspec.yaml": ("pub", parse_pubspec),
    "pom.xml": ("maven", parse_pom_xml),
}


def extract_declared_packages(filename: str, content: str | None) -> tuple[str, set[str]] | None:
    """(ecosystem, declared package names) for a manifest filename this module knows
    how to parse, or None for one it doesn't. Never raises — malformed content for a
    known filename yields an empty set, not an exception. `content` is None for the
    shape GitHub's contents API returns for a manifest over 1MB, a directory, or a
    submodule — guarded here once rather than in each of the 9 parsers below."""
    entry = _PARSERS_BY_FILENAME.get(filename)
    if entry is None:
        return None
    ecosystem, parser = entry
    if content is None:
        return ecosystem, set()
    return ecosystem, parser(content)
