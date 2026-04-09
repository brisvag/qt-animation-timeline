"""Qt animation timeline editor."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("qt-animation-timeline")
except PackageNotFoundError:
    __version__ = "uninstalled"
__author__ = "Lorenzo Gaifas"
__email__ = "brisvag@gmail.com"

from qt_animation_timeline.easing import EasingFunction, _coerce_value
from qt_animation_timeline.editor import AnimationTimelineWidget
from qt_animation_timeline.models import Keyframe, Track
from qt_animation_timeline.state import AnimationState

__all__ = [
    "AnimationState",
    "AnimationTimelineWidget",
    "EasingFunction",
    "Keyframe",
    "Track",
    "_coerce_value",
]
