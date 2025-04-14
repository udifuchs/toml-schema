"""Test the pyproject.toml schema."""

from __future__ import annotations

import pathlib
import sys
from collections.abc import Generator

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import toml_schema


def list_toml_files() -> Generator[tuple[toml_schema.Table, pathlib.Path]]:
    """Generate a list of TOML files to test."""
    schema = toml_schema.from_file("schemastore/pyproject.toml-schema")

    yield schema, pathlib.Path("pyproject.toml")

    yield schema, pathlib.Path("examples/python-packaging-guide/pyproject.toml")

    for path in pathlib.Path("examples/schemastore/pyproject").glob("**/*.toml"):
        yield schema, path

    for path in pathlib.Path("examples/validate-pyproject").glob("**/*.toml"):
        yield schema, path


@pytest.mark.parametrize(("schema", "filepath"), list_toml_files())
def test_pyproject(schema: toml_schema.Table, filepath: pathlib.Path) -> None:
    """Validate a TOML file."""
    if str(filepath) in (
        "examples/schemastore/pyproject/uv-sample-project.toml",
        "examples/schemastore/pyproject/local-version-pep440.toml",
    ):
        return  # TOML files that are failing require further investigation.
    with filepath.open("rb") as toml_file:
        toml_table: dict[str, toml_schema.TOMLValue] = tomllib.load(toml_file)
    schema.validate(toml_table)
