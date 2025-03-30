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

from . import SchemaError, TOMLValue, __version__, load


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
        with pathlib.Path(settings.schema_file).open("rb") as schema_file:
            schema_table = load(schema_file)
        with pathlib.Path(settings.toml_file).open("rb") as toml_file:
            toml_table: dict[str, TOMLValue] = tomllib.load(toml_file)
        schema_table.validate(toml_table)
        print("TOML schema validated.")
    except (SchemaError, FileNotFoundError) as ex:
        print(str(ex), file=sys.stderr)
        raise SystemExit(1) from ex


if __name__ == "__main__":
    main()
