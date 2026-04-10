"""Core data models: Keyframe, Track, and Animation."""

from __future__ import annotations

import dataclasses
import itertools
import warnings
from enum import Enum
from typing import Annotated, Any, ClassVar, Literal

from psygnal import Signal
from psygnal._evented_model import EventedModel
from psygnal.containers import EventedList, EventedSet
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_extra_types.color import Color

from qt_animation_timeline.easing import EasingFunction, _is_model_or_dataclass


class PlayMode(int, Enum):
    NORMAL = 0
    LOOP = 1
    PINGPONG = 2


_UNSET = object()


def _to_dict(obj: Any) -> dict[str, Any]:
    # must make a copy to not change the original value
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict") and hasattr(obj, "__fields__"):
        return obj.dict()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
    warnings.warn(
        f"object of type {type(obj)} could not be converted to dict.", stacklevel=2
    )
    return {}


def _update_model_inplace(target: Any, data: dict) -> None:
    """Update a model/dataclass inplace from the given data."""
    if hasattr(target, "update") and callable(target.update):
        target.update(data)
        return

    for key, val in data.items():
        missing = object()
        field = getattr(target, key, missing)
        try:
            if (
                field is not missing
                and _is_model_or_dataclass(field)
                and _is_model_or_dataclass(val)
            ):
                _update_model_inplace(field, val)
            else:
                setattr(target, key, val)
        except (AttributeError, TypeError):
            warnings.warn(f"setting values to {target} failed", stacklevel=2)
            pass


class Keyframe(BaseModel):
    """A keyframe: time position, value, and easing for the segment after it."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    t: Annotated[int, Field(ge=0)] = 0
    value: Any = None
    easing: EasingFunction = EasingFunction.Linear

    @field_validator("value", mode="before")
    @classmethod
    def _models2dict(cls, value):
        # this is crucial to store just the values of the model
        # and not the model itself. Interpolation will then work
        # without updating the original model.
        if _is_model_or_dataclass(value):
            return _to_dict(value)
        return value

    def __hash__(self):
        """Needed to ensure unique t in sets."""
        return hash((Keyframe, self.t))


class Track(BaseModel):
    """A named, colored animation track holding a set of keyframes."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    name: str
    color: Color = Color((180, 180, 180))
    keyframes: EventedSet = Field(default_factory=EventedSet)

    def add_keyframe(
        self,
        t: int,
        value: Any = 0,
        easing: EasingFunction = EasingFunction.Linear,
    ) -> Keyframe:
        """Add a keyframe at frame t."""
        kf = Keyframe(t=t, value=value, easing=easing)
        if kf in self.keyframes:
            raise KeyError(
                f'keyframe at frame {t} already exists in track "{self.name}"'
            )
        self.keyframes.add(kf)
        return kf

    def remove_keyframe(
        self,
        kf_or_t: Keyframe | int,
    ) -> Keyframe:
        if isinstance(kf_or_t, int):
            t = kf_or_t
            for kf in self.keyframes:
                if kf.t == t:
                    break
            else:
                raise KeyError(f"keyframe at frame {t} does not exist")
        else:
            kf = kf_or_t
        self.keyframes.remove(kf)
        return kf

    def sorted(self) -> list[Keyframe]:
        return sorted(self.keyframes, key=lambda kf: kf.t)


class Animation(EventedModel):
    """Runtime state of an animation timeline."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    track_options: dict[str, tuple[Any, str]] = Field(default_factory=dict)
    tracks: EventedList[Track] = Field(default_factory=EventedList)

    current_frame: Annotated[int, Field(ge=0)] = 0
    playing: bool = False
    play_mode: PlayMode = PlayMode.NORMAL
    play_direction: Literal[-1, 1] = 1
    play_fps: Annotated[int, Field(gt=0)] = 30

    keyframes_added: ClassVar[Signal] = Signal(list)
    keyframes_removed: ClassVar[Signal] = Signal(list)
    keyframes_moved: ClassVar[Signal] = Signal(list)
    easing_changed: ClassVar[Signal] = Signal(list)

    def __init__(
        self,
        **data: Any,
    ) -> None:
        super().__init__(**data)
        self.events.current_frame.connect(self._update_bound_models)

    def get_track(self, name: str) -> Track | None:
        for track in self.tracks:
            if track.name == name:
                return track
        return None

    def add_track(self, name: str, color: Color | None = None) -> Track:
        """Add a new track."""
        if name not in self.track_options:
            raise KeyError(
                f"Track {name} is not allowed. Options are: {tuple(self.track_options)}"
            )
        track = self.get_track(name)
        if track is not None:
            raise KeyError(f"Track {name} already exists.")
        track = Track(name=name, color=color or Color((180, 180, 180)))
        self.tracks.append(track)
        return track

    def remove_track(self, name: str) -> None:
        """Remove *track*."""
        track = self.get_track(name)
        if track is None:
            raise KeyError(f"Track {name} does not exist.")
        self.tracks.remove(track)

    def rename_track(self, old_name: str, new_name: str) -> None:
        """Rename a track option key and any existing track with that name."""
        if old_name == new_name:
            return
        if old_name in self.track_options:
            self.track_options[new_name] = self.track_options.pop(old_name)

        track = self.get_track(old_name)
        if track is not None:
            track.name = new_name

    def add_keyframe(
        self,
        track_name: str,
        t: int,
        value: Any = None,
        easing: EasingFunction = EasingFunction.Linear,
    ) -> Keyframe:
        """Add a keyframe to track."""
        track = self.get_track(track_name)
        if track is None:
            raise KeyError(f"Track {track_name} does not exist.")
        kf = track.add_keyframe(t, value, easing)
        self.keyframes_added([kf])
        self._update_bound_models()
        return kf

    def remove_keyframe(
        self,
        track_name: str,
        t: int,
    ) -> Keyframe:
        track = self.get_track(track_name)
        if track is None:
            raise KeyError(f"Track {track_name} does not exist.")
        kf = track.remove_keyframe(t)
        self.keyframes_removed([kf])
        self._update_bound_models()
        return kf

    def remove_keyframes(
        self,
        keyframes: list[Keyframe],
    ) -> None:
        """Bulk removal of keyframes."""
        for kf in keyframes:
            for track in self.tracks:
                if kf in track:
                    track.remove_keyframe(kf)
                    break
            raise KeyError(f"Keyframe {kf} is not part of any track.")
        self.keyframes_removed(keyframes)
        self._update_bound_models()

    def move_keyframes(
        self,
        keyframes: list[Keyframe],
        offset: int,
    ) -> None:
        """Bulk removal of keyframes."""
        for kf in keyframes:
            for track in self.tracks:
                if kf in track:
                    break
            raise KeyError(f"Keyframe {kf} is not part of any track.")
        for kf in keyframes:
            kf.t += offset
        self.keyframes_moved(keyframes)
        self._update_bound_models()

    def cycle_play_mode(self) -> None:
        """Cycle normal -> loop -> pingpong -> normal."""
        self.play_mode = PlayMode((self.play_mode + 1) % 3)
        self.play_direction = 1

    def advance_playhead(self) -> None:
        """Advance one frame according to the current play mode."""
        max_frame = max((kf.t for t in self.tracks for kf in t.keyframes), default=0)
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

    def interpolate_track(self, track: Track, frame: int) -> Any:
        """Return the interpolated value of track at frame, or ``None``.

        Values before the first keyframe and after the last are held constant.
        """
        kfs = track.sorted()
        if not kfs:
            return _UNSET
        if len(kfs) == 1 or frame <= kfs[0].t:
            return kfs[0].value
        if frame >= kfs[-1].t:
            return kfs[-1].value
        for k1, k2 in itertools.pairwise(kfs):
            # note that k1.t and k2.t are guaranteed to be different
            if k1.t <= frame < k2.t:
                span = k2.t - k1.t
                p = (frame - k1.t) / span
                return k1.easing(p, k1.value, k2.value)
        return kfs[-1].value

    def _update_bound_models(self) -> None:
        """Update each bound model field to the interpolated value at frame.

        When the bound field is itself a model/dataclass the interpolated dict
        is applied in-place.
        """
        for track in self.tracks:
            value = self.interpolate_track(track, self.current_frame)
            if value is _UNSET:
                continue

            model, field = self.track_options[track.name]
            original = getattr(model, field)
            if _is_model_or_dataclass(original):
                _update_model_inplace(original, value)
            else:
                setattr(model, field, value)
