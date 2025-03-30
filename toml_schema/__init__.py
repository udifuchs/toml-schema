"""toml-schema: TOML Obvious Minimal Schema."""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 Udi Fuchs

from ._toml_schema import SchemaError, Table, TOMLValue, from_toml_table, load, loads

__version__ = "0.1-dev"

__all__ = (
    "SchemaError",
    "TOMLValue",
    "Table",
    "__version__",
    "from_toml_table",
    "load",
    "loads",
)
