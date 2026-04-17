"""Core data models: Keyframe, Track, and Animation."""

from __future__ import annotations

import dataclasses
import itertools
import logging
import warnings
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from psygnal import Signal
from psygnal._evented_model import EventedModel
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from qt_animation_timeline.easing import EasingFunction, _is_collection

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)


class PlayMode(int, Enum):
    NORMAL = 0
    LOOP = 1
    PINGPONG = 2


_UNSET = object()


def _nested_to_dict(obj):
    if isinstance(obj, dict):
        return {k: _nested_to_dict(v) for k, v in obj.items()}
    elif _is_model_container(obj):
        return [_nested_to_dict(el) for el in obj]
    return _to_dict(obj)


def _to_dict(obj: Any) -> dict[str, Any]:
    d = None
    # must make a copy to not change the original value
    if isinstance(obj, dict):
        d = dict(obj)
    elif hasattr(obj, "model_dump"):
        d = obj.model_dump()
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        d = {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
    elif hasattr(obj, "dict"):
        d = obj.dict()
    # special napari case. TODO: make it use dict in napari?
    with warnings.catch_warnings():
        warnings.filterwarnings(action="ignore", message="Private attribute")
        if d is None and hasattr(obj, "_get_state"):
            d = obj._get_state()
    # again special case: model_dump should be recursive, but napari
    # returns whole layers from containers (cause they're not models)
    if d is not None:
        return _nested_to_dict(d)

    return obj


def _is_model_or_dataclass(obj: Any) -> bool:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return True
    if hasattr(obj, "model_dump") or (
        hasattr(obj, "dict") and hasattr(obj, "__fields__")
    ):
        return True
    # special napari case for non-model models (ugh)
    with warnings.catch_warnings():
        warnings.filterwarnings(action="ignore", message="Private attribute")
        if hasattr(obj, "_get_state"):
            return True
    return False


def _is_frozen_field(obj: Any, field: str) -> bool:
    if dataclasses.is_dataclass(obj) and obj.__dataclass_params__.frozen:
        return True
    if hasattr(obj, "model_config") and obj.model_config.get("frozen", False):
        return True
    if hasattr(obj, "model_fields") and obj.model_fields[field].frozen:
        return True
    return False


def _is_model_container(obj: Any) -> bool:
    return _is_collection(obj) and all(
        _is_model_container(el) or _is_model_or_dataclass(el) for el in obj
    )


def _update_container_models(obj: Iterable, data: Iterable):
    try:
        for el_old, el_new in zip(obj, data, strict=True):
            _update_model_inplace(el_old, el_new)
    except ValueError as e:
        if e.args and "zip() argument" in e.args[0]:
            # different number of elements. Just give up.
            logger.info(
                "%s and %s have different lengths. Cannot update.", el_old, el_new
            )
        else:
            raise e


def _update_model_inplace(target: Any, data: dict) -> None:
    """Update a model/dataclass inplace from the given data."""
    data_copy = data.copy()
    update_method = getattr(target, "update", None)
    for key in data:
        missing = object()
        current = getattr(target, key, missing)
        if current is missing:
            raise KeyError(f'Field "{current}" is missing from {target}.')

        try:
            if _is_frozen_field(target, key):
                # frozen fields cannot be handled by update method,
                # so just attempt to update inplace directly and remove
                # from the dict
                # TODO: this can be simplified if we handle frozen fields
                #       better in napari within update()
                new_val = data_copy.pop(key)
                if _is_model_or_dataclass(current):
                    _update_model_inplace(current, new_val)
                elif _is_model_container(current):
                    _update_container_models(current, new_val)
                # if it's neither a model nor a container of models, leave it alone
            elif update_method is None:
                new_val = data_copy.pop(key)
                setattr(target, key, new_val)
        except (AttributeError, TypeError) as e:
            warnings.warn(f"setting values to {target} failed:\n{e}", stacklevel=2)
            pass

    if update_method is not None:
        update_method(data_copy)


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


class Track(BaseModel):
    """A named animation track holding a set of keyframes."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    name: str
    keyframes: list[Keyframe] = Field(default_factory=list)

    def add_keyframe(
        self,
        t: int,
        value: Any = 0,
        easing: EasingFunction = EasingFunction.Linear,
    ) -> Keyframe:
        """Add a keyframe at frame t."""
        for kf in self.keyframes:
            if kf.t == t:
                raise KeyError(
                    f'keyframe at frame {t} already exists in track "{self.name}"'
                )
        kf = Keyframe(t=t, value=value, easing=easing)
        self.keyframes.append(kf)
        self.keyframes.sort(key=lambda kf: kf.t)
        return kf

    def _get_kf(self, kf_or_t: int | Keyframe) -> Keyframe:
        if isinstance(kf_or_t, int):
            t = kf_or_t
            for kf in self.keyframes:
                if kf.t == t:
                    return kf
            else:
                raise KeyError(f"keyframe at frame {t} does not exist")
        else:
            kf = kf_or_t
            if kf not in self.keyframes:
                raise KeyError(f'keyframe {kf} is not part of track "{self.name}s"')
            return kf

    def remove_keyframe(
        self,
        kf_or_t: Keyframe | int,
    ) -> Keyframe:
        kf = self._get_kf(kf_or_t)
        self.keyframes.remove(kf)
        return kf

    def move_keyframe(
        self,
        kf_or_t: Keyframe | int,
        offset: int,
    ) -> Keyframe:
        kf = self._get_kf(kf_or_t)
        new_t = max(0, kf.t + offset)
        for kf_ in self.keyframes:
            if new_t == kf_.t:
                raise KeyError(
                    f"cannot move keyframe {kf} to {new_t}: frame is occupied."
                )
        kf.t = new_t
        self.keyframes.sort(key=lambda kf: kf.t)
        return kf


def _resolve_attr_path(source: Any, path: str) -> tuple[Any, str]:
    while True:
        attr, _, path = path.partition(".")
        if not path:
            return source, attr
        source = getattr(source, attr)


class AnimationTimeline(EventedModel):
    """Runtime state of an animation timeline."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    track_options: dict[str, tuple[Any, str]] = Field(default_factory=dict)
    tracks: dict[str, Track] = Field(default_factory=dict)

    current_frame: Annotated[int, Field(ge=0)] = 0
    play_mode: PlayMode = PlayMode.NORMAL
    play_fps: Annotated[int, Field(gt=0)] = 30

    # TODO: ideally would be nested events emitted from children?
    track_added: ClassVar[Signal] = Signal(object)
    track_removed: ClassVar[Signal] = Signal(object)
    track_renamed: ClassVar[Signal] = Signal(object)
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

    def get_track_model_and_attr(self, track_name):
        obj, path = self.track_options[track_name]
        return _resolve_attr_path(obj, path)

    def add_track(self, name: str) -> Track:
        """Add a new track."""
        if name not in self.track_options:
            raise KeyError(
                f"Track {name} is not allowed. Options are: {tuple(self.track_options)}"
            )
        track = Track(name=name)
        self.tracks[name] = track
        self.track_added(track)
        return track

    def remove_track(self, name: str) -> Track:
        """Remove *track*."""
        track = self.tracks.pop(name)
        self.track_removed(track)
        return track

    def rename_track(self, name: str, new_name: str) -> None:
        """Rename a track option key and any existing track with that name."""
        if name not in self.track_options:
            raise KeyError(
                f"Track {name} is not allowed. Options are: {tuple(self.track_options)}"
            )
        if name == new_name:
            return

        self.track_options[new_name] = self.track_options.pop(name)
        track = self.tracks.pop(name)
        if track is not None:
            track.name = new_name
            self.tracks[new_name] = track
        self.track_renamed(track)

    def add_keyframe(
        self,
        track_name: str,
        t: int,
        value: Any = None,
        easing: EasingFunction = EasingFunction.Linear,
    ) -> Keyframe:
        """Add a keyframe to track."""
        track = self.tracks[track_name]
        kf = track.add_keyframe(t, value, easing)
        self.keyframes_added([kf])
        self._update_bound_models()
        return kf

    def add_keyframe_from_state(
        self,
        track_name: str,
        t: int,
        easing: EasingFunction = EasingFunction.Linear,
    ) -> Keyframe:
        """Add a keyframe at frame t with value from the current state."""
        if track_name not in self.tracks:
            self.add_track(track_name)
        model, attr = self.get_track_model_and_attr(track_name)
        value = model if attr == "" else getattr(model, attr)

        return self.add_keyframe(track_name, t, value, easing)

    def remove_keyframe(
        self,
        track_name: str,
        t: int,
    ) -> Keyframe:
        track = self.tracks[track_name]
        kf = track.remove_keyframe(t)
        self.keyframes_removed([kf])
        self._update_bound_models()
        return kf

    def _get_kf_track(self, kf: Keyframe) -> Track:
        for track in self.tracks.values():
            for kf_ in track.keyframes:
                if kf is kf_:
                    return track
        raise KeyError(f"Keyframe {kf} is not part of any track.")

    def remove_keyframes(
        self,
        keyframes: list[Keyframe],
    ) -> None:
        """Bulk removal of keyframes."""
        for kf in keyframes:
            track = self._get_kf_track(kf)
            track.remove_keyframe(kf)
        self.keyframes_removed(keyframes)
        self._update_bound_models()

    def move_keyframes(
        self,
        keyframes: list[Keyframe],
        offset: int,
    ) -> None:
        """Bulk removal of keyframes."""
        for kf in keyframes:
            track = self._get_kf_track(kf)
            try:
                track.move_keyframe(kf, offset)
            except KeyError:
                warnings.warn(
                    f"Cannot move keyframe to frame {kf.t + offset} on track "
                    f'"{track.name}": a keyframe already exists here. Skipping.',
                    stacklevel=1,
                )
            except ValueError:
                warnings.warn(
                    "Cannot move keyframe below frame 0. Skipping.",
                    stacklevel=1,
                )
        self.keyframes_moved(keyframes)
        self._update_bound_models()

    def change_easing(self, keyframe: Keyframe, easing: EasingFunction):
        keyframe.easing = easing
        self.easing_changed([keyframe])
        self._update_bound_models()

    def cycle_play_mode(self) -> None:
        """Cycle normal -> loop -> pingpong -> normal."""
        self.play_mode = PlayMode((self.play_mode + 1) % 3)

    def interpolate_track(self, track: Track, frame: int) -> Any:
        """Return the interpolated value of track at frame, or ``None``.

        Values before the first keyframe and after the last are held constant.
        """
        kfs = track.keyframes
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

    @property
    def n_frames(self):
        max_frame = 0
        for tr in self.tracks.values():
            for kf in tr.keyframes:
                max_frame = max(max_frame, kf.t)
        return max_frame

    @property
    def duration(self):
        return self.n_frames / self.play_fps

    def _update_bound_models(self) -> None:
        """Update each bound model field to the interpolated value at frame.

        When the bound field is itself a model/dataclass the interpolated dict
        is applied in-place.
        """
        for name, track in self.tracks.items():
            value = self.interpolate_track(track, self.current_frame)
            if value is _UNSET:
                continue

            model, field = self.get_track_model_and_attr(name)
            if field == "":
                # whole model should be updated
                if not _is_model_or_dataclass(model):
                    raise ValueError(
                        "To update a whole object, you must pass a model or dataclass."
                    )
                original = model
            else:
                original = getattr(model, field)

            if _is_model_or_dataclass(original):
                _update_model_inplace(original, value)
            else:
                setattr(model, field, value)

    def iter_frames(self, play_range: tuple[int, int] | None = None):
        if self.n_frames == 0:
            return
        if play_range is None:
            start, end = 0, self.n_frames
        else:
            start, end = sorted(play_range)
            start = max(0, start)
            end = min(self.n_frames, end)

        frame = start

        self.current_frame = frame
        yield self.current_frame

        direction = 1
        while True:
            frame = frame + direction
            if frame > end:
                if self.play_mode == PlayMode.NORMAL:
                    return
                elif self.play_mode == PlayMode.LOOP:
                    frame = start
                elif self.play_mode == PlayMode.PINGPONG:
                    direction = -1
                    frame = end - 1
            elif frame < start and PlayMode.PINGPONG and direction == -1:
                direction = 1
                frame = start + 1

            self.current_frame = frame
            yield self.current_frame

    @field_serializer("track_options")
    def _serialize_track_options(self, value: dict[str, tuple[Any, str]]):
        # ensure that the objects are serialized as their classes, so this can be reused
        # with new objects
        return {
            name: (f"{obj.__class__.__module__}.{obj.__class__.__qualname__}", attr)
            for name, (obj, attr) in value.items()
        }
