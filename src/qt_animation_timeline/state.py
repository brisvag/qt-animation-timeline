"""Animation state model -- no Qt dependency.

The ``AnimationState`` class owns the full runtime state of an animation:
track list, current frame, playback mode, and model bindings.  All mutations
emit `psygnal` signals so that any observer (including the Qt widget) can react
without the state itself knowing anything about Qt.

Playback timing (a ``QTimer``) lives in the widget layer; the widget calls
:meth:`AnimationState.advance_playhead` on each tick.
"""

from __future__ import annotations

import dataclasses
import itertools
from typing import Any

import numpy as np
from psygnal import Signal

from qt_animation_timeline.easing import EasingFunction, _coerce_value
from qt_animation_timeline.models import Keyframe, Track

PLAY_NORMAL = 0
PLAY_LOOP = 1
PLAY_PINGPONG = 2

_MISSING = object()


def _is_model_instance(obj: Any) -> bool:
    """Return ``True`` if *obj* is a pydantic model or dataclass instance."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return True
    return hasattr(obj, "model_dump") or (
        hasattr(obj, "dict") and hasattr(obj, "__fields__")
    )


def _apply_model_value(target: Any, source: Any) -> None:
    """Apply pydantic/dataclass field values from *source* to *target* in-place.

    Prefers a user-supplied ``update(dict)`` method.  Falls back to field-by-field
    ``setattr``, skipping computed fields (properties) and recursing into nested
    models.  Frozen models / dataclasses silently ignore unwritable fields.
    """
    if hasattr(source, "model_dump"):
        data = source.model_dump()
    elif hasattr(source, "dict") and hasattr(source, "__fields__"):
        data = source.dict()
    elif dataclasses.is_dataclass(source) and not isinstance(source, type):
        data = {f.name: getattr(source, f.name) for f in dataclasses.fields(source)}
    else:
        return

    if hasattr(target, "update") and callable(getattr(target, "update")):
        target.update(data)
        return

    for key, val in data.items():
        if isinstance(getattr(type(target), key, None), property):
            continue
        existing = getattr(target, key, _MISSING)
        try:
            if existing is not _MISSING and _is_model_instance(existing) and _is_model_instance(val):
                _apply_model_value(existing, val)
            else:
                setattr(target, key, val)
        except (AttributeError, TypeError):
            pass


class _TrackOptionsDict(dict):
    """A ``dict`` subclass that removes orphan tracks when keys are deleted.

    Every mutating operation that removes a key triggers
    ``_cleanup_orphan_tracks()`` on the owning ``AnimationState``.
    """

    __slots__ = ("_state",)

    def __init__(self, data: dict, state: AnimationState) -> None:
        super().__init__(data)
        self._state = state

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self._state._cleanup_orphan_tracks({key})

    def pop(self, *args: Any) -> Any:  # type: ignore[override]
        key = args[0]
        existed = key in self
        result = super().pop(*args)
        if existed:
            self._state._cleanup_orphan_tracks({key})
        return result

    def popitem(self) -> tuple[str, Any]:
        key, val = super().popitem()
        self._state._cleanup_orphan_tracks({key})
        return key, val

    def clear(self) -> None:
        removed = set(self.keys())
        super().clear()
        self._state._cleanup_orphan_tracks(removed)


class AnimationState:
    """Runtime state of an animation timeline.

    Parameters
    ----------
    playback_speed:
        Multiplier applied to playback frame rate.
    track_options:
        Mapping of track name to ``(model_instance, field_name)`` bindings.
        When the playhead moves, each bound field is updated with the
        interpolated track value.  In-place deletions (``del``, ``pop``,
        ``clear``, ``popitem``) automatically remove the matching tracks.
    """

    frame_changed = Signal(int)
    track_added = Signal(object)
    track_removed = Signal(object)
    track_changed = Signal(object)
    keyframe_added = Signal(object, object)
    keyframes_removed = Signal(list)
    keyframes_moved = Signal(list)
    easing_changed = Signal(list)
    playing_changed = Signal(bool)
    play_mode_changed = Signal(int)

    def __init__(
        self,
        *,
        playback_speed: float = 1.0,
        track_options: dict[str, tuple[Any, str]] | None = None,
    ) -> None:
        self._current_frame: int = 0
        self._playing: bool = False
        self._play_mode: int = PLAY_NORMAL
        self._play_direction: int = 1
        self.play_fps: int = 30
        self.playback_speed: float = playback_speed
        self.tracks: list[Track] = []
        self._track_options: _TrackOptionsDict = _TrackOptionsDict(
            track_options if track_options is not None else {}, self
        )

    # ------------------------------------------------------------------
    # track_options property

    @property
    def track_options(self) -> _TrackOptionsDict:
        """Mapping of track name to (model, field) bindings.

        Assigning a new dict replaces the options and removes tracks whose
        names are no longer present.  In-place deletions trigger the same cleanup.
        """
        return self._track_options

    @track_options.setter
    def track_options(self, value: dict[str, tuple[Any, str]]) -> None:
        removed_keys = set(self._track_options) - set(value)
        self._track_options = _TrackOptionsDict(value, self)
        self._cleanup_orphan_tracks(removed_keys)

    def _cleanup_orphan_tracks(self, removed_keys: set[str]) -> None:
        if not removed_keys:
            return
        to_remove = [t for t in self.tracks if t.name in removed_keys]
        for track in to_remove:
            self.tracks.remove(track)
            self.track_removed.emit(track)

    # ------------------------------------------------------------------
    # Properties with change signals

    @property
    def current_frame(self) -> int:
        """Current playhead position (frame number >= 0)."""
        return self._current_frame

    @current_frame.setter
    def current_frame(self, value: int) -> None:
        value = max(0, int(value))
        if value != self._current_frame:
            self._current_frame = value
            self._dispatch_track_callbacks(value)
            self.frame_changed.emit(value)

    @property
    def playing(self) -> bool:
        """``True`` while playback is active."""
        return self._playing

    @playing.setter
    def playing(self, value: bool) -> None:
        if value != self._playing:
            self._playing = value
            self.playing_changed.emit(value)

    @property
    def play_mode(self) -> int:
        """Active play mode: ``PLAY_NORMAL``, ``PLAY_LOOP``, or ``PLAY_PINGPONG``."""
        return self._play_mode

    @play_mode.setter
    def play_mode(self, value: int) -> None:
        if value != self._play_mode:
            self._play_mode = value
            self.play_mode_changed.emit(value)

    # ------------------------------------------------------------------
    # Track management

    def add_track(
        self,
        name: str,
        color: tuple[int, int, int] | None = None,
    ) -> Track:
        """Add a new track and emit :attr:`track_added`."""
        track = Track(name, color)
        self.tracks.append(track)
        self.track_added.emit(track)
        return track

    def remove_track(self, track: Track) -> None:
        """Remove *track* and emit :attr:`track_removed`."""
        if track in self.tracks:
            self.tracks.remove(track)
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
        self._dispatch_track_callbacks(self._current_frame)
        return kf

    def remove_keyframes(self, keyframes: list[Keyframe]) -> None:
        """Remove *keyframes* from their tracks and emit :attr:`keyframes_removed`."""
        kf_set = set(keyframes)
        for track in self.tracks:
            track.keyframes = [kf for kf in track.keyframes if kf not in kf_set]
        if keyframes:
            self.keyframes_removed.emit(list(keyframes))
            self._dispatch_track_callbacks(self._current_frame)

    def notify_keyframes_moved(self, keyframes: list[Keyframe]) -> None:
        """Sort keyframes and emit :attr:`keyframes_moved` after a drag."""
        for track in self.tracks:
            track.keyframes.sort(key=lambda k: k.t)
        self.keyframes_moved.emit(keyframes)
        self._dispatch_track_callbacks(self._current_frame)

    def notify_easing_changed(self, keyframes: list[Keyframe]) -> None:
        """Emit :attr:`easing_changed` and re-dispatch callbacks after easing edit."""
        self.easing_changed.emit(keyframes)
        self._dispatch_track_callbacks(self._current_frame)

    # ------------------------------------------------------------------
    # Playback control

    def cycle_play_mode(self) -> None:
        """Cycle normal -> loop -> pingpong -> normal."""
        self.play_mode = (self._play_mode + 1) % 3
        self._play_direction = 1

    def advance_playhead(self) -> None:
        """Advance one frame according to the current play mode.

        Called by the widget's ``QTimer`` on each tick.
        """
        max_frame = max((kf.t for t in self.tracks for kf in t.keyframes), default=0)
        next_frame = self._current_frame + self._play_direction
        if self._play_mode == PLAY_NORMAL:
            if next_frame > max_frame:
                self.playing = False
                self.current_frame = max_frame
                return
        elif self._play_mode == PLAY_LOOP:
            if next_frame > max_frame:
                next_frame = 0
        elif self._play_mode == PLAY_PINGPONG:
            if next_frame > max_frame:
                self._play_direction = -1
                next_frame = max(0, max_frame - 1)
            elif next_frame < 0:
                self._play_direction = 1
                next_frame = min(1, max_frame)
        self.current_frame = next_frame

    # ------------------------------------------------------------------
    # Track option helpers

    def _can_add_track(self) -> bool:
        """Return ``True`` if at least one unused track option slot exists.

        When ``track_options`` is empty there are no options to choose from,
        so no tracks can be added via the popup.
        """
        if not self.track_options:
            return False
        used = {t.name for t in self.tracks}
        return len(used) < len(self.track_options)

    def available_track_options(self) -> list[str]:
        """Return track option names that are not yet used by any track."""
        used = {t.name for t in self.tracks}
        return [name for name in self.track_options if name not in used]

    # ------------------------------------------------------------------
    # Interpolation and model dispatch

    def interpolate_track(self, track: Track, frame: int) -> Any | None:
        """Return the interpolated value of *track* at *frame*, or ``None`` if empty.

        Values before the first keyframe and after the last are held constant.
        ``list``/``tuple`` values are converted to numpy arrays for arithmetic
        and cast back by :func:`_coerce_value` during dispatch.
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
                if isinstance(v1, (list, tuple)) or isinstance(v2, (list, tuple)):
                    v1 = np.asarray(v1, dtype=float)
                    v2 = np.asarray(v2, dtype=float)
                return k1.easing(p, v1, v2)
        return kfs[-1].value

    def _dispatch_track_callbacks(self, frame: int) -> None:
        """Set each bound model field to the interpolated track value at *frame*.

        For pydantic models and dataclasses the value is applied in-place via
        :func:`_apply_model_value` rather than replaced wholesale.
        """
        for track in self.tracks:
            binding = self.track_options.get(track.name)
            if binding is None:
                continue
            model, field = binding
            value = self.interpolate_track(track, frame)
            if value is None:
                continue
            reference = getattr(model, field)
            if _is_model_instance(reference):
                if _is_model_instance(value):
                    _apply_model_value(reference, value)
            else:
                setattr(model, field, _coerce_value(reference, value))
