"""Qt animation timeline editor."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("qt-animation-editor")
except PackageNotFoundError:
    __version__ = "uninstalled"
__author__ = "Lorenzo Gaifas"
__email__ = "brisvag@gmail.com"

from qt_animation_editor.easing import EasingFunction, _coerce_value
from qt_animation_editor.editor import _PLACEHOLDER_TRACK, AnimationTimelineWidget
from qt_animation_editor.models import Keyframe, Track

__all__ = [
    "_PLACEHOLDER_TRACK",
    "AnimationTimelineWidget",
    "EasingFunction",
    "Keyframe",
    "Track",
    "_coerce_value",
]
