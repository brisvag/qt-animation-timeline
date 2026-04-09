"""Easing functions for animation keyframe segments."""

from __future__ import annotations

from enum import Enum
from typing import Any


def _coerce_value(reference: Any, interpolated: Any) -> Any:
    """Coerce *interpolated* to match the type of *reference*.

    Handles Python ``bool``, ``int``, and ``float`` precisely.  For ``list``
    and ``tuple`` values (including nested ones) the result is cast element-
    wise back to the original container type using numpy for arithmetic.
    numpy arrays and other array-like objects are returned as-is.  Non-numeric
    types are also returned unchanged — they arise only from the ``Step``
    easing which returns the original value directly.
    """
    # interpolation is all or nothing for str and bool, no need to cast
    if isinstance(reference, str | bool):
        return interpolated
    if isinstance(reference, int):
        return round(interpolated)
    # list / tuple (including nested): cast each element back recursively.
    if isinstance(reference, (list, tuple)):
        return type(reference)(
            [_coerce_value(r, v) for r, v in zip(reference, interpolated, strict=True)]
        )
    # numpy arrays and anything else
    return interpolated


def _easing_linear(p: float, v_start: Any, v_end: Any) -> Any:
    """Linearly interpolate between *v_start* and *v_end*.

    Works with any type that supports ``+``, ``-``, and ``*`` by a scalar
    (floats, ints, numpy arrays, …).
    """
    return v_start + (v_end - v_start) * p


def _easing_step(p: float, v_start: Any, v_end: Any) -> Any:
    """Step function: hold *v_start* then jump to *v_end* at p = 0.5.

    Works with *any* value type — no arithmetic is performed, so it handles
    strings, objects, and other non-numeric values just fine.
    """
    return v_end if p >= 0.5 else v_start


class EasingFunction(Enum):
    """Easing functions for keyframe segments.

    Each member is callable as ``f(p, v_start, v_end) -> value`` where *p* ∈
    [0, 1] is the normalised progress within a segment.  The return value is
    the interpolated value between *v_start* and *v_end*.

    ``Linear`` performs standard arithmetic interpolation and is suitable for
    numeric types and numpy arrays.  ``Step`` switches at p = 0.5 and works
    with *any* type.

    Implementation note: the raw functions are wrapped in a one-tuple so that
    Python's Enum machinery does not mistake them for method descriptors (which
    would prevent them from becoming proper enum members).
    """

    # Values are (function,) tuples — see __call__ below.
    Linear = (_easing_linear,)
    Step = (_easing_step,)

    def __call__(self, p: float, v_start: Any, v_end: Any) -> Any:
        return self.value[0](p, v_start, v_end)
