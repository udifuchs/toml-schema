"""Test functionality of toml-schema."""

import runpy
import sys
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import pytest

import toml_schema
import toml_schema._toml_schema as private_toml_schema


def SchemaKey(  # noqa: N802
    name: str, *, required: bool = False, pattern: Optional[str] = None
) -> private_toml_schema.SchemaKey:
    """Fake SchemaKey needed for python 3.9 compatibility.

    With python3.10 SchemaElement._address can be marked as kw_only.
    Then this function could be replaced with the line:
    from toml_schema._toml_schema import SchemaKey
    """
    return private_toml_schema.SchemaKey(name=name, required=required, pattern=pattern)


def schema_table_to_str(schema_table: toml_schema.Table) -> str:
    """Format a schema table into a TOML parsable string."""
    return "\n".join(f"{key} = {value}" for key, value in schema_table.items())


def test_create_schema() -> None:
    """Test create Schema class."""
    toml: dict[str, toml_schema.TOMLValue] = {
        "fruit": "string",
        "temperatures": ["float"],
    }
    schema = toml_schema.from_toml_table(toml)
    manual_schema = toml_schema.Table(
        {
            SchemaKey("fruit"): private_toml_schema.String(),
            SchemaKey("temperatures"): private_toml_schema.Array(
                [private_toml_schema.Float()]
            ),
        }
    )
    assert schema_table_to_str(schema) == schema_table_to_str(manual_schema)
    assert schema == manual_schema

    toml = {
        "fruit": "pattern = 'hello'",
        "temperatures = { required = true }": ["float = {}"],
    }
    schema = toml_schema.from_toml_table(toml)
    manual_schema = toml_schema.Table(
        {
            SchemaKey("fruit"): private_toml_schema.Pattern(pattern="hello"),
            SchemaKey("temperatures", required=True): private_toml_schema.Array(
                [private_toml_schema.Float()]
            ),
        },
    )
    assert schema_table_to_str(schema) == schema_table_to_str(manual_schema)
    assert schema == manual_schema

    toml = {
        "fruit": int,  # type: ignore[dict-item]
    }
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table(toml)
    assert str(exc_info.value) == "'fruit': Schema type '<class 'int'>' not a string."

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("apple = 'Table'")
    assert str(exc_info.value) == "'apple': 'Table' is not a valid keyword type."

    # Internal toml-schema schema for basic TOML types with parameters:
    types_schema_str = """\
        string = { }
        enum = [ "string" ]
        pattern = "string"
        float = { min = "float", max = "float" }
        integer = { min = "integer", max = "integer" }
        boolean = { }
        offset-date-time = { }
        local-date-time = { }
        date = { }
        time = { }
        any-value = { }
        union = { }"""
    schema = toml_schema.loads(types_schema_str)
    assert schema == private_toml_schema.TYPES_SCHEMA
    assert schema_table_to_str(schema) == types_schema_str.replace("        ", "")

    # Two schemas are equal even if their keys are ordered differently:
    assert toml_schema.loads("""
        apple = 'string'
        orange = 'string'
    """) == toml_schema.loads("""
        orange = 'string'
        apple = 'string'
    """)

    assert toml_schema.loads("""
        apple = ['string']
    """) != toml_schema.loads("""
        apple = ['boolean']
    """)

    assert toml_schema.loads("""
        apple = ['union', 'string', 'float']
    """) != toml_schema.loads("""
        apple = ['boolean']
    """)

    assert toml_schema.loads("""
        apple = ['union', 'string', 'float']
    """) == toml_schema.loads("""
        apple = ['union', 'string', 'float']
    """)

    assert toml_schema.loads("""
        apple = ['union', 'string', 'float']
    """) == toml_schema.loads("""
        apple = ['union', 'float', 'string']
    """)

    assert toml_schema.loads("""
        apple = ['union', 'string', 'boolean']
    """) != toml_schema.loads("""
        apple = ['union', 'float', 'string']
    """)


def check(
    schema_str: str,
    toml_str: str,
) -> None:
    """Check if a TOML formatted string matches a TOML schema."""
    schema_table = toml_schema.loads(schema_str)
    test_schema_to_str = toml_schema.loads(schema_table_to_str(schema_table))
    assert schema_table == test_schema_to_str
    toml_table: dict[str, toml_schema.TOMLValue] = tomllib.loads(toml_str)
    schema_table.validate(toml_table)


def test_toml_example() -> None:
    """Test the main TOML example at https://toml.io/."""
    toml = """
        title = "TOML Example"

        [owner]
        name = "Tom Preston-Werner"
        dob = 1979-05-27T07:32:00-08:00

        [database]
        enabled = true
        ports = [ 8000, 8001, 8002 ]
        data = [ ["delta", "phi"], [3.14] ]
        temp_targets = { cpu = 79.5, case = 72.0 }

        [servers]

        [servers.alpha]
        ip = "10.0.0.1"
        role = "frontend"

        [servers.beta]
        ip = "10.0.0.2"
        role = "backend"
    """
    schema = """
        title = "string"

        [owner]
        name = "string"
        dob = "offset-date-time"

        [database]
        enabled = "boolean"
        ports = [ "integer" ]
        data = [
            [
                # Each element can be an array of strings or an array of floats:
                "union",
                [ "string" ],
                [ "float" ]
            ]
        ]
        temp_targets = { cpu = "float", case = "float" }

        [servers."*"]
        ip = "string"
        role = "string"
    """
    check(schema, toml)


def test_doc_table_1() -> None:
    """Test table from TOML documentation."""
    toml = """
        name = "Orange"
        physical.color = "orange"
        physical.shape = "round"
        site."google.com" = true
    """
    schema = """
        name = "string"
        physical.color = "string"
        physical.shape = "string"
        site."*" = "boolean"
    """
    check(schema, toml)


def test_doc_table_2() -> None:
    """Test table from TOML documentation."""
    toml = """
        apple.type = "fruit"
        apple.skin = "thin"
        apple.color = "red"

        orange.type = "fruit"
        orange.skin = "thick"
        orange.color = "orange"
    """
    schema = """
        "*".type = "string"
        "*".skin = "string"
        "*".color = "string"
    """
    check(schema, toml)


def test_doc_subtable() -> None:
    """Test subtable from TOML documentation."""
    toml = """
        [fruit]
        apple.color = "red"
        apple.taste.sweet = true

        [fruit.apple.texture]
        smooth = true
    """
    schema = """
        [fruit]
        "*".color = "string"
        "*".taste.sweet = "boolean"

        [fruit."*".texture]
        smooth = "boolean"
    """
    check(schema, toml)


def test_doc_array() -> None:
    """Test array from TOML documentation."""
    toml = """
        integers = [ 1, 2, 3 ]
        colors = [ "red", "yellow", "green" ]
        nested_arrays_of_ints = [ [ 1, 2 ], [3, 4, 5] ]
        nested_mixed_array = [ [ 1, 2 ], ["a", "b", "c"] ]
        string_array = [ "all", 'strings', \"""are the same\""", '''type''' ]

        # Mixed-type arrays are allowed
        numbers = [ 0.1, 0.2, 0.5, 1, 2, 5 ]
        contributors = [
          "Foo Bar <foo@example.com>",
          { name = "Baz Qux", email = "bazqux@example.com", url = "https://example.com/bazqux"}
        ]
    """
    schema = """
        integers = [ "integer" ]
        colors = [ "string" ]
        nested_arrays_of_ints = [ [ "integer" ] ]
        nested_mixed_array = [
            [
                "union",
                [ "integer" ],
                [ "string" ]
            ]
        ]
        string_array = [ "string" ]

        numbers = [ [ "union", "float", "integer" ] ]
        contributors = [
            [
                "union",
                "string",
                { name = "string", email = "string", url = "string" }
            ]
        ]
    """
    check(schema, toml)


def test_doc_inline_table() -> None:
    """Test inline table from TOML documentation."""
    toml = """
        name = { first = "Tom", last = "Preston-Werner" }
        point = { x = 1, y = 2 }
        animal = { type.name = "pug" }
    """
    schema = """
        name = { first = "string", last = "string" }
        point = { x = "integer", y = "integer" }
        animal = { type.name = "string" }
    """
    check(schema, toml)


def test_doc_array_of_tables() -> None:
    """Test array of tables from TOML documentation."""
    toml = """
        [[fruits]]
        name = "apple"

        [fruits.physical]  # subtable
        color = "red"
        shape = "round"

        [[fruits.varieties]]  # nested array of tables
        name = "red delicious"

        [[fruits.varieties]]
        name = "granny smith"


        [[fruits]]
        name = "banana"

        [[fruits.varieties]]
        name = "plantain"
    """
    schema = """
        [[fruits]]
        name = "string"

        [fruits.physical]  # subtable
        color = "string"
        shape = "string"

        [[fruits.varieties]]  # nested array of tables
        name = "string"
    """
    check(schema, toml)


def test_doc_array_of_inline_tables() -> None:
    """Test array of inline tables from TOML documentation."""
    toml = """
        points = [ { x = 1, y = 2, z = 3 },
                   { x = 7, y = 8, z = 9 },
                   { x = 2, y = 4, z = 8 } ]
    """
    schema = """
        points = [ { x = "integer", y = "integer", z = "integer" } ]
    """
    check(schema, toml)

    toml = """
        points = [ { x = 1, y = 2, z = 3 },
                   { x = 1, y = 2, z = true } ]
    """
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        check(schema, toml)
    assert str(exc_info.value) == "'points[1].z': Value true is not: \"integer\""


def test_wildcard() -> None:
    """Test wildcard "*" being applied after keywords."""
    toml = r"""
        apple = "fruit"
        banana = 7
        "pine apple pen" = 8
        "pine'apple'pen" = 9
        'pine"apple"pen' = 10
        "pine'apple\"pen" = 11
    """
    schema = """
        "*" = "integer"
        "apple" = "string"
    """
    check(schema, toml)

    toml = """
        apple = 3
        banana = 7
    """
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        check(schema, toml)
    assert str(exc_info.value) == "'apple': Value 3 is not: \"string\""

    # Allowing wildcards in root table does not mean that other tables in schema
    # can have any key:
    toml = """
        apple.color = "Red"
        apple.taste = "Sweet"
        banana = 7
    """
    schema = """
        "apple" = { color = "string" }
        "*" = "any-value"
    """
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        check(schema, toml)
    assert (
        str(exc_info.value)
        == """'apple': Key 'taste' not in schema: { color = "string" }"""
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        check(schema, "apple = 'red'")
    assert str(exc_info.value) == """'apple': Value red is not: { color = "string" }"""


def test_tables() -> None:
    """Test handling of tables."""
    schema_1 = toml_schema.loads("""
        ["fruit = { required = true }"]
        "name = { required = true }" = "string"
    """)
    schema_2 = toml_schema.loads("""
        ["'fruit' = { required = true }"]
        "name = { required = true }" = "string = { }"
    """)
    assert schema_1 == schema_2
    assert str(schema_1) == str(schema_2)
    assert (
        str(schema_1) == '{ "fruit = { required = true }" = '
        '{ "name = { required = true }" = "string" } }'
    )

    schema_3 = toml_schema.loads("""
        ["'fruit' = { required = false }"]
        "name = { required = true }" = "string"
    """)
    schema_4 = toml_schema.loads("""
        [fruit]
        "name = { required = true }" = "string"
    """)
    assert schema_3 == schema_4
    assert str(schema_3) == str(schema_4)
    assert str(schema_3) == '{ fruit = { "name = { required = true }" = "string" } }'

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema_1.validate({})
    assert str(exc_info.value) == "root: Missing required key: fruit"
    schema_3.validate({})

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"apple = { banana = 'string' }": "string"})
    assert (
        str(exc_info.value) == "'apple': Key 'banana' not in schema: "
        """{ required = "boolean" }"""
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"apple = required = true": "string"})
    assert (
        str(exc_info.value) == "root: 'apple = required = true' is not a valid TOML: "
        "Invalid value (at line 1, column 9)"
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table(
            {"fruit": [{"apple = { banana = 'string' }": "string"}]}
        )
    assert (
        str(exc_info.value) == "'fruit[0].apple': Key 'banana' not in schema: "
        '{ required = "boolean" }'
    )


def test_arrays() -> None:
    """Test handling of arrays."""
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("'fruit' = []")
    assert str(exc_info.value) == "'fruit': Empty array not allowed in schema."

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("'fruit' = ['string', 'boolean']")
    assert (
        str(exc_info.value)
        == "'fruit': More than one element not allowed in array schema."
    )

    schema = toml_schema.loads("numbers = [ 'integer' ]")
    assert str(schema) == '{ numbers = [ "integer" ] }'

    schema_str = """
        "fruit = { required = true }" = [ "string" ]
    """
    toml_str = """
        fruit = []
    """
    check(schema_str, toml_str)


def test_union() -> None:
    """Test schema unions."""
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("number = ['float', 'integer', 'union']")
    assert (
        str(exc_info.value)
        == "'number': 'union' must be first element in array schema."
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("number = ['union', 'integer', 'float', 'union']")
    assert (
        str(exc_info.value)
        == "'number': 'union' must only be first element in array schema."
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("number = ['union']")
    assert (
        str(exc_info.value) == "'number': Union should contain at least 2 type options."
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("number = ['union', 'float']")
    assert (
        str(exc_info.value) == "'number': Union should contain at least 2 type options."
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("number = ['union', 'float', 'float']")
    assert str(exc_info.value) == "'number': Union must not have duplicates."

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("number = ['union', 'float', 'any-value']")
    assert (
        str(exc_info.value) == "'number': 'any-value' cannot be part of a union schema."
    )

    schema = toml_schema.loads("number = ['union = {}', 'float', 'integer']")
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"number": True})
    assert (
        str(exc_info.value)
        == """'number': Value True not in: [ "union", "float", "integer" ]"""
    )

    schema.validate({"number": 3})
    schema.validate({"number": 3.14})

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("number = 'union = { required = true }'")
    assert (
        str(exc_info.value) == "'number': 'union = { required = true }' schema error: "
        "'union': Key 'required' not in schema: { }"
    )

    schema_1 = toml_schema.loads(
        "'number = { required = true }' = [ 'union', 'float', 'integer' ]"
    )
    test_schema_to_str = toml_schema.loads(schema_table_to_str(schema_1))
    assert schema_1 == test_schema_to_str
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema_1.validate({})
    assert str(exc_info.value) == "root: Missing required key: number"

    schema_2 = toml_schema.loads(
        "'number = { required = false }' = [ 'union', 'float', 'integer' ]"
    )
    schema_3 = toml_schema.loads("'number' = [ 'union', 'float', 'integer' ]")
    assert schema_1 != schema_2
    assert schema_2 == schema_3

    schema = toml_schema.loads(
        "number = [ 'union', 'float', { 're' = 'float', 'im' = 'float' } ]"
    )
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"number": {"re": 3, "im": 4}})
    assert (
        str(exc_info.value) == "'number': Value {'re': 3, 'im': 4} not in: "
        """[ "union", "float", { re = "float", im = "float" } ]"""
    )
    schema.validate({"number": {"re": 3.3, "im": 4.4}})

    schema = toml_schema.loads("number = [ 'union', 'float', [ 'float' ] ]")
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"number": [3, 4]})
    assert (
        str(exc_info.value)
        == """'number': Value [3, 4] not in: [ "union", "float", [ "float" ] ]"""
    )
    schema.validate({"number": [3.3, 4.4, 5.5]})


def test_check_error() -> None:
    """Test errors raised during check."""
    toml = """
        apple.type = "fruit"
    """
    schema = """
        "banana" = "string"
    """
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        check(schema, toml)
    assert (
        str(exc_info.value)
        == """root: Key 'apple' not in schema: { banana = "string" }"""
    )

    schema = """
        "*" = "string"
    """
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        check(schema, toml)
    assert str(exc_info.value) == "'apple': Value {'type': 'fruit'} is not: \"string\""

    toml = """
        apple = ["fruit"]
    """
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        check(schema, toml)
    assert str(exc_info.value) == "'apple': Value ['fruit'] is not: \"string\""

    toml = """
        apple = true
    """
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        check(schema, toml)
    assert str(exc_info.value) == "'apple': Value true is not: \"string\""

    schema = """
        apple = [ "string" ]
    """
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        check(schema, toml)
    assert str(exc_info.value) == """'apple': Value true is not: [ "string" ]"""

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"*": "string"}).validate(
            {"apple": None}  # type: ignore[dict-item]
        )
    assert str(exc_info.value) == "'apple': Value None is not: \"string\""

    schema = """
        "*" = "table"
    """
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        check(schema, toml)
    assert str(exc_info.value) == "'*': 'table' is not a valid keyword type."

    schema = """
        "*" = "table ="
    """
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        check(schema, toml)
    assert (
        str(exc_info.value) == "'*': 'table =' is not a valid type: "
        "Invalid value (at end of document)"
    )


def test_toml_type_schema() -> None:
    """Test the schema of the TOML type schema."""
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"apple": "stringly"})
    assert str(exc_info.value) == "'apple': 'stringly' is not a valid keyword type."

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"apple": "string = {}\nfloat = {}"})
    assert (
        str(exc_info.value)
        == "'apple': 'string = {}\\nfloat = {}' must have a single key."
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"apple": "string = { banana = true }"})
    assert (
        str(exc_info.value) == "'apple': 'string = { banana = true }' schema error: "
        "'string': Key 'banana' not in schema: { }"
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"apple": "stringly = {}"})
    assert (
        str(exc_info.value)
        == "'apple': 'stringly = {}' schema error: root: Key 'stringly' not in schema: "
        "{ string = { }, "
        'enum = [ "string" ], '
        'pattern = "string", '
        'float = { min = "float", max = "float" }, '
        'integer = { min = "integer", max = "integer" }, '
        "boolean = { }, "
        "offset-date-time = { }, "
        "local-date-time = { }, "
        "date = { }, "
        "time = { }, "
        "any-value = { }, "
        "union = { } }"
    )


def test_toml_key_schema() -> None:
    """Test the schema of the TOML key schema."""
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"apple = { required = 'yes' }": "string"})
    assert str(exc_info.value) == "'apple.required': Value yes is not: \"boolean\""

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"apple = { }\nbanana = { }": "string"})
    assert (
        str(exc_info.value)
        == "root: 'apple = { }\\nbanana = { }' must have a single key."
    )

    # Keys without "=" sign have no limitations:
    toml_schema.from_toml_table({"apple\nbanana": "string"})

    schema_1 = toml_schema.loads("'apple = { required = true }' = 'string'")
    schema_2 = toml_schema.loads("'apple = { required = false }' = 'string'")
    schema_3 = toml_schema.loads("'apple = { }' = 'string'")
    schema_4 = toml_schema.loads("apple = 'string'")
    assert schema_1 != schema_2
    assert schema_2 == schema_3 == schema_4

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("""
            "apple = { required = true }" = "string"
            "apple = { required = false }" = "string"
            banana = "integer"
        """)
    assert (
        str(exc_info.value) == "root: Duplicate keys in table: "
        """['"apple = { required = true }"', 'apple']"""
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("""
            "apple = { required = true, pattern = 'banana' }" = "string"
        """)
    assert (
        str(exc_info.value)
        == """'apple': Key 'pattern' not in schema: { required = "boolean" }"""
    )


def test_toml_string_type() -> None:
    """Test TOML string type."""
    schema = toml_schema.from_toml_table({"apple = { required = true }": "string"})
    assert schema == toml_schema.Table(
        {SchemaKey("apple", required=True): private_toml_schema.String()}
    )
    schema.validate({"apple": "green"})

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"apple": 3})
    assert str(exc_info.value) == "'apple': Value 3 is not: \"string\""

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"apple": "string = { max = 3 }"})
    assert (
        str(exc_info.value) == "'apple': 'string = { max = 3 }' schema error: "
        "'string': Key 'max' not in schema: { }"
    )


def test_toml_enum_type() -> None:
    """Test TOML enumerated string type."""
    schema = toml_schema.from_toml_table({"color": "enum = [ 'Red', 'Green', 'Blue' ]"})
    schema.validate({"color": "Blue"})

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"color": "yellow"})
    assert str(exc_info.value) == "'color': 'yellow' not in ['Red', 'Green', 'Blue']"

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"color": True})
    assert str(exc_info.value) == "'color': Value true is not a string."

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"color": "enum = [ 'Red', 'Blue', 'Blue' ]"})
    assert (
        str(exc_info.value) == "'color': 'enum' must not have duplicates: "
        "['Red', 'Blue', 'Blue']"
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"color": "enum"})
    assert str(exc_info.value) == "'color': 'enum' is not a valid keyword type."


def test_toml_string_pattern() -> None:
    """Test TOML string regular expression pattern matching."""
    schema = toml_schema.from_toml_table({"name": "pattern = '^[A-Z]+$'"})
    schema.validate({"name": "HELLO"})
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"name": "WORLd"})
    assert str(exc_info.value) == "'name': 'WORLd' does not match pattern: ^[A-Z]+$"

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"name": 7})
    assert str(exc_info.value) == "'name': Value 7 is not a string."

    schema = toml_schema.from_toml_table(
        {"name": "pattern = '^([a-zA-Z\\d]|[a-zA-Z\\d][\\w.-]*[a-zA-Z\\d])$'"}
    )
    schema.validate({"name": "toml-schema"})

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"name": "-toml-schema"})
    assert (
        str(exc_info.value) == "'name': '-toml-schema' does not match pattern: "
        r"^([a-zA-Z\d]|[a-zA-Z\d][\w.-]*[a-zA-Z\d])$"
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"name": "pattern = '^([a-z]*$'"})
    assert (
        str(exc_info.value) == "'name': String pattern '^([a-z]*$': "
        "missing ), unterminated subpattern at position 1"
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"name": "pattern = true"})
    assert (
        str(exc_info.value) == "'name': 'pattern = true' schema error: 'pattern': "
        'Value true is not: "string"'
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.from_toml_table({"name": "pattern"})
    assert str(exc_info.value) == "'name': 'pattern' is not a valid keyword type."


def test_toml_float_type() -> None:
    """Test TOML float type."""
    schema = toml_schema.from_toml_table({"price": "float = { min = 3.0, max = 7.0 }"})
    assert schema == toml_schema.Table(
        {SchemaKey("price"): private_toml_schema.Float(min=3.0, max=7.0)}
    )
    schema.validate({"price": 7.0})

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"price": 5})
    assert (
        str(exc_info.value)
        == "'price': Value 5 is not: \"float = { min = 3.0, max = 7.0 }\""
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"price": 2.99})
    assert str(exc_info.value) == "'price': Value out of range: 2.99 < 3.0"

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"price": 100.0})
    assert str(exc_info.value) == "'price': Value out of range: 100.0 > 7.0"

    toml_table: dict[str, toml_schema.TOMLValue] = tomllib.loads("price = nan")
    schema.validate(toml_table)

    toml_table = tomllib.loads("price = -inf")
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate(toml_table)
    assert str(exc_info.value) == "'price': Value out of range: -inf < 3.0"

    schema = toml_schema.from_toml_table({"price": "float = { min = nan, max = inf }"})
    assert str(schema) == '{ price = "float = { min = nan, max = inf }" }'
    schema.validate({"price": 100.0})


def test_toml_int_type() -> None:
    """Test TOML integer type."""
    schema = toml_schema.from_toml_table({"price": "integer = { min = 3, max = 7 }"})
    assert schema == toml_schema.Table(
        {SchemaKey("price"): private_toml_schema.Integer(min=3, max=7)}
    )
    schema.validate({"price": 7})

    # isinstance(True, int) is true. Still, True is not int:
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"price": True})
    assert (
        str(exc_info.value)
        == "'price': Value true is not: \"integer = { min = 3, max = 7 }\""
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"price": 2})
    assert str(exc_info.value) == "'price': Value out of range: 2 < 3"

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"price": 100})
    assert str(exc_info.value) == "'price': Value out of range: 100 > 7"


def test_toml_bool_type() -> None:
    """Test TOML boolean type."""
    schema = toml_schema.from_toml_table({"alive": "boolean = {}"})
    assert schema == toml_schema.Table(
        {SchemaKey("alive"): private_toml_schema.Boolean()}
    )
    schema.validate({"alive": True})

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"alive": 3})
    assert str(exc_info.value) == "'alive': Value 3 is not: \"boolean\""

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"alive": 0})
    assert str(exc_info.value) == "'alive': Value 0 is not: \"boolean\""


def test_toml_datetime_type() -> None:
    """Test TOML datetime type."""
    schema = toml_schema.from_toml_table({"dob": "offset-date-time"})
    assert schema == toml_schema.Table(
        {SchemaKey("dob"): private_toml_schema.OffsetDateTime()}
    )
    toml_table: dict[str, toml_schema.TOMLValue] = tomllib.loads(
        "dob = 1979-05-27T07:32:00-08:00"
    )
    schema.validate(toml_table)

    toml_table = tomllib.loads("dob = 1979-05-27")
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate(toml_table)
    assert str(exc_info.value) == "'dob': Value 1979-05-27 is not: \"offset-date-time\""

    toml_table = tomllib.loads("dob = 1979-05-27T07:32:00")
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate(toml_table)
    assert (
        str(exc_info.value) == "'dob': 'offset-date-time' has no offset: "
        "1979-05-27 07:32:00"
    )

    schema = toml_schema.from_toml_table({"dob": "local-date-time"})
    assert schema == toml_schema.Table(
        {SchemaKey("dob"): private_toml_schema.LocalDateTime()}
    )
    toml_table = tomllib.loads("dob = 1979-05-27T07:32:00")
    schema.validate(toml_table)

    toml_table = tomllib.loads("dob = 1979-05-27T07:32:00-08:00")
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate(toml_table)
    assert (
        str(exc_info.value)
        == "'dob': 'local-date-time' is not local: 1979-05-27 07:32:00-08:00"
    )

    toml_table = tomllib.loads("dob = 1979-05-27")
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate(toml_table)
    assert str(exc_info.value) == "'dob': Value 1979-05-27 is not: \"local-date-time\""


def test_toml_date_type() -> None:
    """Test TOML date type."""
    schema = toml_schema.from_toml_table({"dob": "date = {}"})
    assert schema == toml_schema.Table({SchemaKey("dob"): private_toml_schema.Date()})
    toml_table: dict[str, toml_schema.TOMLValue] = tomllib.loads("dob = 1979-05-27")
    schema.validate(toml_table)

    # isinstance(datetime_value, self._type) is true since datetime is
    # a subclass of date. Still, type(datetime_value) is not date:
    toml_table = tomllib.loads("dob = 1979-05-27T07:32:00")
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate(toml_table)
    assert str(exc_info.value) == "'dob': Value 1979-05-27 07:32:00 is not: \"date\""


def test_toml_time_type() -> None:
    """Test TOML time type."""
    schema = toml_schema.from_toml_table({"alarm": "time = {}"})
    assert schema == toml_schema.Table({SchemaKey("alarm"): private_toml_schema.Time()})
    toml_table: dict[str, toml_schema.TOMLValue] = tomllib.loads("alarm = 08:00:00")
    schema.validate(toml_table)

    toml_table = tomllib.loads("alarm = 1979-05-27T07:32:00")
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate(toml_table)
    assert str(exc_info.value) == "'alarm': Value 1979-05-27 07:32:00 is not: \"time\""


def test_required_key() -> None:
    """Test use of required keys."""
    # Test Table with required keys:
    schema = toml_schema.loads("""
        [fruit]
        "*"."color = { required = true }" = "string"
        "*"."weight = { required = true }" = "any-value"
        "*".taste = "string"
    """)
    toml_table: dict[str, toml_schema.TOMLValue] = tomllib.loads("""
        [fruit.apple]
        color = "sour"
        weight = 5.5

        [fruit.pear]
        color = "green"
        taste = "sweet"
    """)
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate(toml_table)
    assert str(exc_info.value) == "'fruit.pear': Missing required key: weight"

    # Table element required:
    schema = toml_schema.loads("'fruit = { required = true }' = { name = 'string' }")
    toml_table = tomllib.loads("fruit = { name = 'apple' }")
    schema.validate(toml_table)

    toml_table = tomllib.loads("")
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate(toml_table)
    assert str(exc_info.value) == "root: Missing required key: fruit"

    # Array element required:
    schema = toml_schema.loads("'fruits = { required = true }' = [ 'string' ]")
    toml_table = tomllib.loads("fruits = [ 'apple' ]")
    schema.validate(toml_table)

    toml_table = tomllib.loads("")
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate(toml_table)
    assert str(exc_info.value) == "root: Missing required key: fruits"

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads("site.'\"*\" = { required = true }' = 'boolean'")
    assert (
        str(exc_info.value) == "'site': Wildcard key '*' cannot be marked as required."
    )

    # Test quoted key that are also required:
    schema = toml_schema.loads("""'"fruit flies" = { required = true }' = 'string'""")
    assert str(schema) == r'{ "\"fruit flies\" = { required = true }" = "string" }'
    schema.validate({"fruit flies": "like an arrow"})


def test_key_pattern() -> None:
    """Test use of wildcard key patterns."""
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        SchemaKey("name", pattern="***")
    assert (
        str(exc_info.value) == """root: '"pattern = '***'"': """
        "Pattern key must be 'pattern'."
    )

    with pytest.raises(toml_schema.SchemaError) as exc_info:
        toml_schema.loads('''"pattern = '(world'" = "boolean"''')
    assert (
        str(exc_info.value) == "root: Key pattern '(world': "
        "missing ), unterminated subpattern at position 0"
    )

    # Make sure that a key named "pattern" is not confused with actual patterns:
    schema = toml_schema.loads("""
        pattern = "integer"
        "pattern = '^[a-z]*$'" = "float"
        "pattern = '^[A-Z]*$'" = "boolean"
        "*" = "string"
    """)
    schema.validate(
        {
            "pattern": 3,
            "qwerty": 3.14,
            "QWERTY": True,
            "Qwerty": "hello",
        }
    )

    # Patterns can be used to specify keys with "=" in them:
    schema = toml_schema.loads("""
        "pattern = '^hello=world$'" = "boolean"
    """)
    schema.validate({"hello=world": True})
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"hello world": True})
    assert (
        str(exc_info.value) == "root: Key 'hello world' not in schema: "
        """{ "pattern = '^hello=world$'" = "boolean" }"""
    )

    # Patterns can be used to specify the key "*":
    schema = toml_schema.loads(r"""
        "pattern = '^\\*$'" = "boolean"
    """)
    schema.validate({"*": True})
    with pytest.raises(toml_schema.SchemaError) as exc_info:
        schema.validate({"x": True})
    assert (
        str(exc_info.value) == "root: Key 'x' not in schema: "
        r"""{ "pattern = '^\*$'" = "boolean" }"""
    )

    schema = toml_schema.loads(r"""
        "pattern = 'boolean:\\w'" = "boolean"
        "pattern = 'string:\\w'" = "string"
    """)
    schema.validate(
        {
            "boolean:apple": True,
            "boolean:banana": False,
            "string:mango": "mango",
            "string:pineapple": "pineapple",
        }
    )


def run_toml_schema(*args: str) -> None:
    """Run toml-schema as if it was an executable."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "argv", ["toml-schema", *args])
        runpy.run_module("toml_schema", run_name="__main__")


def test_main(capsys: pytest.CaptureFixture[str]) -> None:
    """Test main entry point."""
    # Test argument error:
    with pytest.raises(SystemExit, match="2"):
        run_toml_schema()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err == "usage: toml-schema [-h] [--version] schema_file toml_file\n"
        "toml-schema: error: the following arguments are required: "
        "schema_file, toml_file\n"
    )

    # Test help message:
    with pytest.raises(SystemExit, match="0"):
        run_toml_schema("--help")
    captured = capsys.readouterr()
    assert captured.out.startswith(
        "usage: toml-schema [-h] [--version] schema_file toml_file\n"
        "\n"
        "positional arguments:\n"
        "  schema_file\n"
        "  toml_file\n"
    )
    assert captured.err == ""

    # Check schema of pyproject.toml full example from https://packaging.python.org/
    with pytest.raises(SystemExit, match="0"):
        run_toml_schema("--version")
    captured = capsys.readouterr()
    assert captured.out == f"toml-schema {toml_schema.__version__}\n"
    assert captured.err == ""

    # Check schema of pyproject.toml full example from https://packaging.python.org/
    run_toml_schema("examples/pyproject.toml-schema", "examples/pyproject.toml")
    captured = capsys.readouterr()
    assert captured.out == "TOML schema validated.\n"
    assert captured.err == ""

    # Check schema of our own pyproject.toml:
    run_toml_schema("examples/pyproject.toml-schema", "pyproject.toml")
    captured = capsys.readouterr()
    assert captured.out == "TOML schema validated.\n"
    assert captured.err == ""

    # Test failed schema check:
    with pytest.raises(SystemExit, match="1"):
        run_toml_schema("pyproject.toml", "examples/pyproject.toml-schema")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err == "'project.name': 'toml-schema' is not a valid keyword type.\n"
    )
