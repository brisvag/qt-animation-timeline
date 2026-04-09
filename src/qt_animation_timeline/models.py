"""Core data models: Keyframe, Track, and Animation."""

from __future__ import annotations

import dataclasses
import itertools
from enum import Enum
from typing import Any, ClassVar

import numpy as np
from psygnal import Signal
from psygnal._evented_model import EventedModel
from pydantic import ConfigDict, field_validator

from qt_animation_timeline.easing import EasingFunction, _coerce_value


class PlayMode(int, Enum):
    NORMAL = 0
    LOOP = 1
    PINGPONG = 2


_MISSING = object()


# ---------------------------------------------------------------------------
# Helpers for dataclass / pydantic model dispatch


def _is_model_or_dataclass(obj: Any) -> bool:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return True
    return hasattr(obj, "model_dump") or (
        hasattr(obj, "dict") and hasattr(obj, "__fields__")
    )


def _to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict") and hasattr(obj, "__fields__"):
        return obj.dict()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
    return {}


def _interpolate_field(easing: EasingFunction, p: float, v1: Any, v2: Any) -> Any:
    """Interpolate between *v1* and *v2* using *easing*, falling back to Step."""
    if easing is not EasingFunction.Linear:
        return easing(p, v1, v2)
    # str values must never be cast to numbers; always use Step regardless of easing.
    if isinstance(v1, str) or isinstance(v2, str):
        return EasingFunction.Step(p, v1, v2)
    try:
        v1n = np.asarray(v1, dtype=float) if isinstance(v1, (list, tuple)) else v1
        v2n = np.asarray(v2, dtype=float) if isinstance(v2, (list, tuple)) else v2
        return EasingFunction.Linear(p, v1n, v2n)
    except (TypeError, ValueError):
        return EasingFunction.Step(p, v1, v2)


def _interpolate_model(
    easing: EasingFunction, p: float, m1: Any, m2: Any
) -> dict[str, Any]:
    """Return a dict of per-field interpolated values between two models or dicts."""
    f1 = _to_dict(m1)
    f2 = _to_dict(m2)
    return {
        name: _interpolate_field(easing, p, f1[name], f2[name])
        for name in f1
        if name in f2
    }


def _apply_model_value(target: Any, source: Any) -> None:
    """Apply field values from *source* (dict or model) to *target* in-place."""
    data = source if isinstance(source, dict) else _to_dict(source)
    if not data:
        return

    if hasattr(target, "update") and callable(target.update):
        target.update(data)
        return

    for key, val in data.items():
        if isinstance(getattr(type(target), key, None), property):
            continue
        existing = getattr(target, key, _MISSING)
        try:
            if (
                existing is not _MISSING
                and _is_model_or_dataclass(existing)
                and _is_model_or_dataclass(val)
            ):
                _apply_model_value(existing, val)
            else:
                setattr(target, key, val)
        except (AttributeError, TypeError):
            pass


# ---------------------------------------------------------------------------
# _TrackOptionsDict — auto-cleanup on deletion


class _TrackOptionsDict(dict):
    """dict subclass that removes orphan tracks when keys are deleted."""

    __slots__ = ("_animation",)

    def __init__(self, data: dict, animation: Animation) -> None:
        super().__init__(data)
        self._animation = animation

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self._animation._cleanup_orphan_tracks({key})

    def pop(self, *args: Any) -> Any:  # type: ignore[override]
        key = args[0]
        existed = key in self
        result = super().pop(*args)
        if existed:
            self._animation._cleanup_orphan_tracks({key})
        return result

    def popitem(self) -> tuple[str, Any]:
        key, val = super().popitem()
        self._animation._cleanup_orphan_tracks({key})
        return key, val

    def clear(self) -> None:
        removed = set(self.keys())
        super().clear()
        self._animation._cleanup_orphan_tracks(removed)


# ---------------------------------------------------------------------------
# Keyframe and Track


class Keyframe:
    """A keyframe: time position, value, and easing for the segment after it."""

    def __init__(
        self,
        t: int,
        value: Any = 0,
        easing: EasingFunction = EasingFunction.Linear,
    ) -> None:
        self.t = max(0, int(t))
        self.value = _to_dict(value) if _is_model_or_dataclass(value) else value
        self.easing = easing


class Track:
    """A named animation track holding an ordered list of keyframes.

    Parameters
    ----------
    name:
        Display name for the track.
    color:
        RGB colour as an ``(r, g, b)`` tuple.  Defaults to ``(180, 180, 180)``.
    """

    def __init__(self, name: str, color: tuple[int, int, int] | None = None) -> None:
        self.name = name
        self.color: tuple[int, int, int] = color or (180, 180, 180)
        self.keyframes: list[Keyframe] = []

    def add_keyframe(
        self,
        t: int,
        value: Any = 0,
        easing: EasingFunction = EasingFunction.Linear,
    ) -> Keyframe:
        """Add a keyframe at frame *t*, raising `KeyError` if one already exists."""
        t = max(0, int(t))
        for kf in self.keyframes:
            if kf.t == t:
                msg = f'keyframe at frame {t} already exists in track "{self.name}"'
                raise KeyError(msg)
        kf = Keyframe(t, value, easing)
        self.keyframes.append(kf)
        self.keyframes.sort(key=lambda k: k.t)
        return kf


# ---------------------------------------------------------------------------
# Animation — EventedModel


class Animation(EventedModel):
    """Runtime state of an animation timeline.

    Scalar properties (``current_frame``, ``playing``, ``play_mode``,
    ``play_direction``, ``play_fps``, ``playback_speed``) are pydantic fields;
    assigning them auto-emits the corresponding signal on ``animation.events``.

    Structural changes (tracks, keyframes) emit the class-level ``Signal``
    attributes (``track_added``, ``track_removed``, etc.).

    Parameters
    ----------
    playback_speed:
        Multiplier applied to the playback frame rate.
    track_options:
        Mapping of track name to ``(model_instance, field_name)`` bindings.
        When the playhead moves, each bound field is updated with the
        interpolated track value.  In-place deletions (``del``, ``pop``,
        ``clear``, ``popitem``) automatically remove the matching tracks.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    # Evented scalar fields — signals auto-emitted via .events.<name>
    current_frame: int = 0
    playing: bool = False
    play_mode: PlayMode = PlayMode.NORMAL
    play_direction: int = 1
    play_fps: int = 30
    playback_speed: float = 1.0

    # Structural-change signals (not auto-generated by EventedModel)
    track_added: ClassVar[Signal] = Signal(object)
    track_removed: ClassVar[Signal] = Signal(object)
    track_changed: ClassVar[Signal] = Signal(object)
    keyframe_added: ClassVar[Signal] = Signal(object, object)
    keyframes_removed: ClassVar[Signal] = Signal(list)
    keyframes_moved: ClassVar[Signal] = Signal(list)
    easing_changed: ClassVar[Signal] = Signal(list)

    @field_validator("current_frame", mode="before")
    @classmethod
    def _clamp_frame(cls, v: Any) -> int:
        """Clamp frame to >= 0."""
        return max(0, int(v))

    def __init__(
        self,
        *,
        playback_speed: float = 1.0,
        track_options: dict[str, tuple[Any, str]] | None = None,
        **data: Any,
    ) -> None:
        super().__init__(playback_speed=playback_speed, **data)
        # Non-pydantic mutable state — set after super().__init__ so validators
        # don't interfere, and before connecting signals so initial dispatch works.
        object.__setattr__(self, "tracks", [])
        object.__setattr__(
            self,
            "_track_options",
            _TrackOptionsDict(track_options or {}, self),
        )
        # Dispatch callbacks whenever the playhead moves.
        self.events.current_frame.connect(self._dispatch_track_callbacks)

    # ------------------------------------------------------------------
    # track_options property

    @property
    def track_options(self) -> _TrackOptionsDict:
        """Mapping of track name to (model, field) bindings.

        Assigning a new dict replaces the options and removes tracks whose
        names are no longer present.  In-place deletions trigger the same cleanup.
        """
        return self._track_options  # type: ignore[attr-defined]

    @track_options.setter
    def track_options(self, value: dict[str, tuple[Any, str]]) -> None:
        removed_keys = set(self._track_options) - set(value)  # type: ignore[attr-defined]
        object.__setattr__(self, "_track_options", _TrackOptionsDict(value, self))
        self._cleanup_orphan_tracks(removed_keys)

    def _cleanup_orphan_tracks(self, removed_keys: set[str]) -> None:
        if not removed_keys:
            return
        tracks: list[Track] = self.tracks  # type: ignore[attr-defined]
        to_remove = [t for t in tracks if t.name in removed_keys]
        for track in to_remove:
            tracks.remove(track)
            self.track_removed.emit(track)

    # ------------------------------------------------------------------
    # Track management

    def add_track(self, name: str, color: tuple[int, int, int] | None = None) -> Track:
        """Add a new track and emit :attr:`track_added`."""
        track = Track(name, color)
        self.tracks.append(track)  # type: ignore[attr-defined]
        self.track_added.emit(track)
        return track

    def remove_track(self, track: Track) -> None:
        """Remove *track* and emit :attr:`track_removed`."""
        tracks: list[Track] = self.tracks  # type: ignore[attr-defined]
        if track in tracks:
            tracks.remove(track)
            self.track_removed.emit(track)

    def rename_track(self, track: Track, name: str) -> None:
        """Rename *track* and emit :attr:`track_changed`."""
        track.name = name
        self.track_changed.emit(track)

    def add_keyframe(
        self,
        track: Track,
        t: int,
        value: Any = 0,
        easing: EasingFunction = EasingFunction.Linear,
    ) -> Keyframe:
        """Add a keyframe to *track* and emit :attr:`keyframe_added`."""
        kf = track.add_keyframe(t, value, easing)
        self.keyframe_added.emit(track, kf)
        self._dispatch_track_callbacks(self.current_frame)
        return kf

    def remove_keyframes(self, keyframes: list[Keyframe]) -> None:
        """Remove *keyframes* from their tracks and emit :attr:`keyframes_removed`."""
        kf_set = set(keyframes)
        for track in self.tracks:  # type: ignore[attr-defined]
            track.keyframes = [kf for kf in track.keyframes if kf not in kf_set]
        if keyframes:
            self.keyframes_removed.emit(list(keyframes))
            self._dispatch_track_callbacks(self.current_frame)

    def notify_keyframes_moved(self, keyframes: list[Keyframe]) -> None:
        """Sort keyframes and emit :attr:`keyframes_moved` after a drag."""
        for track in self.tracks:  # type: ignore[attr-defined]
            track.keyframes.sort(key=lambda k: k.t)
        self.keyframes_moved.emit(keyframes)
        self._dispatch_track_callbacks(self.current_frame)

    def notify_easing_changed(self, keyframes: list[Keyframe]) -> None:
        """Emit :attr:`easing_changed` and re-dispatch callbacks."""
        self.easing_changed.emit(keyframes)
        self._dispatch_track_callbacks(self.current_frame)

    # ------------------------------------------------------------------
    # Playback

    def cycle_play_mode(self) -> None:
        """Cycle normal -> loop -> pingpong -> normal."""
        self.play_mode = PlayMode((self.play_mode + 1) % 3)
        self.play_direction = 1

    def advance_playhead(self) -> None:
        """Advance one frame according to the current play mode.

        Called by the widget's ``QTimer`` on each tick.
        """
        tracks: list[Track] = self.tracks  # type: ignore[attr-defined]
        max_frame = max((kf.t for t in tracks for kf in t.keyframes), default=0)
        next_frame = self.current_frame + self.play_direction
        if self.play_mode == PlayMode.NORMAL:
            if next_frame > max_frame:
                self.playing = False
                self.current_frame = max_frame
                return
        elif self.play_mode == PlayMode.LOOP:
            if next_frame > max_frame:
                next_frame = 0
        elif self.play_mode == PlayMode.PINGPONG:
            if next_frame > max_frame:
                self.play_direction = -1
                next_frame = max(0, max_frame - 1)
            elif next_frame < 0:
                self.play_direction = 1
                next_frame = min(1, max_frame)
        self.current_frame = next_frame

    # ------------------------------------------------------------------
    # Track option helpers

    def _can_add_track(self) -> bool:
        """Return ``True`` if at least one unused track option slot exists."""
        return bool(self.available_track_options())

    def available_track_options(self) -> list[str]:
        """Return track option names not yet used by any track."""
        tracks: list[Track] = self.tracks  # type: ignore[attr-defined]
        used = {t.name for t in tracks}
        return [name for name in self.track_options if name not in used]

    # ------------------------------------------------------------------
    # Interpolation and model dispatch

    def interpolate_track(self, track: Track, frame: int) -> Any | None:
        """Return the interpolated value of *track* at *frame*, or ``None``.

        Values before the first keyframe and after the last are held constant.
        When keyframe values are dataclass or pydantic model instances the
        interpolation is done field-by-field via :func:`_interpolate_model`,
        with automatic ``Step`` fallback for non-numeric fields.
        """
        kfs = track.keyframes
        if not kfs:
            return None
        if len(kfs) == 1 or frame <= kfs[0].t:
            return kfs[0].value
        if frame >= kfs[-1].t:
            return kfs[-1].value
        for k1, k2 in itertools.pairwise(kfs):
            if k1.t <= frame < k2.t:
                span = k2.t - k1.t
                if span == 0:
                    return k2.value
                p = (frame - k1.t) / span
                v1, v2 = k1.value, k2.value
                if (
                    _is_model_or_dataclass(v1)
                    or _is_model_or_dataclass(v2)
                    or (isinstance(v1, dict) and isinstance(v2, dict))
                ):
                    return _interpolate_model(k1.easing, p, v1, v2)
                if isinstance(v1, (list, tuple)) or isinstance(v2, (list, tuple)):
                    v1 = np.asarray(v1, dtype=float)
                    v2 = np.asarray(v2, dtype=float)
                return _interpolate_field(k1.easing, p, v1, v2)
        return kfs[-1].value

    def _dispatch_track_callbacks(self, frame: int) -> None:
        """Update each bound model field to the interpolated value at *frame*.

        When the bound field is itself a model/dataclass the interpolated dict
        is applied in-place via :func:`_apply_model_value` rather than replaced.
        """
        tracks: list[Track] = self.tracks  # type: ignore[attr-defined]
        for track in tracks:
            binding = self.track_options.get(track.name)
            if binding is None:
                continue
            model, field = binding
            value = self.interpolate_track(track, frame)
            if value is None:
                continue
            reference = getattr(model, field)
            if _is_model_or_dataclass(reference):
                _apply_model_value(reference, value)
            else:
                setattr(model, field, _coerce_value(reference, value))
