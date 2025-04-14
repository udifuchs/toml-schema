# toml-schema
**TOML Obvious Minimal Schema**

The TOML schema defines what type of fields are expected to be in the TOML file.
For example, for the following TOML data file:
```
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
```
The TOML schema would be:
```
title = "string"

[owner]
name = "string"
dob = "offset-date-time"

[database]
enabled = "boolean"
ports = [ "integer" ]
data = [ [ "any-value" ] ]
temp_targets = { cpu = "float", case = "float" }

[servers."*"]
ip = "string"
role = "string"
```

The schema file itself is a TOML file and it is very similar to the TOML data file it defines.
The main difference is that instead of data values, it has the data types as in:
```
[owner]
name = "string"
dob = "offset-date-time"
```
The list of allowed TOML types is:

* `string`
* `float`
* `integer`
* `boolean`
* `offset-date-time`
* `local-date-time`
* `date`
* `time`
* `any-value`

For arrays, the schema is represented with a length one array containing the type of the array data as in:
```
ports = [ "integer" ]
```

Tables with arbitrary keys can be represented with the wildcard symbol `*`.
In the example above the server name is the key of the `servers` table:
```
[servers."*"]
ip = "string"
role = "string"
```
The `any-value` keyword is used to allow any value type.
`any-value` can be any basic type.
It can also be a composite type such as an array or a table.
For example, to specify that any field is allow in the `tool` table of `pyproject.toml` use:
```
[tool."*"]
"*" = "any-value"
```

### Union types

In some cases a value is allowed to have more than one type.
One basic example is allowing numbers to be float or integers:
```
[fruit.apple]
weight = 5

[fruit.banana]
weight = 3.3
```

The schema that defines this TOML is:
```
[fruit.*]
weight = [ "union", "float", "integer" ]
```
In this case, since the first element of the array is the keyword "union",
the array describes a union of allowed types.
These types can also be composite types:
```
complex_number = [
    "union",
    "float",
    "integer",
    { real = "float", imag = "float" },
    { real = "integer", imag = "integer" },
]
```

### Extra options for types

It is also possible to specify extra options for each type.
For example, to specify that an integer value must be positive:
```
score = "integer = { min = 0 }"
```
The string describing the type options should itself be a valid TOML.
Here is the TOML schema defining all valid options:
```
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
ref = "string"
file = "string"
```

- Strings can be limited to a list of enumated values. For example:
```
pixel-color = "enum = ['Red', 'Green', 'Blue']"
```

- Strings can also be specified with a regular expression pattern. For example, to specify that a string can only contain lower case characters:
```
name = "pattern = '^[a-z]+$'"
```

- Integers and floats can have a limited range:
```
discount-percent = "float = { min = 0.0, max = 100.0 }"
```

- `ref` is used to reference other components defined in the schema. For example:
```
["def = { hidden = true }"]
number = [ "union", "float", "integer" ]
complex = [
    "union",
    "ref = 'def.number'",
    { real = "ref = 'def.number'", imag = "ref = 'def.number'" },
]

[quantum]
wave-function = "ref = 'def.complex'"
```

- `file` is used to reference other TOML schema files. The file path should always be relative to the main TOML file. Here is a minimal example:

    `user.toml-schema`:
    ```
    name = "string"
    ```

    `main.toml-schema`:
    ```
    user = "file = 'user.toml-schema'"
    ```

    `main.toml`:
    ```
    user.name = "John"
    ```

### Extra options for keys

It is also possible to specify options for the keys of a table. For example, to specify that the "owner" key is required in the root table and that the "name" key is required in the "owner" table, use:
```
["owner = { required = true }"]
"name = { required = true }" = "string"
dob = "date"
```

The `hidden` flag is used to hide keys in the schema. The standard use case is to hide the definition table `[def]` that is used internally in the scheam but should not be used directly in the TOML file.

Key options can also be used to specify wildcard patterns for the keys. For example, to specify that any uppercase key in a table can be an integer, use:
```
"pattern = '^[A-Z]+$'" = "integer"
```

Any key with an "=" in it, is assumed to be a key with options and is required to be a valid TOML. In the odd case where you actually want to have a key with an "=" in your schema you can specify it with a pattern:
```
"pattern = '^hello=world$'" = "string"
```

### Usage:

There is a command-line tool for validating a TOML file with a schema.
For example, to validate the project `pyproject.toml`:
```
$ python3 -m toml_schema examples/pyproject.toml-schema pyproject.toml
TOML schema validated.
```

The code to validate a TOML file in python is:
```
import tomllib
import toml_schema

with open("examples/pyproject.toml-schema", "rb") as schema_file:
    schema = toml_schema.load(schema_file)
with open("pyproject.toml", "rb") as toml_file:
    toml_table: dict[str, toml_schema.TOMLValue] = tomllib.load(toml_file)
try:
    schema.validate(toml_table)
    print("TOML schema validated.")
except toml_schema.SchemaError as ex:
    print(f"TOML validation error: {ex}")
```
