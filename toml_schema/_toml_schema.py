"""toml-schema: TOML Obvious Minimal Schema."""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 Udi Fuchs

import dataclasses
import datetime
import re
import sys
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, BinaryIO, Optional, cast

if TYPE_CHECKING:
    from typing import TypeAlias

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

TOMLValue: "TypeAlias" = """(
    str | int | float | bool | datetime.datetime | datetime.date | datetime.time
    | list[TOMLValue] | dict[str, TOMLValue]
)"""


@dataclasses.dataclass
class SchemaError(Exception):
    """TOML Schema Error."""

    message: str
    context: str

    def __str__(self) -> str:
        context = "root" if self.context == "" else f"'{self.context}'"
        return f"{context}: {self.message}"


def _type_name(cls: type) -> str:
    """Generate type name from class name."""
    cls_name = cls.__name__
    # Replace capitalized words with hyphens:
    return re.sub(r"([a-z])([A-Z])", r"\1-\2", cls_name).lower()


def _format_attr(attr: object) -> str:
    if isinstance(attr, bool):
        return str(attr).lower()
    return str(attr)


@dataclasses.dataclass(frozen=True)
class SchemaElement:
    """Base class for schema elements."""

    required: bool = False
    _address: str = dataclasses.field(default="", compare=False)

    def __str__(self) -> str:
        # Omit default fields in object string representation. Based on:
        # https://stackoverflow.com/questions/72161257/exclude-default-fields-from-python-dataclass-repr
        fields: tuple[dataclasses.Field[object], ...] = dataclasses.fields(self)
        non_default = [
            field
            for field in fields
            if cast(object, getattr(self, field.name)) != field.default
            and not field.name.startswith("_")
        ]
        if len(non_default) == 0:
            return f"{_type_name(self.__class__)}"

        non_def_str = ", ".join(
            f"{field.name} = {_format_attr(cast(object, getattr(self, field.name)))}"
            for field in non_default
        )
        return f"{_type_name(self.__class__)} = {{ {non_def_str} }}"

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for this type."""
        raise NotImplementedError


@dataclasses.dataclass(frozen=True)
class String(SchemaElement):
    """String schema type."""

    tokens: Optional[list[str]] = None
    pattern: Optional[str] = None
    _regex: Optional[re.Pattern[str]] = dataclasses.field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.pattern is not None:
            try:
                regex: re.Pattern[str] = re.compile(self.pattern)
            except re.error as ex:
                raise SchemaError(f"String pattern: {ex}", self._address) from None
            object.__setattr__(self, "_regex", regex)

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for string type."""
        if type(value) is not str:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)
        if self.tokens is not None and value not in self.tokens:
            raise SchemaError(f"'{value}' not in {self.tokens}", context)
        if self._regex is not None:
            result = self._regex.match(value)
            if result is None:
                raise SchemaError(
                    f"'{value}' does not match pattern: {self.pattern}", context
                )


@dataclasses.dataclass(frozen=True)
class Float(SchemaElement):
    """Float schema type."""

    min: Optional[float] = None
    max: Optional[float] = None

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for float type."""
        if type(value) is not float:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)
        if self.min is not None and value < self.min:
            raise SchemaError(f"Value out of range: {value} < {self.min}", context)
        if self.max is not None and value > self.max:
            raise SchemaError(f"Value out of range: {value} > {self.max}", context)


@dataclasses.dataclass(frozen=True)
class Integer(SchemaElement):
    """Integer schema type."""

    min: Optional[int] = None
    max: Optional[int] = None

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for integer type."""
        if type(value) is not int:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)
        if self.min is not None and value < self.min:
            raise SchemaError(f"Value out of range: {value} < {self.min}", context)
        if self.max is not None and value > self.max:
            raise SchemaError(f"Value out of range: {value} > {self.max}", context)


class Boolean(SchemaElement):
    """Boolean schema type."""

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for boolean type."""
        if type(value) is not bool:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)


@dataclasses.dataclass(frozen=True)
class OffsetDateTime(SchemaElement):
    """Offset date-time schema type."""

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for offset date-time type."""
        if type(value) is not datetime.datetime:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)
        local_time = value.utcoffset() is None
        if local_time:
            raise SchemaError(f"'offset-date-time' has no offset: {value}", context)


@dataclasses.dataclass(frozen=True)
class LocalDateTime(SchemaElement):
    """Local date-time schema type."""

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for local date-time type."""
        if type(value) is not datetime.datetime:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)
        local_time = value.utcoffset() is None
        if not local_time:
            raise SchemaError(f"'local-date-time' is not local: {value}", context)


class Date(SchemaElement):
    """Date schema type."""

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for local date type."""
        if type(value) is not datetime.date:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)


class Time(SchemaElement):
    """Time schema type."""

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for local time type."""
        if type(value) is not datetime.time:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)


class AnyValue(SchemaElement):
    """Wildcard schema type."""

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validating value for any-value type is always successful."""


class Union(SchemaElement):
    """A marker for a union of TOML schema types."""


class Options(SchemaElement):
    """A marker for options in TOML schema containers."""


# TOML bare key chars copied from: cpython/Lib/tomllib/_parser.py
# fmt: off
BARE_KEY_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz" "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "0123456789" "-_"
)
# fmt: on


def _is_bare_key(key: str) -> bool:
    """Test if key is a valid TOML bare key."""
    return all(char in BARE_KEY_CHARS for char in key)


def toml_key_to_str(key: str) -> str:
    """Quote TOML key when needed."""
    if _is_bare_key(key):
        return key
    escape_quotes = key.replace('"', '\\"')
    return f'"{escape_quotes}"'


def schema_value_to_str(value: SchemaElement) -> str:
    """Non-container values in TOML schema are quoted strings."""
    if isinstance(value, (Table, Array, UnionContainer)):
        return str(value)
    return f'"{value}"'


class Table(SchemaElement, dict[str, SchemaElement]):
    """Table schema container."""

    def __init__(
        self,
        schema_table: Mapping[str, SchemaElement],
        /,
        *,
        required: bool = False,
        _address: str = "",
    ) -> None:
        SchemaElement.__init__(self, required=required, _address=_address)
        dict.__init__(self, schema_table)
        if "*" in self and self["*"].required:
            raise SchemaError(
                "Wildcard key '*' cannot be marked as required.", _address
            )
        keys = [
            repr(key) for key, schema in self.items() if isinstance(schema, Options)
        ]
        if len(keys) > 0:
            raise SchemaError(
                f"Options in table schema must use '_' key, not: {', '.join(keys)}",
                _address,
            )

    def __str__(self) -> str:
        values = [
            f"{toml_key_to_str(key)} = {schema_value_to_str(value)}"
            for key, value in self.items()
        ]
        if self.required:
            values.append('"_" = "options = { required = true }"')
        return "{ }" if len(values) == 0 else f"{{ {', '.join(values)} }}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Table):
            return False
        return SchemaElement.__eq__(self, other) and dict.__eq__(self, other)

    def validate(self, value: TOMLValue, /, *, context: str = "") -> None:
        """Validate table and its elements."""
        if type(value) is not dict:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)
        for key, element in value.items():
            if key in self:
                schema = self[key]
            elif "*" in self:
                schema = self["*"]
            else:
                raise SchemaError(f"Key '{key}' not in schema: {self}", context)

            key_context = key if context == "" else f"{context}.{key}"
            schema.validate(element, context=key_context)

        for key, schema in self.items():
            if schema.required is True and key not in value:
                raise SchemaError(f"Missing required key: {key}", context)


class Array(SchemaElement, list[SchemaElement]):
    """Array schema container."""

    def __init__(
        self,
        schema_list: Sequence[SchemaElement],
        /,
        *,
        required: bool = False,
        _address: str = "",
    ) -> None:
        SchemaElement.__init__(self, required=required, _address=_address)
        list.__init__(self, schema_list)

        if len(self) == 0:
            raise SchemaError("Empty array not allowed in schema.", _address)
        if any(isinstance(schema, Union) for schema in schema_list):
            raise SchemaError(
                "'union' must be first element in array schema.", _address
            )
        if any(isinstance(schema, Options) for schema in self):
            raise SchemaError("'options' must be last element in array.", _address)
        if len(self) > 1:
            raise SchemaError(
                "More than one element not allowed in array schema.", _address
            )

    def __str__(self) -> str:
        schemas = [schema_value_to_str(schema) for schema in self]
        if self.required:
            schemas.append('"options = { required = true }"')
        return f"[ {', '.join(schemas)} ]"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Array):
            return False
        return SchemaElement.__eq__(self, other) and list.__eq__(self, other)

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate array and its elements."""
        if type(value) is not list:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)
        schema = self[0]
        for index, element in enumerate(value):
            schema.validate(element, context=f"{context}[{index}]")


class UnionContainer(SchemaElement, list[SchemaElement]):
    """Union schema container."""

    def __init__(
        self,
        schema_list: Sequence[SchemaElement],
        /,
        *,
        required: bool = False,
        _address: str = "",
    ) -> None:
        SchemaElement.__init__(self, required=required, _address=_address)
        list.__init__(self, schema_list)

        if any(sum(1 for elem_2 in self if elem_1 == elem_2) > 1 for elem_1 in self):
            raise SchemaError("Union must not have duplicates.", _address)
        if any(isinstance(schema, Union) for schema in self):
            raise SchemaError(
                "'union' must only be first element in array schema.", _address
            )
        if any(isinstance(schema, Options) for schema in self):
            raise SchemaError("'options' must be last element in union.", _address)
        if len(self) < 2:
            raise SchemaError("Union should contain at least 2 type options.", _address)
        if any(isinstance(value, AnyValue) for value in self):
            raise SchemaError("'any-value' cannot be part of a union schema.", _address)

    def __str__(self) -> str:
        schemas = [schema_value_to_str(schema) for schema in self]
        if self.required:
            schemas.append('"options = { required = true }"')
        return f"""[ "union", {", ".join(schemas)} ]"""

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UnionContainer):
            return False
        if not SchemaElement.__eq__(self, other):
            return False
        return all(element in other for element in self) and len(self) == len(other)

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate union type."""
        # For union do not call super().
        for schema_option in self:
            try:
                schema_option.validate(value, context=context)
            except SchemaError:  # noqa: PERF203
                pass
            else:
                return
        raise SchemaError(f"Value {value} not in {self}.", context)


def _create_schema_basic_type(toml_type: str, _address: str) -> SchemaElement:
    if _is_bare_key(toml_type):
        # Loops ONLY over direct subclasses of SchemaElement:
        for type_class in SchemaElement.__subclasses__():
            if _type_name(type_class) == toml_type and toml_type in TYPES_SCHEMA_TABLE:
                return type_class(_address=_address)  # optionless types like "string".
        raise SchemaError(f"'{toml_type}' is not a valid keyword type.", _address)

    try:
        toml_type_toml: dict[str, TOMLValue] = tomllib.loads(toml_type)
    except tomllib.TOMLDecodeError as ex:
        raise SchemaError(
            f"'{toml_type}' is not a valid type: {ex}", _address
        ) from None

    try:
        TYPES_SCHEMA.validate(toml_type_toml, context="")
    except SchemaError as ex:
        raise SchemaError(f"'{toml_type}' schema error: {ex}", _address) from None

    if len(toml_type_toml) != 1:
        toml_type_str = toml_type.replace("\n", "\\n")
        raise SchemaError(f"'{toml_type_str}' must have a single key.", _address)
    # Get type name. For "Float = { min = 3.3' }" it would be "Float".
    type_name = next(iter(toml_type_toml))

    # Loops ONLY over direct subclasses of SchemaElement:
    for type_class in SchemaElement.__subclasses__():
        if _type_name(type_class) == type_name:
            # It is not possible to static check the call parameters typing.
            # But the types schema validation guarantees the typing dynamically.
            return type_class(
                _address=_address,
                **toml_type_toml[type_name],  # type: ignore[arg-type]
            )

    # The schema validation guarantees that this exception would never be reached:
    raise RuntimeError(
        f"'{_address}': '{toml_type}' is not a valid type."
    )  # pragma: no cover


def _create_schema(toml_value: TOMLValue, _address: str) -> SchemaElement:
    if isinstance(toml_value, dict):
        # Create schema table:
        return from_toml_table(toml_value, _address=_address)

    if isinstance(toml_value, list):
        # Create array or union schema:
        schema_list = [
            _create_schema(value, _address=f"{_address}[{index}]")
            for index, value in enumerate(toml_value)
        ]
        for schema in schema_list:
            if schema.required is True and not isinstance(schema, Options):
                raise SchemaError(
                    f"Required values not allowed in array: {schema}", _address
                )

        required = False
        if len(schema_list) > 0 and isinstance(schema_list[-1], Options):
            required = schema_list[-1].required
            schema_list.pop(-1)

        if len(schema_list) > 0 and isinstance(schema_list[0], Union):
            return UnionContainer(schema_list[1:], required=required, _address=_address)

        return Array(schema_list, required=required, _address=_address)

    if isinstance(toml_value, str):
        # Create schema basic type:
        return _create_schema_basic_type(toml_value, _address)

    raise SchemaError(f"Schema type '{toml_value}' not a string.", _address)


def from_toml_table(
    toml_table: dict[str, TOMLValue], /, *, _address: str = ""
) -> Table:
    """Create a schema table from a TOML table."""
    base_address = "" if _address == "" else f"{_address}."
    schema_table = {
        key: _create_schema(value, _address=f"{base_address}{key}")
        for key, value in toml_table.items()
    }
    required = False
    if "_" in schema_table and isinstance(schema_table["_"], Options):
        required = schema_table["_"].required
        del schema_table["_"]
    return Table(schema_table, required=required, _address=_address)


TYPES_SCHEMA_TABLE: dict[str, TOMLValue] = {
    "string": {"required": "boolean", "tokens": ["string"], "pattern": "string"},
    "float": {"required": "boolean", "min": "float", "max": "float"},
    "integer": {"required": "boolean", "min": "integer", "max": "integer"},
    "boolean": {"required": "boolean"},
    "offset-date-time": {"required": "boolean"},
    "local-date-time": {"required": "boolean"},
    "date": {"required": "boolean"},
    "time": {"required": "boolean"},
    "any-value": {"required": "boolean"},
    "options": {"required": "boolean"},
    "union": {},
}

TYPES_SCHEMA = from_toml_table(TYPES_SCHEMA_TABLE)


def load(toml_file: BinaryIO, /) -> Table:
    """Load TOML schema from a binary I/O stream."""
    toml_table: dict[str, TOMLValue] = tomllib.load(toml_file)
    return from_toml_table(toml_table)


def loads(toml_str: str, /) -> Table:
    """Load TOML schema from a string."""
    toml_table: dict[str, TOMLValue] = tomllib.loads(toml_str)
    return from_toml_table(toml_table)
