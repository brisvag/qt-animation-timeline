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
uv sync                         # install deps
uv run pytest                   # run tests (uses offscreen Qt)
uv run pre-commit run --all-files  # lint (ruff check + ruff format + typos)
python examples/demo.py         # visual demo
```

## Code style

- `ruff` for formatting and linting (line length 88, target py310). Run before committing.
- `from __future__ import annotations` at top of every source file.
- Section headers as `# ------------------------------------------------------------------` comments.
- Short private helpers prefixed with `_`. Internal flags like `_dragging_keyframes` / `_track_moved` are plain `bool` attributes on the widget.
- No inline comments for obvious code; doc comments use numpy-style docstrings.
- Tests: pytest, offscreen Qt (`os.environ["QT_QPA_PLATFORM"] = "offscreen"`), session-scoped `qapp` fixture. Each test is self-contained (creates its own widget). No mocking — prefer direct attribute/signal inspection.
- Commits follow conventional commits (`fix:`, `feat:`, `refactor:`, `ci:`, `docs:`).

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

## Things to watch out for

- `tracks` and `_track_options` are set via `object.__setattr__` in `Animation.__init__` to bypass pydantic validation — don't try to declare them as pydantic fields.
- `mouseReleaseEvent` must guard `notify_keyframes_moved` with the `_track_moved` / `_dragging_keyframes` flags; calling it unconditionally overwrites model state (see PR #12).
- `_get_allowed_easings_for_track` restricts `bool` and `str` fields to `Step` only — keep that in sync if new types are added.
- `_TrackOptionsDict` overrides `__delitem__`, `pop`, `popitem`, `clear` to trigger orphan-track cleanup; don't bypass it.
- Widget `add_track` picks the next color from `track_color_cycle` (cycles round-robin); track color is stored as an `(r, g, b)` tuple on `Track`.
