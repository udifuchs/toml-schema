"""toml-schema: TOML Obvious Minimal Schema."""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 Udi Fuchs

import argparse
import pathlib
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from . import SchemaError, TOMLValue, __version__, from_file


class Settings:
    """Settings from command line arguments."""

    schema_file: str
    toml_file: str

    def __init__(self) -> None:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--version", action="version", version=f"toml-schema {__version__}"
        )
        parser.add_argument("schema_file")
        parser.add_argument("toml_file")
        parser.parse_args(namespace=self)


def main() -> None:
    """toml-schema main entry-point."""
    try:
        settings = Settings()
        try:
            schema_table = from_file(settings.schema_file)
        except tomllib.TOMLDecodeError as ex:
            print(f"Error reading '{settings.schema_file}': {ex}", file=sys.stderr)
            raise SystemExit(1) from ex
        try:
            with pathlib.Path(settings.toml_file).open("rb") as toml_file:
                toml_table: dict[str, TOMLValue] = tomllib.load(toml_file)
        except tomllib.TOMLDecodeError as ex:
            print(f"Error reading '{settings.toml_file}': {ex}", file=sys.stderr)
            raise SystemExit(1) from ex
        schema_table.validate(toml_table)
        print("TOML schema validated.")
    except (SchemaError, OSError) as ex:
        print(str(ex), file=sys.stderr)
        raise SystemExit(1) from ex


if __name__ == "__main__":
    main()
