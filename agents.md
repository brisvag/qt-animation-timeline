# agents.md

Quick reference for agents working on this repo.

## What it is

A Blender-style Qt animation timeline widget (`AnimationTimelineWidget`) that lets users scrub a playhead over named tracks of keyframes and automatically interpolates bound model fields (pydantic, dataclasses, or plain objects).

## Repo layout

```
src/qt_animation_timeline/
    __init__.py      # public API: Animation, AnimationTimelineWidget, EasingFunction, Keyframe, Track
    models.py        # Animation (EventedModel), Track, Keyframe, interpolation helpers
    easing.py        # EasingFunction enum (Linear, Step), _coerce_value
    editor.py        # AnimationTimelineWidget — single QWidget, all painting + events
examples/demo.py     # runnable demo (python examples/demo.py)
tests/test_qt_animation_timeline.py
```

## Key concepts

- **`Animation`** (`psygnal.EventedModel`): all runtime state. Scalar fields (`current_frame`, `playing`, `play_mode`, `play_fps`, `playback_speed`) emit via `animation.events.<name>`. Structural changes (tracks, keyframes) use explicit `ClassVar[Signal]` attributes.
- **`track_options`**: `dict[str, tuple[model, field_name]]` — maps a track name to the object attribute it drives. Setting or deleting keys automatically removes orphan tracks.
- **`AnimationTimelineWidget`**: wraps `Animation` as `widget.state`; forwards all signals. Most state lives in `state`, widget holds only rendering/interaction state (scroll, drag flags, etc.).
- **Interpolation**: `Animation.interpolate_track(track, frame)` → scalar, list/tuple, or dict for model values. `str` and `bool` values always use `Step`. Keyframe values that are pydantic models/dataclasses are stored as static dicts at creation time.
- **Easing**: only `Linear` and `Step` exist. Easings are per-keyframe (govern the segment *after* that keyframe).

## Development commands

```sh
uv sync                  # install deps
uv run pytest            # run tests (uses offscreen Qt)
prek --all-files         # lint (ruff check + ruff format + typos)
python examples/demo.py  # visual demo
```

## Code style

- `ruff` for formatting and linting (line length 88, target py310). Prefer running `prek` to fix issues rather than editing manually.
- `from __future__ import annotations` at top of every source file.
- No section-header comments or self-evident inline comments. Doc comments use numpy-style docstrings.
- Short private helpers prefixed with `_`.
- Tests: pytest, offscreen Qt (`os.environ["QT_QPA_PLATFORM"] = "offscreen"`), session-scoped `qapp` fixture. Each test is self-contained (creates its own widget). No mocking — prefer direct attribute/signal inspection. Keep tests minimal and concise.
- Follow pydantic v2 conventions (`model_dump`, `ConfigDict`, `field_validator`, etc.).
- Commits follow conventional commits (`fix:`, `feat:`, `refactor:`, `ci:`, `docs:`). Make atomic commits — prefer smaller self-sufficient commits over one large one. If tests break due to an unrelated pre-existing issue, commit the code change first and fix tests separately.

## Common patterns

**Adding a track programmatically:**
```python
timeline = AnimationTimelineWidget(track_options={"x": (obj, "x")})
timeline.add_track("x")
timeline.tracks[0].add_keyframe(0, value=0.0)
timeline.tracks[0].add_keyframe(100, value=10.0)
```

**Listening to events:**
```python
timeline.playhead_moved.connect(lambda frame: ...)
timeline.keyframes_moved.connect(lambda kfs: ...)
# or on the model directly:
timeline.state.events.current_frame.connect(lambda f: ...)
```

**Model binding (pydantic/dataclass/plain object):**
```python
track_options = {"pos": (model, "pos"), "whole_obj": (holder, "light")}
# Scalar fields: coerced to reference type (int rounds, bool stays bool).
# Model/dataclass fields: updated in-place field-by-field.
```
