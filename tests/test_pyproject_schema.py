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

from validate_pyproject import formats

import toml_schema
from toml_schema._toml_schema import Ref

# Set to True to generate the errors.txt files instead of comparing againt them:
WRITE_ERROR_FILES = False

# The following is a method to handle special checks for "ref = 'format.*'" strings.
# It works by monkey-patching the Ref.validate method.

# This example uses the functions in validate_project.formats for the special checks.
# For example,  "ref = 'format.python-module-name-relaxed'" is checked with
# the function: validate_project.formats.format.python_module_name_relaxed

ref_original_validate = Ref.validate


def ref_validate(self: Ref, value: toml_schema.TOMLValue, /, *, context: str) -> None:
    """Validate format references using validate_pyproject.formats."""
    ref_original_validate(self, value, context=context)
    if self.ref.startswith("format."):
        ref_format = self.ref.split(".", 2)[1]
        if ref_format in ("email", "uri"):
            return
        ref_format = ref_format.replace("-", "_")
        check: bool = getattr(formats, ref_format)(value)
        if not check:
            raise toml_schema.SchemaError(f"Invalid format {self.ref}", context)


Ref.validate = ref_validate  # type: ignore[method-assign]


def list_toml_files() -> Generator[tuple[toml_schema.Table, pathlib.Path]]:
    """Generate a list of TOML files to test."""
    schema = toml_schema.from_file("schemastore/pyproject.schema.toml")

    if not WRITE_ERROR_FILES:  # pragma: no branch
        yield schema, pathlib.Path("pyproject.toml")

        yield schema, pathlib.Path("examples/python-packaging-guide/pyproject.toml")

        for path in pathlib.Path("examples/schemastore/pyproject").glob("**/*.toml"):
            yield schema, path

        for path in pathlib.Path("examples/validate-pyproject").glob("**/*.toml"):
            yield schema, path

    for path in pathlib.Path("examples/schemastore-negative-test").glob("**/*.toml"):
        if not WRITE_ERROR_FILES and str(path) in (
            "examples/schemastore-negative-test/pyproject/cibuildwheel-bad-override.toml",
            "examples/schemastore-negative-test/pyproject/pep639-mismatch.toml",
            "examples/schemastore-negative-test/pyproject/dynamic-version-specified.toml",
            "examples/schemastore-negative-test/pyproject/version-unspecified.toml",
        ):
            continue
        yield schema, path

    for path in pathlib.Path("examples/validate-pyproject-invalid").glob("**/*.toml"):
        if not WRITE_ERROR_FILES and str(path) in (
            "examples/validate-pyproject-invalid/pep735/not-pep508.toml",
            "examples/validate-pyproject-invalid/store/cibw-overrides-noaction.toml",
            "examples/validate-pyproject-invalid/localtool/fail2.toml",
            "examples/validate-pyproject-invalid/localtool/fail1.toml",
            "examples/validate-pyproject-invalid/simple/pep639.toml",
            "examples/validate-pyproject-invalid/cibuildwheel/overrides-noaction.toml",
            "examples/validate-pyproject-invalid/setuptools/dependencies/invalid-extra-name.toml",
            "examples/validate-pyproject-invalid/setuptools/cmdclass/invalid-value.toml",
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
        try:
            schema.validate(toml_table)
        except toml_schema.SchemaError as ex:
            with err_filepath.open("w") as err_file:
                err_file.write(f"{ex}\n")
    elif err_filepath.exists():
        with err_filepath.open() as err_file:
            err_text = err_file.read()[:-1]
        with pytest.raises(toml_schema.SchemaError) as exc_info:
            schema.validate(toml_table)
        assert str(exc_info.value) == err_text
    else:
        schema.validate(toml_table)
