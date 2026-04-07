# qt-animation-editor

[![License](https://img.shields.io/pypi/l/qt-animation-editor.svg?color=green)](https://github.com/brisvag/qt-animation-editor/qt-animation-editor/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/qt-animation-editor.svg?color=green)](https://pypi.org/project/qt-animation-editor)
[![Python Version](https://img.shields.io/pypi/pyversions/qt-animation-editor.svg?color=green)](https://python.org)
[![CI](https://github.com/brisvag/qt-animation-editor/qt-animation-editor/actions/workflows/ci.yml/badge.svg)](https://github.com/brisvag/qt-animation-editor/qt-animation-editor/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/brisvag/qt-animation-editor/qt-animation-editor/branch/main/graph/badge.svg)](https://codecov.io/gh/brisvag/qt-animation-editor/qt-animation-editor)

Package description.

## Development

The easiest way to get started is to use the [github cli](https://cli.github.com)
and [uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
gh repo fork brisvag/qt-animation-editor/qt-animation-editor --clone
# or just
# gh repo clone brisvag/qt-animation-editor/qt-animation-editor
cd qt-animation-editor
uv sync
```

Run tests:

```sh
uv run pytest
```

Lint files:

```sh
uv run pre-commit run --all-files
```
