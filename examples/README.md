# TOML example files

TOML examples copied from other projects. Assuming that these projects have up-to-date git clone under `$HOME/git`, they can be synchronized using:
```
cd examples  # Switch to this folder
rsync -av ~/git/validate-pyproject/tests/examples/ validate-pyproject/
rsync -av ~/git/validate-pyproject/tests/invalid-examples/ validate-pyproject-invalid/
rsync -av ~/git/schemastore/src/test/pyproject/ schemastore/pyproject/
rsync -av ~/git/schemastore/src/negative_test/pyproject/ schemastore-negative-test/pyproject/
```

Delete redundant JSON files and error message files:
```
find . -name "*.json" -delete
find . -name "*.errors.txt" -delete
```

The example in `schemastore-negative-test` is from https://packaging.python.org/en/latest/guides/writing-pyproject-toml/.

Then the error message files need to be updated by setting `WRITE_ERROR_FILES = True` in`tests/test_pyproject_schema.py`, running the test:
```
cd ..
tox -e py313
```
and then setting back `WRITE_ERROR_FILES = False`.
