# qt-animation-timeline

[![License](https://img.shields.io/pypi/l/qt-animation-timeline.svg?color=green)](https://github.com/brisvag/qt-animation-editor/qt-animation-editor/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/qt-animation-timeline.svg?color=green)](https://pypi.org/project/qt-animation-timeline)
[![Python Version](https://img.shields.io/pypi/pyversions/qt-animation-timeline.svg?color=green)](https://python.org)
[![CI](https://github.com/brisvag/qt-animation-editor/qt-animation-editor/actions/workflows/ci.yml/badge.svg)](https://github.com/brisvag/qt-animation-editor/qt-animation-editor/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/brisvag/qt-animation-editor/qt-animation-editor/branch/main/graph/badge.svg)](https://codecov.io/gh/brisvag/qt-animation-editor/qt-animation-editor)

A blender-style timeline widget for qt to edit animations.

<img width="874" height="166" alt="image" src="https://github.com/user-attachments/assets/abf109b3-68ad-4d0b-876c-c413aa82367e" />

## Usage

The widget is designed to work with dataclass/pydantic style models directly.

```py
from pydantic import BaseModel

class Circle(BaseModel):
    color: tuple[int, int, int] = (255, 0, 0)
    size: float = 10
    filled: bool = True
    other_stuff = ...

circle = Circle()

track_options = {
    'color': (circle, 'color'),
    'size': (circle, 'size')
}

timeline = AnimationTimelineWidget(track_options=track_options)
```

This will allow to animate the color and size, updating the model accordingly when the playhead scrubs along the animation.

When a keyframe is created manually, it will inherit the current model value for the given attribute.

Note that this also works for nested models whenever possible:

```py
class CircleSet(BaseModel):
    circle1: Circle()
    circle2: Circle()

circleset = CircleSet()

track_options = {
    'circle 1': (circleset, 'circle1'),
    'circle 2': (circleset, 'circle2')
}
```

In this case, the whole model is considered the keyframe value, and all its elements will be interpolated.

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
