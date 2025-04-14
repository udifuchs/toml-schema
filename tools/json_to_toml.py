"""Convert a JSON schema to a TOML schema."""

# ruff: noqa: TRY002
# ruff: noqa: T201
# ruff: noqa: S101
# ruff: noqa: D103
# ruff: noqa: TD002
# ruff: noqa: TD003

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
from typing import Any

import toml_schema

WGET = False
VERBOSE_LEVEL = 1
# 1 - Warning that should be treated.
# 2 - Information that is safe to ignore.
# 3 - Debug.


def debug(text: str) -> None:
    if VERBOSE_LEVEL >= 3:
        print(f"DEBUG: {global_filename}: {text}")


def info(text: str) -> None:
    if VERBOSE_LEVEL >= 2:
        print(f"INFO: {global_filename}: {text}")


def warning(text: str) -> None:
    if VERBOSE_LEVEL >= 1:
        print(f"WARNING: {global_filename}: {text}")


JSON_IGNORE = (
    "$schema",
    "$id",
    "$comment",
    "title",
    "description",
    "markdownDescription",
    "x-intellij-html-description",
    "x-intellij-language-injection",
    "x-taplo",
    "x-taplo-info",
    "x-tombi-table-keys-order",
    "x-tombi-toml-version",
    "x-tombi-array-values-order",
    "examples",
    "default",
    "deprecated",
    "$$description",  # Used by https://github.com/pypa/setuptools/config/setuptools.schema.json
)
JSON_TODO = (
    "if",
    "then",
    "else",
    "minLength",
    "maxLength",
    "minItems",
    "dependencies",
    "minProperties",  # Shows up only in json object.
    "propertyNames",  # Shows up only in json object.
    "uniqueItems",  # For array
    "additionalItems",  # For array
)


def get_toml_element(  # noqa: C901, PLR0911, PLR0912
    key: str, json_object: dict[str, Any], *, inline: bool
) -> str | None:
    debug(f"get {key}")
    for ignore in JSON_IGNORE:
        if ignore in json_object:
            del json_object[ignore]
    for ignore in JSON_TODO:
        if ignore in json_object:
            value = json_object.pop(ignore)
            warning(f"{key}: Ignoring key: {ignore}, value: {value}")

    if "enum" in json_object:
        if "type" in json_object:
            json_type = json_object.pop("type")
            assert json_type == "string"
        enum_list = json_object.pop("enum")
        enum_str = "\n".join(f'    "{value}",' for value in enum_list)
        return f'"""enum = [\n{enum_str}\n]"""'

    if "const" in json_object:
        const = json_object.pop("const")
        assert isinstance(const, str)
        if "type" in json_object:
            json_type = json_object.pop("type")
            assert json_type == "string"
        return f'''"enum = [ '{const}' ]"'''

    if "pattern" in json_object:
        if "type" in json_object:
            json_type = json_object.pop("type")
            assert json_type == "string"
        pattern = json_object.pop("pattern")
        if "\n" in pattern:
            warning(rf"{key}: Replaced '\n' with '\\n' in pattern.")
            pattern = pattern.replace("\n", "\\n")
        if "'" in pattern:
            pattern = repr(pattern).replace(r"\'", "'")
            return f'''"""\n    pattern = ''{pattern}''\n"""'''
        return f'"""\n    pattern = {pattern!r}\n"""'

    toml_union = get_toml_union(key, json_object)
    if toml_union is not None:
        return toml_union

    if "type" in json_object:
        return get_toml_type(key, json_object, inline=inline)

    if "$ref" in json_object:
        ref = json_object.pop("$ref")
        if ref.startswith("#/"):
            keys = ref.split("/")[1:]
            if keys[0] in ("definitions", "$defs"):
                keys = [key for key in keys[1:] if key != "properties"]
                toml_key = ".".join(keys)
                return f'''"ref = 'defs.{toml_key}'"'''
            if keys[0] == "properties":
                keys = [key for key in keys if key != "properties"]
                toml_key = ".".join(keys)
                return f'''"ref = '{toml_key}'"'''
        if ref.startswith(global_uri_base):
            json_ref = ref[len(global_uri_base) + 1:]
            global_file_list.append(json_ref)
            debug(f"{key}: Queued file for loading: {json_ref}")
            if WGET:
                subprocess.run(  # noqa: PLW1510,S603
                    ["wget", f"--output-document={json_ref}", ref]  # noqa: S607
                )
            toml_ref = pathlib.Path(json_ref).with_suffix(".toml-schema")
            return f'''"file = '{toml_ref}'"'''
        warning(f"{key}: Unsupported reference: {ref}")
        return '"any-value"'

    warning(f"{key}: Missing type in: {json_object}")
    return "{ }"


def get_toml_type(  # noqa: C901, PLR0912
    key: str, json_object: dict[str, Any], *, inline: bool
) -> str | None:
    json_type = json_object.pop("type")
    if "$ref" in json_object:
        ref = json_object.pop("$ref")
        warning(f"{key}: Redundant $ref ignored: {ref}")
    if isinstance(json_type, list):
        if "null" in json_type:
            del json_type[json_type.index("null")]
        if len(json_type) > 1:
            union_str = ", ".join(f'"{typ}"' for typ in json_type)
            return f'[ "union", {union_str} ]'
        if len(json_type) < 1 :
            raise Exception(f"{key}: JSON type array is empty: {json_type}")
        json_type = json_type[0]

    if "anyOf" in json_object:
        any_of = json_object.pop("anyOf")
        warning(f"{key}: 'anyOf' in json type ignored: {any_of}")

    if json_type == "object":
        return get_toml_table(key, json_object, inline=inline)
    if json_type == "array":
        return get_toml_array(key, json_object)

    options = []
    minimum: float | int | None = None
    maximum: float | int | None = None
    if "minimum" in json_object:
        minimum = json_object.pop("minimum")
        if json_type == "integer" and not isinstance(minimum, int):
            info(f"{key}: Minimum with non-integer value: {minimum}")
            minimum = int(minimum)
    if "maximum" in json_object:
        maximum = json_object.pop("maximum")
        if json_type == "integer" and not isinstance(maximum, int):
            info(f"{key}: Maximum with non-integer value: {maximum}")
            maximum = int(maximum)
    if "format" in json_object:
        # The format value is not part of the json schema specification.
        json_format = json_object.pop("format")
        if json_format == "uint8":
            minimum = 0 if minimum is None else max(minimum, 0)
            maximum = 0xff if maximum is None else min(maximum, 0xff)
        elif json_format == "uint16":
            minimum = 0 if minimum is None else max(minimum, 0)
            maximum = 0xffff if maximum is None else min(maximum, 0xffff)
        elif json_format == "uint":
            minimum = 0 if minimum is None else max(minimum, 0)
        else:
            warning(f"{key}: Ignoring format: {json_format}")

    if minimum is not None:
        options.append(f"min = {minimum}")
    if maximum is not None:
        options.append(f"max = {maximum}")
    if len(options) > 0:
        options_str = ", ".join(options)
        return f'"{json_type} = {{ {options_str} }}"'
    return f'"{json_type}"'


def get_toml_table(  # noqa: C901, PLR0912
    key: str, json_table_object: dict[str, Any], *, inline: bool
) -> str | None:
    required_list = json_table_object.pop("required", [])

    properties = None
    pattern_properties = None
    if "patternProperties" in json_table_object:
        pattern_properties = json_table_object.pop("patternProperties")
    if "properties" in json_table_object:
        properties = json_table_object.pop("properties")
    if "additionalProperties" in json_table_object:
        ap = json_table_object.pop("additionalProperties")
        if ap is not False:
            if pattern_properties is not None:
                raise Exception(
                    f"{key}: Cannot mix additionalProperties with patternProperties"
                )
            pattern_properties = {}
            if ap is True:
                pattern_properties['"*"'] = {"type": "any-value"}
            else:
                pattern_properties['"*"'] = ap
    else:
        if pattern_properties is None:
            pattern_properties = {}
        warning(f"{key}: No additionalProperties. Defaults to true.")
        assert '"*"' not in pattern_properties
        pattern_properties['"*"'] = {"type": "any-value"}

    json_defs = None
    if "definitions" in json_table_object:
        json_defs = json_table_object.pop("definitions")
    if "$defs" in json_table_object:
        if json_defs is not None:
            raise Exception("'definitions' and '$defs' both defined.")
        json_defs = json_table_object.pop("$defs")

    if "anyOf" in json_table_object:
        any_of = json_table_object.pop("anyOf")
        warning(f"{key}: 'anyOf' in json object ignored: {any_of}")

    if "oneOf" in json_table_object:
        one_of = json_table_object.pop("oneOf")
        warning(f"{key}: 'oneOf' in json object ignored: {one_of}")

    if json_table_object != {}:
        raise Exception(f"{key}: Extra values: {json_table_object}")

    return get_toml_table_from_properties(
        key,
        properties,
        pattern_properties,
        json_defs,
        inline=inline,
        required_list=required_list,
    )


def get_toml_table_from_properties(  # noqa: C901, PLR0912, PLR0913
    key: str,
    json_properties: dict[str, Any] | None,
    json_pattern_properties: dict[str, Any] | None,
    json_defs: dict[str, Any] | None,
    *,
    inline: bool,
    required_list: list[str],
) -> str | None:
    if inline:
        inline_types = {}
    elif key != "":
        global_toml_file.write(f"\n[{key}]\n")

    def is_table(json_object: dict[str, Any]) -> bool:
        if "type" in json_object:
            json_type = json_object["type"]
            if json_type == "object":
                return True
            if isinstance(json_type, list) and "object" in json_type:
                return True
        return False

    def process_sub_key(sub_key: str, json_object: dict[str, Any]) -> None:
        if sub_key in required_list:
            del required_list[required_list.index(sub_key)]
            sub_key_str = f'"{sub_key} = {{ required = true }}"'
        else:
            sub_key_str = sub_key
        full_key = sub_key_str if key == "" else f"{key}.{sub_key_str}"
        json_type = get_toml_element(full_key, json_object, inline=inline)
        if json_type is not None:
            if inline:
                inline_types[sub_key_str] = json_type
            else:
                global_toml_file.write(f"{sub_key_str} = {json_type}\n")
        if json_object != {}:
            raise Exception(f"Extra keys: {key}.{sub_key}: {json_object}")

    if json_properties is None and json_pattern_properties is None:
        warning(f"{key}: Empty table.")
        return None

    if json_properties is not None:
        for sub_key, json_object in json_properties.items():
            if is_table(json_object):
                continue
            process_sub_key(sub_key, json_object)

    if json_pattern_properties is not None:
        for sub_key, json_object in json_pattern_properties.items():
            if is_table(json_object):
                continue
            sub_key_pat = sub_key if sub_key == '"*"' else f'"pattern = {sub_key!r}"'
            process_sub_key(sub_key_pat, json_object)

    if json_properties is not None:
        for sub_key, json_object in json_properties.items():
            if not is_table(json_object):
                continue
            process_sub_key(sub_key, json_object)

    if json_pattern_properties is not None:
        for sub_key, json_object in json_pattern_properties.items():
            if not is_table(json_object):
                continue
            sub_key_pat = sub_key if sub_key == '"*"' else f'"pattern = {sub_key!r}"'
            process_sub_key(sub_key_pat, json_object)

    if json_defs is not None:
        get_toml_table_from_properties(
            '"defs = { hidden = true }"',
            json_properties = json_defs,
            json_pattern_properties = None,
            json_defs = None,
            inline=False,
            required_list=[]
        )

    if len(required_list) != 0:
        raise Exception(f"{key}: Extra required: {required_list}")
    if inline:
        inline_str = ", ".join(
            f"{key} = {value}" for key, value in inline_types.items()
        )
        return f"{{ {inline_str} }}"
    return None


def get_toml_array(key: str, json_object: dict[str, Any]) -> str:
    if "items" in json_object:
        json_items = json_object.pop("items")
    else:
        warning(f"{key}: Array without items")
        json_items = {"type": "any-value"}
    toml_type = get_toml_element(key, json_items, inline=True)
    if json_object != {}:
        raise Exception(f"Extra keys: {key}: {json_object}")
    return f"[ {toml_type} ]"


def get_toml_union(  # noqa: C901, PLR0912
    key: str, json_object: dict[str, Any]
) -> str | None:
    if "anyOf" in json_object:
        union_list = json_object.pop("anyOf")
    elif "oneOf" in json_object:
        # anyOf and oneOf are almost identical when used as unions.
        union_list = json_object.pop("oneOf")
        try:
            union_types = [elem["type"] for elem in union_list]
        except KeyError:
            warning(f"{key}: oneOf is treated as anyOf: {union_list}")
        else:
            if len(union_types) == len(set(union_types)):
                # All types are different:
                info(f"{key}: oneOf is treated as anyOf: {union_types}")
            elif len(set(union_types)) == 1 and union_types[0] == "string":
                try:
                    union_enums = [
                        enum
                        for elem in union_list
                        for enum in elem["enum"]
                    ]
                    if len(union_enums) == len(set(union_enums)):
                        # All types are enum strings with different values:
                        info(f"{key}: oneOf is treated as anyOf: {union_enums}")
                    else:
                        warning(f"{key}: oneOf for enums is treated as anyOf.")
                except KeyError:
                    warning(f"{key}: oneOf is treated as anyOf.")
            else:
                warning(f"{key}: oneOf is treated as anyOf.")
    elif "allOf" in json_object:
        warning(f"{key}: allOf is treated as anyOf.")
        union_list = json_object.pop("allOf")
    else:
        return None

    if "type" in json_object:
        json_type = json_object.pop("type")
        warning(f"{key}: Redundant type in anyOf ignored: {json_type}")
    if "required" in json_object:
        required = json_object.pop("required")
        warning(f"{key}: 'required' in union not supported: {required}")
    union_types = []
    for i, json_item in enumerate(union_list):
        typ = get_toml_element(key, json_item, inline=True)
        if typ != '"null"':
            union_types.append(typ)
        if json_item != {}:
            raise Exception(f"Extra keys: {key}[{i}]: {json_item}")
    if len(union_types) == 1:
        info(f"{key}: Union with length 1: {union_types}")
        return union_types[0]
    union_str = ",\n    ".join(union_types)
    return f'[\n    "union",\n    {union_str},\n]'


def get_json_defs(key: str, json_object: dict[str, Any]) -> None:
    json_defs = None
    if "definitions" in json_object:
        json_defs = json_object.pop("definitions")
    if "$defs" in json_object:
        if json_defs is not None:
            raise Exception("'definitions' and '$defs' both defined.")
        json_defs = json_object.pop("$defs")

    if json_defs is not None:
        get_toml_table_from_properties(
            key, json_defs, None, None, inline=False, required_list=[]
        )


global_uri_base = ""
global_filename = ""
global_toml_file = None
global_file_list: list[str] = []


def convert(json_filename: str) -> str:

    global global_filename  # noqa: PLW0603
    global_filename = json_filename

    with pathlib.Path(json_filename).open("r") as json_file:
        json_object = json.load(json_file)

    toml_filename = pathlib.Path(json_filename).with_suffix(".toml-schema")
    debug(f"Generating file: {toml_filename}")
    global global_toml_file
    with pathlib.Path(toml_filename).open("w") as global_toml_file:
        if "oneOf" in json_object and json_filename == "hatch.json":
            one_of = json_object.pop("oneOf")
            warning(f"Ignored 'oneOf': {one_of}")

        json_type = get_toml_element("", json_object, inline=False)
        if json_object != {}:
            raise Exception(f"Extra keys: {json_object}")
        assert json_type is None

    return toml_filename


def main() -> None:

    os.chdir("schemastore")

    parser = argparse.ArgumentParser()
    parser.add_argument("--wget", action="store_true")
    args = parser.parse_args()

    global WGET  # noqa: PLW0603
    WGET = args.wget

    json_id = "https://json.schemastore.org/pyproject.json"

    global global_uri_base  # noqa: PLW0603
    global_uri_base = json_id[:json_id.rfind("/")]
    json_filename = json_id[len(global_uri_base) + 1:]

    if WGET:
        subprocess.run(  # noqa: PLW1510,S603
            ["wget", f"--output-document={json_filename}", json_id]  # noqa: S607
        )
    toml_filename = convert(json_filename)

    while len(global_file_list) > 0:
        json_file = global_file_list.pop(0)
        convert(json_file)

    toml_schema.from_file(toml_filename)


if __name__ == "__main__":
    main()
