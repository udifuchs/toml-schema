"""Convert a JSON schema to a TOML schema."""

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
    "dependencies",
    "minProperties",  # Shows up only in json object.
    "propertyNames",  # Shows up only in json object.
)

# Regex patterns taken from:
# https://github.com/horejsek/python-fastjsonschema/blob/master/fastjsonschema/draft04.py
EMAIL_PATTERN = r"^(?!.*\.\..*@)[^@.][^@]*(?<!\.)@[^@]+\.[^@]+\Z"
URI_PATTERN = r"^\w+:(\/?\/?)[^\s]+\Z"
FORMAT: dict[str, dict[str, str]] = {}


# Specific handlers for JSON schemas with unusual combinations:


def handle_pyproject_project_one_of(key: str, json_object: dict[str, Any]) -> None:
    if global_filename == "pyproject.json" and key == "project":
        one_of = json_object.pop("oneOf")
        warning(f"{key}: ignoring item: oneOf = {one_of}")


def handle_pyproject_project_author(key: str, json_object: dict[str, Any]) -> None:
    if (
        global_filename == "pyproject.json"
        and key == '"defs = { hidden = true }".projectAuthor'
    ):
        any_of = json_object.pop("anyOf")
        warning(f"{key}: ignoring item: anyOf = {any_of}")


def handle_setuptools_readme(key: str, json_object: dict[str, Any]) -> None:
    if (
        global_filename == "partial-setuptools.json"  # fmt: skip
        and key == "dynamic"
    ):
        json_object = json_object["properties"]["readme"]
        json_type = json_object.pop("type")
        warning(f"{key}: ignoring item: type = {json_type}")
        required = json_object.pop("required")
        json_object["anyOf"][1]["required"] = required
        warning(f"{key}: key 'required' moved to expected location.")


def handle_setuptools_define_macros(key: str, json_object: dict[str, Any]) -> None:
    if (
        global_filename == "partial-setuptools.json"
        and key == '"defs = { hidden = true }".ext-module.define-macros[0]'
    ):
        add_items = json_object.pop("additionalItems")
        assert add_items is False
        json_object["items"] = {"type": "string"}
        json_object["minItems"] = 2
        json_object["maxItems"] = 2
        warning(f"{key}: Special handling for tuple validation.")


def handle_cibuildwheels_defs_description(
    key: str, json_object: dict[str, Any]
) -> None:
    if (
        global_filename == "partial-cibuildwheel.json"
        and key == '"defs = { hidden = true }"'
    ):
        desc = json_object.pop("description")
        warning(f"{key}: ignoring item: description = {desc}")


def handle_poe_cwd_min_len(key: str, json_object: dict[str, Any]) -> None:
    if (
        global_filename == "partial-poe.json"
        and key == '"defs = { hidden = true }".common_task.cwd'
    ):
        json_object.pop("minLength")
        warning(f"{key}: Redundant minLength in pattern")


def handle_hatch_empty_override() -> str | None:
    if global_filename == "hatch.json":
        return '"any-value"'
    return None


def handle_hatch_root_one_of(key: str, json_object: dict[str, Any]) -> None:
    if global_filename == "hatch.json" and key == "":
        one_of = json_object.pop("oneOf")
        warning(f"{key}: Ignored 'oneOf': {one_of}")


def handle_hatch_build_any_of(key: str, json_object: dict[str, Any]) -> None:
    if (
        global_filename == "hatch.json"  # fmt: skip
        and key == '"defs = { hidden = true }".Build'
    ):
        any_of = json_object.pop("anyOf")
        warning(f"{key}: ignoring item: anyOf = {any_of}")


def handle_hatch_publish_index_repos(key: str, json_object: dict[str, Any]) -> None:
    if (
        global_filename == "hatch.json"
        and key == '"defs = { hidden = true }".PublishIndex'
    ):
        json_object = json_object["properties"]["repos"]
        properties = json_object.pop("properties")
        warning(f"{key}.repos: ignoring item: properties = {properties}")


def handle_pdm_env_file_override(key: str, json_object: dict[str, Any]) -> None:
    if (
        global_filename == "partial-pdm.json"
        and key == '"defs = { hidden = true }".env-file'
    ):
        problem = json_object["anyOf"][0]
        add_prop = problem["properties"].pop("additionalProperties")
        problem["additionalProperties"] = add_prop
        warning(f"{key}.env-file: bad location for additionalProperties = {add_prop}")


def handle_poe_args_defs(key: str, json_defs: dict[str, Any] | None) -> None:
    if (
        global_filename == "partial-poe.json"  # fmt: skip
        and json_defs is not None
    ):
        json_object = json_defs["common_task"]["properties"]["args"]
        # Move 'args' definition to the top:
        defs = json_object.pop("definitions")
        json_defs["args"] = defs["args"]
        # Reassign references to 'args' definition:
        old_def = "#/definitions/common_task/properties/args/definitions/args"
        new_def = "#/definitions/args"
        assert json_object["anyOf"][0]["items"]["anyOf"][1]["$ref"] == old_def
        json_object["anyOf"][0]["items"]["anyOf"][1]["$ref"] = new_def
        assert json_object["anyOf"][1]["additionalProperties"]["$ref"] == old_def
        json_object["anyOf"][1]["additionalProperties"]["$ref"] = new_def
        warning(f"{key}: args definition moved to top.")


def get_toml_element(  # noqa: C901, PLR0911
    key: str, json_object: dict[str, Any], *, inline: bool
) -> str | None:
    debug(f"get {key}")
    for ignore in JSON_IGNORE:
        if ignore in json_object:
            json_object.pop(ignore)
    for ignore in JSON_TODO:
        if ignore in json_object:
            value = json_object.pop(ignore)
            warning(f"{key}: Ignoring key: {ignore}, value: {value}")

    handle_setuptools_readme(key, json_object)
    handle_setuptools_define_macros(key, json_object)
    handle_pyproject_project_one_of(key, json_object)
    handle_pyproject_project_author(key, json_object)
    handle_hatch_root_one_of(key, json_object)
    handle_hatch_build_any_of(key, json_object)
    handle_hatch_publish_index_repos(key, json_object)
    handle_poe_cwd_min_len(key, json_object)
    handle_pdm_env_file_override(key, json_object)

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
        return get_toml_pattern(json_object)

    toml_union = get_toml_union(key, json_object)
    if toml_union is not None:
        return toml_union

    if "type" in json_object:
        return get_toml_type(key, json_object, inline=inline)

    if "$ref" in json_object:
        return get_toml_ref(key, json_object)

    warning(f"{key}: Missing type in: {json_object}")
    return handle_hatch_empty_override()


def get_toml_type(key: str, json_object: dict[str, Any], *, inline: bool) -> str | None:
    json_type = json_object.pop("type")
    if "$ref" in json_object:
        ref = json_object.pop("$ref")
        warning(f"{key}: Redundant $ref ignored: {ref}")
    if isinstance(json_type, list):
        if "null" in json_type:
            del json_type[json_type.index("null")]
        if len(json_type) > 1:
            union_str = ", ".join(f'"{typ}"' for typ in json_type)
            return f"{{ union = [ {union_str} ] }}"
        if len(json_type) < 1:
            raise Exception(f"{key}: JSON type array is empty: {json_type}")
        json_type = json_type[0]

    if json_type == "object":
        return get_toml_table(key, json_object, inline=inline)
    if json_type == "array":
        return get_toml_array(key, json_object)

    if json_type == "number":
        json_type = "float"

    return get_toml_type_options(key, json_type, json_object)


def get_toml_type_options(  # noqa: C901, PLR0912, PLR0915
    key: str, json_type: str, json_object: dict[str, Any]
) -> str | None:
    options = []
    if "minLength" in json_object:
        min_len = json_object.pop("minLength")
        options.append(f"min-len = {min_len}")
    if "maxLength" in json_object:
        max_len = json_object.pop("maxLength")
        options.append(f"max-len = {max_len}")
    minimum: float | int | None = None
    maximum: float | int | None = None
    if "minimum" in json_object:
        json_minimum = json_object.pop("minimum")
        if isinstance(json_minimum, (int, float)):
            minimum = json_minimum
            if json_type == "integer" and not isinstance(minimum, int):
                info(f"{key}: Minimum with non-integer value: {minimum}")
                minimum = int(minimum)
        else:
            raise Exception(f"{key}: Minimum with non-numeric value: {json_minimum}")
    if "maximum" in json_object:
        json_maximum = json_object.pop("maximum")
        if isinstance(json_maximum, (int, float)):
            maximum = json_maximum
            if json_type == "integer" and not isinstance(maximum, int):
                info(f"{key}: Maximum with non-integer value: {maximum}")
                maximum = int(maximum)
        else:
            raise Exception(f"{key}: Maximum with non-numeric value: {json_maximum}")
    if "format" in json_object:
        json_format = json_object.pop("format")
        if json_format == "email":
            FORMAT[global_filename]["email"] = f'''"pattern = {EMAIL_PATTERN!r}"'''
            return '''"ref = 'format.email'"'''
        if json_format == "uri":
            FORMAT[global_filename]["uri"] = f'''"pattern = {URI_PATTERN!r}"'''
            return '''"ref = 'format.uri'"'''
        # The format value is not part of the json schema specification.
        if json_type == "string":
            warning(f"{key}: Adding generic string format rule: {json_format}")
            FORMAT[global_filename][json_format] = '''"pattern = '^.*$'"'''
            return f'''"ref = 'format.{json_format}'"'''
        if json_format == "uint8":
            minimum = 0 if minimum is None else max(minimum, 0)
            maximum = 0xFF if maximum is None else min(maximum, 0xFF)
        elif json_format == "uint16":
            minimum = 0 if minimum is None else max(minimum, 0)
            maximum = 0xFFFF if maximum is None else min(maximum, 0xFFFF)
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


def get_toml_ref(key: str, json_object: dict[str, Any]) -> str | None:
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
        json_ref = ref[len(global_uri_base) + 1 :]
        global_file_list.append(json_ref)
        debug(f"{key}: Queued file for loading: {json_ref}")
        if WGET:
            subprocess.run(  # noqa: PLW1510,S603
                ["wget", f"--output-document={json_ref}", ref]  # noqa: S607
            )
        toml_ref = pathlib.Path(json_ref).with_suffix(".schema.toml")
        return f'''"file = '{toml_ref}'"'''
    warning(f"{key}: Unsupported reference: {ref}")
    return '"any-value"'


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
            if pattern_properties is None:
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

    handle_poe_args_defs(key, json_defs)

    if "anyOf" in json_table_object:
        any_of = json_table_object.pop("anyOf")
        raise Exception(f"{key}: 'anyOf' in json object ignored: {any_of}")

    if "oneOf" in json_table_object:
        one_of = json_table_object.pop("oneOf")
        raise Exception(f"{key}: 'oneOf' in json object ignored: {one_of}")

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


def get_toml_table_from_properties(  # noqa: C901, PLR0912, PLR0913, PLR0915
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
        assert global_toml_file is not None
        global_toml_file.write(f"\n[{key}]\n")

    if json_properties is not None:
        handle_cibuildwheels_defs_description(key, json_properties)

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
                assert global_toml_file is not None
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
            json_properties=json_defs,
            json_pattern_properties=None,
            json_defs=None,
            inline=False,
            required_list=[],
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
    if isinstance(json_items, list):
        raise Exception(  # noqa: TRY004
            f"{key}: No support for 'items' list: {json_items}"
        )
    toml_type = get_toml_element(f"{key}[0]", json_items, inline=True)

    options = []
    if "minItems" in json_object:
        min_items = json_object.pop("minItems")
        options.append(f'"min-items = {min_items}"')
    if "maxItems" in json_object:
        max_items = json_object.pop("maxItems")
        options.append(f'"max-items = {max_items}"')
    if "uniqueItems" in json_object:
        unique_items = json_object.pop("uniqueItems")
        options.append(f'"unique-items = {str(unique_items).lower()}"')
    if "additionalItems" in json_object:
        add_items = json_object.pop("additionalItems")
        if add_items is not False:
            raise Exception(f"{key}: Unsupported additionalItems = {add_items}")
    if json_object != {}:
        raise Exception(f"Extra keys: {key}: {json_object}")
    if len(options) > 0:
        return f"[ {toml_type}, {', '.join(options)} ]"
    return f"[ {toml_type} ]"


def get_toml_pattern(json_object: dict[str, Any]) -> str | None:
    pattern = json_object.pop("pattern")
    if "type" in json_object:
        json_type = json_object.pop("type")
        assert json_type == "string"
    if "\n" in pattern:
        pattern = pattern.replace("\n", "\\n")
    if "'" in pattern:
        pattern = repr(pattern).replace(r"\'", "'")
        return f'''"""\n    pattern = ''{pattern}''\n"""'''
    return f'"""\n    pattern = {pattern!r}\n"""'


def get_toml_union(  # noqa: C901, PLR0912, PLR0915
    key: str, json_object: dict[str, Any]
) -> str | None:
    if "anyOf" in json_object:
        union_list = json_object.pop("anyOf")
        union_mode = "any"
    elif "oneOf" in json_object:
        # anyOf and oneOf are almost identical when used as unions.
        union_list = json_object.pop("oneOf")
        try:
            union_types = [elem["type"] for elem in union_list]
        except KeyError:
            info(f"{key}: Check if oneOf could be replaced with anyOf.")
            union_mode = "one"
        else:
            if len(union_types) == len(set(union_types)):
                # All types are different:
                info(f"{key}: oneOf is treated as anyOf: {union_types}")
                union_mode = "any"
            elif len(set(union_types)) == 1 and union_types[0] == "string":
                try:
                    union_enums = [
                        enum_value
                        for element in union_list
                        for enum_value in element["enum"]
                    ]
                    if len(union_enums) == len(set(union_enums)):
                        # All types are enum strings with different values:
                        info(f"{key}: oneOf is treated as anyOf: {union_enums}")
                        union_mode = "any"
                    else:
                        info(f"{key}: Check if oneOf could be replaced with anyOf.")
                        union_mode = "one"
                except KeyError:
                    info(f"{key}: Check if oneOf could be replaced with anyOf.")
                    union_mode = "one"
            else:
                info(f"{key}: Check if oneOf could be replaced with anyOf.")
                union_mode = "one"
    elif "allOf" in json_object:
        union_list = json_object.pop("allOf")
        union_mode = "all"
    elif "not" in json_object:
        union_list = json_object.pop("not")
        union_mode = "none"
    else:
        return None

    if "type" in json_object:
        json_type = json_object.pop("type")
        warning(f"{key}: Redundant type in anyOf ignored: {json_type}")
    if "required" in json_object:
        required = json_object.pop("required")
        raise Exception(f"{key}: 'required' in union not supported: {required}")
    union_types = []
    if union_mode == "none":
        typ = get_toml_element(key, union_list, inline=True)
        union_types.append(typ)
    else:
        for i, json_item in enumerate(union_list):
            typ = get_toml_element(f"{key}[{i}]", json_item, inline=True)
            if typ != '"null"' and typ is not None:
                union_types.append(typ)
            if json_item != {}:
                raise Exception(f"Extra keys: {key}[{i}]: {json_item}")
        if len(union_types) == 1:
            info(f"{key}: Union with length 1: {union_types}")
            assert isinstance(union_types[0], str)
            return union_types[0]
    union_str = ",\n    ".join(union_types)
    if union_mode == "any":
        return f"{{ union = [\n    {union_str},\n] }}"
    return f'{{ "union = {union_mode!r}" = [\n    {union_str},\n] }}'


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


def convert(json_filename: str) -> pathlib.Path:
    global global_filename  # noqa: PLW0603
    global_filename = json_filename
    FORMAT[global_filename] = {}

    with pathlib.Path(json_filename).open("r") as json_file:
        json_object = json.load(json_file)

    toml_filename = pathlib.Path(json_filename).with_suffix(".schema.toml")
    debug(f"Generating file: {toml_filename}")
    global global_toml_file
    with pathlib.Path(toml_filename).open("w") as global_toml_file:
        json_type = get_toml_element("", json_object, inline=False)
        if json_object != {}:
            raise Exception(f"Extra keys: {json_object}")
        assert json_type is None

        if len(FORMAT[global_filename]) > 0:
            global_toml_file.write('\n["format = { hidden = true }"]\n')
            for key, format_value in FORMAT[global_filename].items():
                global_toml_file.write(f"\n{key} = {format_value}\n")

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
    global_uri_base = json_id[: json_id.rfind("/")]
    json_filename = json_id[len(global_uri_base) + 1 :]

    if WGET:
        subprocess.run(  # noqa: PLW1510,S603
            ["wget", f"--output-document={json_filename}", json_id]  # noqa: S607
        )
    toml_filename = convert(json_filename)

    while len(global_file_list) > 0:
        json_file = global_file_list.pop(0)
        convert(json_file)

    toml_schema.from_file(str(toml_filename))


if __name__ == "__main__":
    main()
