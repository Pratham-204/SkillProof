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


def test_extract_declared_packages_returns_none_for_unregistered_filename():
    assert manifest_parsing.extract_declared_packages("setup.py", "anything") is None


def test_extract_declared_packages_dispatches_by_filename():
    ecosystem, names = manifest_parsing.extract_declared_packages("package.json", '{"dependencies": {"lodash": "*"}}')
    assert ecosystem == "npm"
    assert names == {"lodash"}
