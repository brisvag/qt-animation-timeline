"""Qt animation timeline editor."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("qt-animation-timeline")
except PackageNotFoundError:
    __version__ = "uninstalled"
__author__ = "Lorenzo Gaifas"
__email__ = "brisvag@gmail.com"

from qt_animation_timeline.easing import EasingFunction
from qt_animation_timeline.models import AnimationTimeline, Keyframe, PlayMode, Track
from qt_animation_timeline.qt_timeline import AnimationTimelineWidget

__all__ = [
    "AnimationTimeline",
    "AnimationTimelineWidget",
    "EasingFunction",
    "Keyframe",
    "PlayMode",
    "Track",
]
