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


def parse_pip_requirements(content: str) -> set[str]:
    names: set[str] = set()
    for line in content.splitlines():
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
    for dep in data.get("project", {}).get("dependencies", []):
        name = _strip_version(dep)
        if name:
            names.add(name)
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
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
    return set(re.findall(r"\{:(\w+)\s*,", content))


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
    return {el.text.strip() for el in root.iter() if el.tag.endswith("artifactId") and el.text and el.text.strip()}


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


def extract_declared_packages(filename: str, content: str) -> tuple[str, set[str]] | None:
    """(ecosystem, declared package names) for a manifest filename this module knows
    how to parse, or None for one it doesn't. Never raises — malformed content for a
    known filename yields an empty set, not an exception."""
    entry = _PARSERS_BY_FILENAME.get(filename)
    if entry is None:
        return None
    ecosystem, parser = entry
    return ecosystem, parser(content)
