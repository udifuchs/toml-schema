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

# Set to True to generate the errors.txt files instead of comparing againt them:
WRITE_ERROR_FILES = False


def list_toml_files() -> Generator[tuple[toml_schema.Table, pathlib.Path]]:
    """Generate a list of TOML files to test."""
    schema = toml_schema.from_file("schemastore/pyproject.schema.toml")

    if not WRITE_ERROR_FILES:  # pragma: no branch
        yield schema, pathlib.Path("pyproject.toml")

        yield schema, pathlib.Path("examples/python-packaging-guide/pyproject.toml")

        for path in pathlib.Path("examples/schemastore/pyproject").glob("**/*.toml"):
            if str(path) in (
                "examples/schemastore/pyproject/uv-sample-project.toml",
                "examples/schemastore/pyproject/local-version-pep440.toml",
            ):
                continue  # TOML files that are failing require further investigation.
            yield schema, path

        for path in pathlib.Path("examples/validate-pyproject").glob("**/*.toml"):
            yield schema, path

    for path in pathlib.Path("examples/schemastore-negative-test").glob("**/*.toml"):
        if str(path) in (
            "examples/schemastore-negative-test/pyproject/cibuildwheel-bad-override.toml",
            "examples/schemastore-negative-test/pyproject/pep639-mismatch.toml",
            "examples/schemastore-negative-test/pyproject/poetry-source-2.toml",
            "examples/schemastore-negative-test/pyproject/mypy-emptymodule.toml",
            "examples/schemastore-negative-test/pyproject/dynamic-version-specified.toml",
            "examples/schemastore-negative-test/pyproject/poetry-plugin-dotenv-example-1.toml",
            "examples/schemastore-negative-test/pyproject/poetry-source-3.toml",
            "examples/schemastore-negative-test/pyproject/version-unspecified.toml",
        ):
            continue
        yield schema, path

    for path in pathlib.Path("examples/validate-pyproject-invalid").glob("**/*.toml"):
        if str(path) in (
            "examples/validate-pyproject-invalid/pep735/not-pep508.toml",
            "examples/validate-pyproject-invalid/store/cibw-overrides-noaction.toml",
            "examples/validate-pyproject-invalid/localtool/fail2.toml",
            "examples/validate-pyproject-invalid/localtool/fail1.toml",
            "examples/validate-pyproject-invalid/simple/pep639.toml",
            "examples/validate-pyproject-invalid/cibuildwheel/overrides-noaction.toml",
            "examples/validate-pyproject-invalid/setuptools/attr/missing-attr-name.toml",
            "examples/validate-pyproject-invalid/setuptools/dependencies/invalid-extra-name.toml",
            "examples/validate-pyproject-invalid/setuptools/cmdclass/invalid-value.toml",
            "examples/validate-pyproject-invalid/setuptools/package-dir/invalid-name.toml",
            "examples/validate-pyproject-invalid/setuptools/packages/invalid-stub-name.toml",
            "examples/validate-pyproject-invalid/setuptools/packages/invalid-name.toml",
            "examples/validate-pyproject-invalid/pep621/dynamic/static_entry_points_listed_as_dynamic.toml",
            "examples/validate-pyproject-invalid/pep621/missing-fields/missing-version.toml",
            "examples/validate-pyproject-invalid/pep621/missing-fields/empty-author.toml",
            "examples/validate-pyproject-invalid/pep621/missing-fields/missing-version-with-dynamic.toml",
            "examples/validate-pyproject-invalid/pep621/pep639/bothstyles.toml",
        ):
            continue
        yield schema, path


@pytest.mark.parametrize(("schema", "filepath"), list_toml_files())
def test_pyproject(schema: toml_schema.Table, filepath: pathlib.Path) -> None:
    """Validate a TOML file."""
    with filepath.open("rb") as toml_file:
        toml_table: dict[str, toml_schema.TOMLValue] = tomllib.load(toml_file)
    err_filepath = filepath.with_suffix(".errors.txt")
    if WRITE_ERROR_FILES:  # pragma: no cover
        with pytest.raises(toml_schema.SchemaError) as exc_info:
            schema.validate(toml_table)
        with err_filepath.open("w") as err_file:
            err_file.write(f"{exc_info.value}\n")
    elif err_filepath.exists():
        with err_filepath.open() as err_file:
            err_text = err_file.read()[:-1]
        with pytest.raises(toml_schema.SchemaError) as exc_info:
            schema.validate(toml_table)
        assert str(exc_info.value) == err_text
    else:
        schema.validate(toml_table)
