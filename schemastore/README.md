# schemastore

JSON schemas for TOML files copied from schemastore and setuptools.  Assuming that these projects have up-to-date git clone under `$HOME/git`, they can be synchronized using:
```
cd schemastore  # Switch to this folder
for f in *.json; do cp ~/git/schemastore/src/schemas/json/$f $f; done
cp ~/git/setuptools/setuptools/config/setuptools.schema.json partial-setuptools.json
```

TOML schemas can be generated from these JSON schemas using:
```
cd ..
tox -e schemastore
```
