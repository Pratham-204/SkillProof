from skillproof import manifest_parsing


def test_parse_npm_covers_all_dependency_sections():
    content = """
    {
      "dependencies": {"react": "^18.0.0"},
      "devDependencies": {"eslint": "^8.0.0"},
      "peerDependencies": {"react-dom": "^18.0.0"},
      "optionalDependencies": {"fsevents": "^2.0.0"}
    }
    """
    assert manifest_parsing.parse_npm(content) == {"react", "eslint", "react-dom", "fsevents"}


def test_parse_npm_ignores_malformed_json():
    assert manifest_parsing.parse_npm("not json") == set()


def test_parse_pip_requirements_strips_version_specifiers_and_comments():
    content = "requests>=2.31,<3\nflask==2.3.0  # web framework\n-r other.txt\n\n# a comment\nnumpy\n"
    assert manifest_parsing.parse_pip_requirements(content) == {"requests", "flask", "numpy"}


def test_parse_pyproject_toml_covers_pep621_and_poetry_dependencies():
    content = """
    [project]
    dependencies = ["httpx>=0.27", "pydantic"]

    [tool.poetry.dependencies]
    python = "^3.11"
    rich = "^13.0"
    """
    assert manifest_parsing.parse_pyproject_toml(content) == {"httpx", "pydantic", "rich"}


def test_parse_pyproject_toml_ignores_malformed_toml():
    assert manifest_parsing.parse_pyproject_toml("not [ valid toml") == set()


def test_parse_pyproject_toml_does_not_raise_when_project_is_not_a_table():
    # Valid TOML: "project" is a plain string, not the table the parser expects.
    assert manifest_parsing.parse_pyproject_toml('project = "myproject"\n') == set()


def test_parse_pyproject_toml_does_not_raise_for_array_of_tables_project():
    # Valid TOML: [[project]] makes data["project"] a list, not a dict.
    assert manifest_parsing.parse_pyproject_toml("[[project]]\nname = \"x\"\n") == set()


def test_parse_pyproject_toml_does_not_raise_when_tool_poetry_is_not_a_table():
    assert manifest_parsing.parse_pyproject_toml('tool = "not-a-table"\n') == set()


def test_parse_pipfile_covers_packages_and_dev_packages():
    content = """
    [packages]
    requests = "*"

    [dev-packages]
    pytest = "*"
    """
    assert manifest_parsing.parse_pipfile(content) == {"requests", "pytest"}


def test_parse_composer_excludes_php_and_extensions():
    content = """
    {
      "require": {"php": ">=8.1", "ext-json": "*", "guzzlehttp/guzzle": "^7.0"},
      "require-dev": {"phpunit/phpunit": "^10.0"}
    }
    """
    assert manifest_parsing.parse_composer(content) == {"guzzlehttp/guzzle", "phpunit/phpunit"}


def test_parse_pip_requirements_extracts_name_from_egg_fragment():
    content = "git+https://github.com/org/repo.git@v1.0#egg=mypkg\nrequests==2.31\n"
    assert manifest_parsing.parse_pip_requirements(content) == {"mypkg", "requests"}


def test_parse_pip_requirements_extracts_name_from_pep508_direct_reference():
    content = "mypkg @ git+https://github.com/org/repo.git@main\n"
    assert manifest_parsing.parse_pip_requirements(content) == {"mypkg"}


def test_parse_pip_requirements_skips_bare_url_with_no_extractable_name():
    content = "https://example.com/packages/mypkg-1.0-py3-none-any.whl\nrequests==2.31\n"
    assert manifest_parsing.parse_pip_requirements(content) == {"requests"}


def test_parse_gemfile_extracts_gem_declarations():
    content = 'source "https://rubygems.org"\n\ngem "rails", "~> 7.0"\ngem \'sidekiq\'\n'
    assert manifest_parsing.parse_gemfile(content) == {"rails", "sidekiq"}


def test_parse_mix_exs_extracts_deps_tuples():
    content = """
    defp deps do
      [
        {:phoenix, "~> 1.7"},
        {:ecto_sql, "~> 3.10"}
      ]
    end
    """
    assert manifest_parsing.parse_mix_exs(content) == {"phoenix", "ecto_sql"}


def test_parse_mix_exs_ignores_commented_out_dependency():
    content = """
    defp deps do
      [
        {:phoenix, "~> 1.7"},
        # {:old_dep, "~> 0.5"},
        {:ecto_sql, "~> 3.10"}
      ]
    end
    """
    assert manifest_parsing.parse_mix_exs(content) == {"phoenix", "ecto_sql"}


def test_parse_pubspec_excludes_flutter_sdk_entries():
    content = """
    dependencies:
      flutter:
        sdk: flutter
      http: ^0.13.0
    dev_dependencies:
      flutter_test:
        sdk: flutter
      build_runner: ^2.4.0
    """
    assert manifest_parsing.parse_pubspec(content) == {"http", "build_runner"}


def test_parse_pom_xml_extracts_artifact_ids():
    content = """<?xml version="1.0"?>
    <project>
      <dependencies>
        <dependency>
          <groupId>org.springframework</groupId>
          <artifactId>spring-core</artifactId>
        </dependency>
      </dependencies>
    </project>
    """
    assert manifest_parsing.parse_pom_xml(content) == {"spring-core"}


def test_parse_pom_xml_ignores_malformed_xml():
    assert manifest_parsing.parse_pom_xml("<not><valid") == set()


_POM_WITH_PARENT_AND_PLUGINS = """<?xml version="1.0"?>
<project>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.0</version>
  </parent>
  <artifactId>my-app</artifactId>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-core</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
"""


def test_parse_pom_xml_excludes_parent_and_plugin_artifact_ids():
    assert manifest_parsing.parse_pom_xml(_POM_WITH_PARENT_AND_PLUGINS) == {"spring-core"}


def test_parse_pom_xml_excludes_parent_and_plugin_artifact_ids_with_namespace():
    namespaced = _POM_WITH_PARENT_AND_PLUGINS.replace(
        "<project>", '<project xmlns="http://maven.apache.org/POM/4.0.0">'
    )
    assert manifest_parsing.parse_pom_xml(namespaced) == {"spring-core"}


def test_extract_declared_packages_returns_none_for_unregistered_filename():
    assert manifest_parsing.extract_declared_packages("setup.py", "anything") is None


def test_extract_declared_packages_dispatches_by_filename():
    ecosystem, names = manifest_parsing.extract_declared_packages("package.json", '{"dependencies": {"lodash": "*"}}')
    assert ecosystem == "npm"
    assert names == {"lodash"}


def test_extract_declared_packages_does_not_raise_for_none_content():
    # GitHub's contents API returns no `content` for a manifest over 1MB, a
    # directory, or a submodule — the real caller filters that out today, but
    # the "never raises" contract must hold even if a future caller doesn't.
    assert manifest_parsing.extract_declared_packages("package.json", None) == ("npm", set())
    assert manifest_parsing.extract_declared_packages("pom.xml", None) == ("maven", set())
