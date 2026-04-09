"""Core data models: Keyframe and Track."""

from __future__ import annotations

from typing import Any

from qt_animation_timeline.easing import EasingFunction


class Keyframe:
    """A keyframe: time position, value, and easing for the segment after it."""

    def __init__(
        self,
        t: int,
        value: Any = 0,
        easing: EasingFunction = EasingFunction.Linear,
    ) -> None:
        self.t = max(0, int(t))
        self.value = value
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
