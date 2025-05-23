"""toml-schema: TOML Obvious Minimal Schema."""
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 Udi Fuchs

import dataclasses
import datetime
import pathlib
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
            return f'"{_type_name(self.__class__)}"'

        non_def_str = ", ".join(
            f"{field.name} = {_format_attr(cast(object, getattr(self, field.name)))}"
            for field in non_default
        )
        return f'"{_type_name(self.__class__)} = {{ {non_def_str} }}"'

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for this type."""
        raise NotImplementedError

    def register_root(self, root: "Table") -> None:
        """Register the root table of this element."""
        if not hasattr(self, "ref"):
            return
        self_ref: Optional[str] = self.ref
        if self_ref is None:
            return
        schema: SchemaElement = root
        base_key = ""
        for key in self_ref.split("."):
            base_key = key if base_key == "" else f"{base_key}.{key}"
            if not isinstance(schema, Table):
                raise SchemaError(
                    f"Reference to non-existing sub-key: {base_key}", self._address
                )
            next_schema = schema.get_sub_schema(key, get_hidden=True)
            if next_schema is None:
                raise SchemaError(
                    f"Reference to non-existing key: {base_key}", self._address
                )
            schema = next_schema
        object.__setattr__(self, "_ref_schema", schema)


# TOML bare key chars copied from: cpython/Lib/tomllib/_parser.py
# fmt: off
BARE_KEY_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz" "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "0123456789" "-_"
)
# fmt: on


def _str_field_required() -> str:
    """Make sure that dataclass field is always specified.

    Once python 3.9 support is dropped, SchemaElement._address can be marked as kw_only,
    making this function redundant.
    """
    raise ValueError("Required field missing.")  # pragma: no cover


def _list_str_field_required() -> list[str]:
    raise ValueError("Required field missing.")  # pragma: no cover


def _int_field_required() -> int:
    raise ValueError("Required field missing.")  # pragma: no cover


def _bool_field_required() -> bool:
    raise ValueError("Required field missing.")  # pragma: no cover


@dataclasses.dataclass(frozen=True)
class SchemaKey(SchemaElement):
    """Schema for table keys."""

    name: str = dataclasses.field(default_factory=_str_field_required)
    required: bool = False
    hidden: bool = False
    pattern: Optional[str] = None
    ref: Optional[str] = None
    union: Optional[str] = None
    _regex: Optional[re.Pattern[str]] = dataclasses.field(init=False, default=None)
    _ref_schema: Optional[SchemaElement] = dataclasses.field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.name == "*":
            object.__setattr__(self, "name", "pattern")
            object.__setattr__(self, "pattern", "^.*$")
            if self.required:
                raise SchemaError(
                    "Wildcard key '*' cannot be marked as required.", self._address
                )

        if self.pattern is not None:
            if self.name != "pattern":
                raise SchemaError(
                    f"'{self}': Pattern key must be 'pattern'.", self._address
                )
            try:
                regex: re.Pattern[str] = re.compile(self.pattern)
            except re.error as ex:
                raise SchemaError(
                    f"Key pattern '{self.pattern}': {ex}", self._address
                ) from None
            object.__setattr__(self, "_regex", regex)

    def __str__(self) -> str:
        if self.required:
            key_str = self._toml_key_name().replace('"', '\\"')
            return f'"{key_str} = {{ required = {_format_attr(self.required)} }}"'
        if self.hidden:
            key_str = self._toml_key_name().replace('"', '\\"')
            return f'"{key_str} = {{ hidden = {_format_attr(self.hidden)} }}"'
        if self.pattern is not None:
            return f'''"pattern = '{self.pattern}'"'''
        if self.ref is not None:
            return f'''"ref = '{self.ref}'"'''
        return self._toml_key_name()

    def special_match(self, value: str) -> bool:
        """Check if value matches with wildcard or reference key."""
        if self._regex is not None:
            result = self._regex.match(value)
            return result is not None
        if self._ref_schema is not None:
            if not isinstance(value, str):
                return False
            try:
                self._ref_schema.validate(value, context="N/A")
            except SchemaError:
                return False
            else:
                return True
        return False

    def _toml_key_name(self) -> str:
        """Quote TOML key when needed."""
        if all(char in BARE_KEY_CHARS for char in self.name):
            # self.name is a bare key.
            return self.name
        escape_quotes = self.name.replace('"', '\\"')
        return f'"{escape_quotes}"'


@dataclasses.dataclass(frozen=True)
class String(SchemaElement):
    """String schema type."""

    min_len: Optional[int] = None
    max_len: Optional[int] = None

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for string type."""
        if type(value) is not str:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)
        if self.min_len is not None and len(value) < self.min_len:
            raise SchemaError(f"len({value!r}) < {self.min_len}", context)
        if self.max_len is not None and len(value) > self.max_len:
            raise SchemaError(f"len({value!r}) > {self.max_len}", context)


@dataclasses.dataclass(frozen=True)
class Enum(SchemaElement):
    """Enumerated string schema type."""

    enum: list[str] = dataclasses.field(default_factory=_list_str_field_required)

    def __post_init__(self) -> None:
        if any(
            sum(1 for elem_2 in self.enum if elem_1 == elem_2) > 1
            for elem_1 in self.enum
        ):
            raise SchemaError(
                f"'enum' must not have duplicates: {self.enum}", self._address
            )

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for string type."""
        if type(value) is not str:
            raise SchemaError(f"Value {_format_attr(value)} is not a string.", context)
        if value not in self.enum:
            if len(str(self.enum)) > 80:
                # No point showing enum if it is very long:
                raise SchemaError(f"'{value}' not in enum.", context)
            raise SchemaError(f"'{value}' not in: {self.enum}", context)


@dataclasses.dataclass(frozen=True)
class Pattern(SchemaElement):
    """Regular expression pattern for string schema type."""

    pattern: str = dataclasses.field(default_factory=_str_field_required)
    _regex: re.Pattern[str] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        try:
            regex: re.Pattern[str] = re.compile(self.pattern)
        except re.error as ex:
            raise SchemaError(
                f"String pattern '{self.pattern}': {ex}", self._address
            ) from None
        object.__setattr__(self, "_regex", regex)

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for pattern type."""
        if type(value) is not str:
            raise SchemaError(f"Value {_format_attr(value)} is not a string.", context)
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


class OffsetDateTime(SchemaElement):
    """Offset date-time schema type."""

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value for offset date-time type."""
        if type(value) is not datetime.datetime:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)
        local_time = value.utcoffset() is None
        if local_time:
            raise SchemaError(f"'offset-date-time' has no offset: {value}", context)


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


class Table(SchemaElement, dict[SchemaKey, SchemaElement]):
    """Table schema container."""

    def __init__(
        self,
        schema_table: Mapping[SchemaKey, SchemaElement],
        /,
        *,
        toml_filename: Optional[str] = None,
        is_root: bool,
        _address: str = "",
    ) -> None:
        SchemaElement.__init__(self, _address=_address)
        dict.__init__(self, schema_table)

        self.toml_filename = toml_filename
        if is_root:
            self.register_root(self)
        elif toml_filename is not None:  # pragma: no cover
            raise RuntimeError("toml_filename should only be specified if is_root.")

        key_count = {
            str(key_1): sum(
                1
                for key_2 in self
                if key_1.name == key_2.name
                and key_1.pattern == key_2.pattern
                and key_1.hidden == key_2.hidden
            )
            for key_1 in self
        }
        if any(count > 1 for count in key_count.values()):
            raise SchemaError(
                "Duplicate keys in table: "
                f"{[str(key) for key, count in key_count.items() if count > 1]}",
                self._address,
            )

    def register_root(self, root: "Table") -> None:
        for schema_key, schema_value in self.items():
            schema_key.register_root(root)
            schema_value.register_root(root)

    def __str__(self) -> str:
        values = [f"{key} = {value}" for key, value in self.items()]
        return "{ }" if len(values) == 0 else f"{{ {', '.join(values)} }}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Table):
            return False
        return SchemaElement.__eq__(self, other) and dict.__eq__(self, other)

    def get_sub_schema(
        self, key: str, *, get_hidden: bool = False
    ) -> Optional[SchemaElement]:
        """Get the schema for the specified key."""
        if get_hidden:  # Hidden keys are retrieved before visible ones.
            for schema_key, schema_value in self.items():
                if (
                    schema_key.hidden
                    and key == schema_key.name
                    and schema_key.pattern is None
                ):
                    return schema_value
        for schema_key, schema_value in self.items():
            if not get_hidden and schema_key.hidden:
                continue
            if key == schema_key.name and schema_key.pattern is None:
                return schema_value
        return None

    def validate(self, value: TOMLValue, /, *, context: str = "") -> None:
        """Validate table and its elements."""
        if type(value) is not dict:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)
        for key, element in value.items():
            # Check if key is in schema:
            schema = self.get_sub_schema(key)
            if schema is None:
                # Check if key matches any wildcard or reference schema key:
                for schema_key, schema_value in self.items():
                    if schema_key.special_match(key):
                        schema = schema_value
                        break
                else:
                    if len(str(self)) > 80:
                        # No point showing schema if it is very long:
                        raise SchemaError(f"Key '{key}' not in schema.", context)
                    raise SchemaError(f"Key '{key}' not in schema: {self}", context)

            key_context = key if context == "" else f"{context}.{key}"
            schema.validate(element, context=key_context)

        for schema_key in self:
            if schema_key.required and schema_key.name not in value:
                raise SchemaError(f"Missing required key: {schema_key.name}", context)


@dataclasses.dataclass(frozen=True)
class Ref(SchemaElement):
    """Schema for referencing other schema keys."""

    ref: str = dataclasses.field(default_factory=_str_field_required)
    _ref_schema: Optional[SchemaElement] = dataclasses.field(init=False, default=None)

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value with the reference type."""
        if self._ref_schema is None:  # pragma: no cover
            # If this exception is reached there is a bug in Table's register_root:
            raise RuntimeError(f"'{self._address}': _ref_schema is None.")
        self._ref_schema.validate(value, context=context)


@dataclasses.dataclass(frozen=True)
class File(SchemaElement):
    """Schema for referencing other schema files."""

    file: str = dataclasses.field(default_factory=_str_field_required)
    _ref_schema: Optional[SchemaElement] = dataclasses.field(init=False, default=None)

    def register_root(self, root: Table) -> None:
        if root.toml_filename is None:
            raise SchemaError(
                "Schema has file reference. Must specify TOML filename.", self._address
            )
        toml_path = pathlib.Path(root.toml_filename).parent
        try:
            schema = from_file(str(toml_path / self.file))
        except (SchemaError, tomllib.TOMLDecodeError, OSError) as ex:
            raise SchemaError(
                f"Error reading '{self.file}': {ex}", self._address
            ) from None
        object.__setattr__(self, "_ref_schema", schema)

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate value with the reference schema file."""
        if self._ref_schema is None:
            # If this exception is reached there is a bug in Table's register_root:
            raise RuntimeError(
                f"'{self._address}': _ref_schema is None."
            )  # pragma: no cover
        self._ref_schema.validate(value, context=context)


@dataclasses.dataclass(frozen=True)
class MinItems(SchemaElement):
    """Schema for min-items option in arrays."""

    min_items: int = dataclasses.field(default_factory=_int_field_required)
    _array_option: bool = True


@dataclasses.dataclass(frozen=True)
class MaxItems(SchemaElement):
    """Schema for max-items option in arrays."""

    max_items: int = dataclasses.field(default_factory=_int_field_required)
    _array_option: bool = True


@dataclasses.dataclass(frozen=True)
class UniqueItems(SchemaElement):
    """Schema for unique-items option in arrays."""

    unique_items: bool = dataclasses.field(default_factory=_bool_field_required)
    _array_option: bool = True


class Array(SchemaElement, list[SchemaElement]):
    """Array schema container."""

    def __init__(
        self,
        schema_list: Sequence[SchemaElement],
        /,
        *,
        _address: str = "",
    ) -> None:
        SchemaElement.__init__(self, _address=_address)
        list.__init__(self, schema_list)

        options_count = sum(1 for schema in self if hasattr(schema, "_array_option"))
        if len(self) - options_count == 0:
            raise SchemaError("Empty array not allowed in schema.", _address)
        if len(self) - options_count > 1:
            raise SchemaError(
                "More than one element not allowed in array schema.", _address
            )

    def register_root(self, root: Table) -> None:
        for schema_value in self:
            schema_value.register_root(root)

    def __str__(self) -> str:
        schemas = [str(schema) for schema in self]
        return f"[ {', '.join(schemas)} ]"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Array):
            return False
        return SchemaElement.__eq__(self, other) and list.__eq__(self, other)

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate array and its elements."""
        if type(value) is not list:
            raise SchemaError(f"Value {_format_attr(value)} is not: {self}", context)
        for schema in self:
            if isinstance(schema, MinItems):
                if len(value) < schema.min_items:
                    raise SchemaError(
                        f"Array has less than {schema.min_items} items.", context
                    )
            elif isinstance(schema, MaxItems):
                if len(value) > schema.max_items:
                    raise SchemaError(
                        f"Array has more than {schema.max_items} items.", context
                    )
            elif isinstance(schema, UniqueItems):
                if schema.unique_items and any(
                    sum(1 for elem_2 in value if elem_1 == elem_2) > 1
                    for elem_1 in value
                ):
                    raise SchemaError("Array has duplicate values.", context)
            else:
                for index, element in enumerate(value):
                    schema.validate(element, context=f"{context}[{index}]")


class Union(SchemaElement, list[SchemaElement]):
    """Union schema container."""

    def __init__(
        self,
        mode: str,
        schema_list: Sequence[SchemaElement],
        /,
        *,
        _address: str = "",
    ) -> None:
        SchemaElement.__init__(self, _address=_address)
        list.__init__(self, schema_list)
        self.mode = mode

        if any(sum(1 for elem_2 in self if elem_1 == elem_2) > 1 for elem_1 in self):
            raise SchemaError("Union must not have duplicates.", _address)
        if len(self) < 2 and self.mode != "none":
            raise SchemaError("Union should contain at least 2 type options.", _address)
        if any(isinstance(value, AnyValue) for value in self):
            raise SchemaError("'any-value' cannot be part of a union schema.", _address)

    def register_root(self, root: Table) -> None:
        for schema_value in self:
            schema_value.register_root(root)

    def __str__(self) -> str:
        schemas = [str(schema) for schema in self]
        return f"""{{ union = [ {", ".join(schemas)} ] }}"""

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Union):
            return False
        return all(element in other for element in self) and len(self) == len(other)

    def validate(self, value: TOMLValue, /, *, context: str) -> None:
        """Validate union type."""
        # For union do not call super().
        valid_count = 0
        for schema_option in self:
            try:
                schema_option.validate(value, context=context)
            except SchemaError:  # noqa: PERF203
                if self.mode == "none":
                    return
            else:
                if self.mode == "any":
                    return
                valid_count += 1

        if self.mode == "one" and valid_count == 1:
            return
        if self.mode == "all" and valid_count == len(self):
            return
        error_message = (
            "not"
            if self.mode == "any"
            else "does not match all"
            if self.mode == "all"
            else "does not match exactly one"
            if self.mode == "one"
            else "does not match none"  # if self.mode == "none"
        )
        if len(str(self)) > 80:
            # No point showing union if it is very long:
            raise SchemaError(f"Value {value} {error_message} in union.", context)
        raise SchemaError(f"Value {value} {error_message} in: {self}", context)


def _create_key(key: str, _address: str) -> SchemaKey:
    if "=" not in key:  # Key is certainly not a TOML string.
        if key == "union":
            return SchemaKey(name=key, union="any", _address=_address)
        return SchemaKey(name=key, _address=_address)

    try:
        key_toml: dict[str, TOMLValue] = tomllib.loads(key)
    except tomllib.TOMLDecodeError as ex:
        raise SchemaError(f"'{key}' is not a valid TOML: {ex}", _address) from None

    KEY_SCHEMA.validate(key_toml, context=_address)

    if len(key_toml) != 1:
        key_str = key.replace("\n", "\\n")
        raise SchemaError(f"'{key_str}' must have a single key.", _address)
    # Get key name.
    key_name = next(iter(key_toml))

    # It is not possible to static check the call parameters typing.
    # But the key schema validation guarantees the typing dynamically.
    return SchemaKey(
        name=key_name,
        _address=_address,
        **(
            key_toml  # For example: {"pattern": "^[a-z]*$"}
            if isinstance(key_toml[key_name], str)
            else key_toml[key_name]  # For example: {"name": {"required": True}}
        ),  # type: ignore[arg-type]
    )


def _create_schema_basic_type(toml_type: str, _address: str) -> SchemaElement:
    if "=" not in toml_type:  # toml_type is certainly not a TOML string.
        # Loops ONLY over direct subclasses of SchemaElement:
        for type_class in SchemaElement.__subclasses__():
            if (
                _type_name(type_class) == toml_type
                and toml_type in TYPES_SCHEMA_TABLE
                and isinstance(TYPES_SCHEMA_TABLE[toml_type], dict)
            ):
                return type_class(_address=_address)  # optionless types like "string".
        raise SchemaError(f"'{toml_type}' is not a valid keyword type.", _address)

    return _create_schema_from_toml_string(toml_type, _address, TYPES_SCHEMA)


def _create_schema_from_toml_string(
    toml_type: str, _address: str, types_schema: Table
) -> SchemaElement:
    try:
        toml_type_toml: dict[str, TOMLValue] = tomllib.loads(toml_type)
    except tomllib.TOMLDecodeError as ex:
        raise SchemaError(
            f"'{toml_type}' is not a valid type: {ex}", _address
        ) from None

    try:
        types_schema.validate(toml_type_toml, context="")
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
            if isinstance(toml_type_toml[type_name], dict):
                # Table option, for example: "integer = { min = 0, max = 255 }"
                type_dict = cast(dict[str, TOMLValue], toml_type_toml[type_name])
            else:
                # Key-value option, for example: "pattern = '^[a-z]*$'"
                type_dict = toml_type_toml

            type_params: dict[str, TOMLValue] = {
                key.replace("-", "_"): value for key, value in type_dict.items()
            }
            return type_class(_address=_address, **type_params)

    # The schema validation guarantees that this exception would never be reached:
    raise RuntimeError(
        f"'{_address}': '{toml_type}' is not a valid type."
    )  # pragma: no cover


def _create_schema(toml_value: TOMLValue, _address: str) -> SchemaElement:
    if isinstance(toml_value, dict):
        schema_keys = [_create_key(key, _address) for key in toml_value]
        if any(key.union is not None for key in schema_keys):
            if len(toml_value) != 1:
                raise SchemaError(
                    "Union table must contain exactly one element.", _address
                )
            toml_union = next(iter(toml_value.values()))
            if not isinstance(toml_union, list):
                raise SchemaError("Union value must be a list.", _address)
            # Create schema union:
            schema_union = [
                _create_schema(value, _address=f"{_address}[{index}]")
                for index, value in enumerate(toml_union)
            ]
            union_mode = cast(str, schema_keys[0].union)
            return Union(union_mode, schema_union, _address=_address)

        # Create schema table:
        return from_toml_table(toml_value, is_root=False, _address=_address)

    if isinstance(toml_value, list):
        # Create schema array:
        schema_list = [
            _create_schema_in_array(value, _address=f"{_address}[{index}]")
            for index, value in enumerate(toml_value)
        ]
        return Array(schema_list, _address=_address)

    if isinstance(toml_value, str):
        # Create schema basic type:
        return _create_schema_basic_type(toml_value, _address)

    raise SchemaError(f"Schema type '{toml_value}' not a string.", _address)


def _create_schema_in_array(toml_value: TOMLValue, _address: str) -> SchemaElement:
    if isinstance(toml_value, str) and "=" in toml_value:
        # toml_value is assumed to be a TOML string.
        try:
            return _create_schema_from_toml_string(
                toml_value, _address, ARRAY_TYPES_SCHEMA
            )
        except SchemaError:
            pass
    return _create_schema(toml_value, _address)


def from_toml_table(
    toml_table: dict[str, TOMLValue],
    /,
    *,
    toml_filename: Optional[str] = None,
    is_root: bool = True,
    _address: str = "",
) -> Table:
    """Create a schema table from a TOML table."""
    base_address = "" if _address == "" else f"{_address}."
    schema_table = {
        _create_key(key, _address): _create_schema(
            value, _address=f"{base_address}{key}"
        )
        for key, value in toml_table.items()
    }
    if any(key.union is not None for key in schema_table):
        raise SchemaError("'union' cannot be a schema key", _address)
    return Table(
        schema_table, toml_filename=toml_filename, is_root=is_root, _address=_address
    )


TYPES_SCHEMA_TABLE: dict[str, TOMLValue] = {
    "string": {"min-len": "integer", "max-len": "integer"},
    "enum": ["string"],
    "pattern": "string",
    "float": {"min": "float", "max": "float"},
    "integer": {"min": "integer", "max": "integer"},
    "boolean": {},
    "offset-date-time": {},
    "local-date-time": {},
    "date": {},
    "time": {},
    "any-value": {},
    "ref": "string",
    "file": "string",
}

TYPES_SCHEMA = from_toml_table(TYPES_SCHEMA_TABLE)

ARRAY_TYPES_SCHEMA_TABLE: dict[str, TOMLValue] = {
    "min-items": "integer",
    "max-items": "integer",
    "unique-items": "boolean",
}

ARRAY_TYPES_SCHEMA = from_toml_table(ARRAY_TYPES_SCHEMA_TABLE)

KEY_SCHEMA_TABLE: dict[str, TOMLValue] = {
    "pattern": {
        "union": [
            "string",
            {"required": "boolean"},
        ]
    },
    "ref": {
        "union": [
            "string",
            {"required": "boolean"},
        ]
    },
    # The "union" key requires a workaround:
    # union = { "union" = [
    #     "enum = [ 'any', 'all', 'one', 'none' ]",
    #     {"required": "boolean"},
    # ] }
    # Any key can be marked as required or hidden:
    "*": {
        "union": [
            {"required": "boolean"},
            {"hidden": "boolean"},
        ]
    },
}

KEY_SCHEMA = from_toml_table(KEY_SCHEMA_TABLE)
# Work around the fact that "union" cannot be a schema key:
KEY_SCHEMA[SchemaKey(name="union")] = Union(
    "any",
    [
        Enum(enum=["any", "all", "one", "none"]),
        Table({SchemaKey(name="required"): Boolean()}, is_root=False),
    ],
)


def from_file(toml_filename: str) -> Table:
    with pathlib.Path(toml_filename).open("rb") as toml_file:
        return load(toml_file, toml_filename=toml_filename)


def load(toml_file: BinaryIO, /, *, toml_filename: Optional[str] = None) -> Table:
    """Load TOML schema from a binary I/O stream."""
    toml_table: dict[str, TOMLValue] = tomllib.load(toml_file)
    return from_toml_table(toml_table, toml_filename=toml_filename)


def loads(toml_str: str, /, *, toml_filename: Optional[str] = None) -> Table:
    """Load TOML schema from a string."""
    toml_table: dict[str, TOMLValue] = tomllib.loads(toml_str)
    return from_toml_table(toml_table, toml_filename=toml_filename)
