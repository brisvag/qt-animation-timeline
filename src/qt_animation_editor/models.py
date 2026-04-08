"""Core data models: Keyframe, Track, and value-coercion helpers."""

from __future__ import annotations

from typing import Any

from qtpy.QtGui import QColor

from qt_animation_editor.easing import EasingFunction


def _coerce_value(reference: Any, interpolated: Any) -> Any:
    """Coerce *interpolated* to match the type of *reference* for scalar types.

    Handles Python ``bool``, ``int``, and ``float`` precisely.  Array-like
    values (e.g. numpy arrays) are returned as-is because element-wise
    arithmetic already produces the correct type.  Non-numeric types (e.g.
    strings, arbitrary objects) are also returned unchanged — they arise only
    from the ``Step`` easing which returns the original value directly.
    """
    # bool must be checked before int — bool is a subclass of int.
    if isinstance(reference, bool):
        return bool(round(float(interpolated)))
    if isinstance(reference, int):
        return round(float(interpolated))
    if isinstance(reference, float):
        return float(interpolated)
    # numpy arrays and other array-like / arbitrary types.
    return interpolated


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
        # Controls the interpolation curve from this keyframe to the *next* one.
        self.easing = easing


class Track:
    """A named animation track holding an ordered list of keyframes."""

    def __init__(self, name: str, color: QColor | None = None) -> None:
        self.name = name
        self.color = color or QColor(180, 180, 180)
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
                msg = f"keyframe at frame {t} already exists in track \"{self.name}\""
                raise KeyError(msg)
        kf = Keyframe(t, value, easing)
        self.keyframes.append(kf)
        self.keyframes.sort(key=lambda k: k.t)
        return kf
