"""Qt animation timeline editor."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("qt-animation-editor")
except PackageNotFoundError:
    __version__ = "uninstalled"
__author__ = "Lorenzo Gaifas"
__email__ = "brisvag@gmail.com"

# Re-export the public API so callers can do:
#   from qt_animation_editor import AnimationTimelineWidget, EasingFunction, …
from qt_animation_editor.easing import EasingFunction
from qt_animation_editor.editor import _PLACEHOLDER_TRACK, AnimationTimelineWidget
from qt_animation_editor.models import Keyframe, Track, _coerce_value

__all__ = [
    "_PLACEHOLDER_TRACK",
    "AnimationTimelineWidget",
    "EasingFunction",
    "Keyframe",
    "Track",
    "_coerce_value",
]
