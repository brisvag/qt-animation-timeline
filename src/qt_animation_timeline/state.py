"""Backward-compatibility shim — all symbols now live in ``models``."""

from qt_animation_timeline.models import (
    PLAY_LOOP,
    PLAY_NORMAL,
    PLAY_PINGPONG,
    Animation,
    AnimationState,
    _apply_model_value,
    _is_model_instance,
    _TrackOptionsDict,
)

__all__ = [
    "PLAY_LOOP",
    "PLAY_NORMAL",
    "PLAY_PINGPONG",
    "Animation",
    "AnimationState",
    "_apply_model_value",
    "_is_model_instance",
    "_TrackOptionsDict",
]
