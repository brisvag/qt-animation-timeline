# Easing functions were largely copied from napari-animation
# (https://github.com/napari/napari-animation/blob/main/napari_animation/easing.py)

from __future__ import annotations

import logging
from collections.abc import Iterable
from enum import Enum
from math import cos, pi, pow, sin, sqrt
from types import NoneType
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic_core import core_schema

tau = pi * 2

if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler


logger = logging.getLogger(__name__)


def linear_interpolation(p):
    """Modeled after the line y = x"""
    return p


def quadratic_ease_in(p):
    """Modeled after the parabola y = x^2"""
    return p * p


def quadratic_ease_out(p):
    """Modeled after the parabola y = -x^2 + 2x"""
    return -(p * (p - 2))


def quadratic_ease_in_out(p):
    """Modeled after the piecewise quadratic
    y = (1/2)((2x)^2)             ; [0, 0.5)
    y = -(1/2)((2x-1)*(2x-3) - 1) ; [0.5, 1]
    """
    if p < 0.5:
        return 2 * p * p
    else:
        return (-2 * p * p) + (4 * p) - 1


def cubic_ease_in(p):
    """Modeled after the cubic y = x^3"""
    return p * p * p


def cubic_ease_out(p):
    """Modeled after the cubic y = (x - 1)^3 + 1"""
    f = p - 1
    return (f * f * f) + 1


def cubic_ease_in_out(p):
    """Modeled after the piecewise cubic
    y = (1/2)((2x)^3)       ; [0, 0.5)
    y = (1/2)((2x-2)^3 + 2) ; [0.5, 1]
    """
    if p < 0.5:
        return 4 * p * p * p
    else:
        f = (2 * p) - 2
        return (0.5 * f * f * f) + 1


def quintic_ease_in(p):
    """Modeled after the quintic y = x^5"""
    return p * p * p * p * p


def quintic_ease_out(p):
    """Modeled after the quintic y = (x - 1)^5 + 1"""
    f = p - 1
    return (f * f * f * f * f) + 1


def quintic_ease_in_out(p):
    """Modeled after the piecewise quintic
    y = (1/2)((2x)^5)       ; [0, 0.5)
    y = (1/2)((2x-2)^5 + 2) ; [0.5, 1]
    """
    if p < 0.5:
        return 16 * p * p * p * p * p
    else:
        f = (2 * p) - 2
        return (0.5 * f * f * f * f * f) + 1


def sine_ease_in(p):
    """Modeled after quarter-cycle of sine wave"""
    return sin((p - 1) * tau) + 1


def sine_ease_out(p):
    """Modeled after quarter-cycle of sine wave (different phase)"""
    return sin(p * tau)


def sine_ease_in_out(p):
    """Modeled after half sine wave"""
    return 0.5 * (1 - cos(p * pi))


def circular_ease_in(p):
    """Modeled after shifted quadrant IV of unit circle"""
    return 1 - sqrt(1 - (p * p))


def circular_ease_out(p):
    """Modeled after shifted quadrant II of unit circle"""
    return sqrt((2 - p) * p)


def circular_ease_in_out(p):
    """Modeled after the piecewise circular function
    y = (1/2)(1 - sqrt(1 - 4x^2))           ; [0, 0.5)
    y = (1/2)(sqrt(-(2x - 3)*(2x - 1)) + 1) ; [0.5, 1]
    """
    if p < 0.5:
        return 0.5 * (1 - sqrt(1 - 4 * (p * p)))
    else:
        return 0.5 * (sqrt(-((2 * p) - 3) * ((2 * p) - 1)) + 1)


def exponential_ease_in(p):
    """Modeled after the exponential function y = 2^(10(x - 1))"""
    if p == 0.0:
        return p
    else:
        return pow(2, 10 * (p - 1))


def exponential_ease_out(p):
    """Modeled after the exponential function y = -2^(-10x) + 1"""
    if p == 1.0:
        return p
    else:
        return 1 - pow(2, -10 * p)


def exponential_ease_in_out(p):
    """Modeled after the piecewise exponential
    y = (1/2)2^(10(2x - 1))         ; [0,0.5)
    y = -(1/2)*2^(-10(2x - 1))) + 1 ; [0.5,1]
    """
    if p == 0.0 or p == 1.0:
        return p

    if p < 0.5:
        return 0.5 * pow(2, (20 * p) - 10)
    else:
        return -0.5 * pow(2, (-20 * p) + 10) + 1


def elastic_ease_in(p):
    """Modeled after the damped sine wave y = sin(13pi/2*x)*2^(10 * (x - 1))"""
    return sin(13 * tau * p) * pow(2, 10 * (p - 1))


def elastic_ease_out(p):
    """Modeled after the damped sine wave y = sin(-13pi/2*(x + 1))*pow(2, -10x) + 1"""
    return sin(-13 * tau * (p + 1)) * pow(2, -10 * p) + 1


def elastic_ease_in_out(p):
    """Modeled after the piecewise exponentially-damped sine wave:
    y = (1/2)*sin(13pi/2*(2*x))*pow(2, 10 * ((2*x) - 1))      ; [0, 0.5)
    y = (1/2)*(sin(-13pi/2*((2x-1)+1))*pow(2,-10(2*x-1)) + 2) ; [0.5, 1]
    """
    if p < 0.5:
        return 0.5 * sin(13 * tau * (2 * p)) * pow(2, 10 * ((2 * p) - 1))
    else:
        return 0.5 * (
            sin(-13 * tau * ((2 * p - 1) + 1)) * pow(2, -10 * (2 * p - 1)) + 2
        )


def back_ease_in(p):
    """Modeled after the overshooting cubic y = x^3-x*sin(x*pi)"""
    return p * p * p - p * sin(p * pi)


def back_ease_out(p):
    """Modeled after overshooting cubic y = 1-((1-x)^3-(1-x)*sin((1-x)*pi))"""
    f = 1 - p
    return 1 - (f * f * f - f * sin(f * pi))


def back_ease_in_out(p):
    """Modeled after the piecewise overshooting cubic function:
    y = (1/2)*((2x)^3-(2x)*sin(2*x*pi))           ; [0, 0.5)
    y = (1/2)*(1-((1-x)^3-(1-x)*sin((1-x)*pi))+1) ; [0.5, 1]
    """
    if p < 0.5:
        f = 2 * p
        return 0.5 * (f * f * f - f * sin(f * pi))
    else:
        f = 1 - (2 * p - 1)
        return (0.5 * (1 - (f * f * f - f * sin(f * pi)))) + 0.5


def bounce_ease_in(p):
    return 1 - bounce_ease_out(1 - p)


def bounce_ease_out(p):
    if p < 4 / 11.0:
        return (121 * p * p) / 16.0

    elif p < 8 / 11.0:
        return ((363 / 40.0) * p * p) - ((99 / 10.0) * p) + (17 / 5.0)

    elif p < 9 / 10.0:
        return ((4356 / 361.0) * p * p) - ((35442 / 1805.0) * p) + (16061 / 1805.0)

    else:
        return ((54 / 5.0) * p * p) - ((513 / 25.0) * p) + (268 / 25.0)


def bounce_ease_in_out(p):
    if p < 0.5:
        return 0.5 * bounce_ease_in(p * 2)
    else:
        return (0.5 * bounce_ease_out(p * 2 - 1)) + 0.5


def _easing_step(p: float, v_start: Any, v_end: Any) -> Any:
    """Step function: hold *v_start* then jump to *v_end* at p = 0.5.

    Works with *any* value type — no arithmetic is performed, so it handles
    strings, objects, and other non-numeric values just fine.
    """
    return v_end if p >= 0.5 else v_start


def _is_collection(obj: Any) -> bool:
    # exclude stuff like strings and numpy arrays which are handled differently
    return (
        isinstance(obj, Iterable)
        and not np.isscalar(obj)
        and not isinstance(obj, np.ndarray)
    )


def _is_numeric_array(arr: np.ndarray) -> bool:
    return arr.dtype.kind in "iufcmM"


def _coerce_value(reference: Any, interpolated: Any) -> Any:
    """Coerce *interpolated* to match the type of *reference*.

    Handles Python ``bool``, ``int``, and ``float`` precisely.  For ``list``
    and ``tuple`` values (including nested ones) the result is cast element-
    wise back to the original container type using numpy for arithmetic.
    numpy arrays and other array-like objects are returned as-is.  Non-numeric
    types are also returned unchanged — they arise only from the ``Step``
    easing which returns the original value directly.
    """
    if isinstance(reference, bool | Enum):
        # need to do before int or they will be converted to int
        return interpolated
    if isinstance(reference, int):
        # back from float
        return round(interpolated)
    if isinstance(reference, dict):
        # assume at this point dicts have the same set of keys
        return {
            k: _coerce_value(vref, vint)
            for (k, vref), (_, vint) in zip(
                reference.items(), interpolated.items(), strict=True
            )
        }
    if _is_collection(reference):
        # cast each element back recursively (handles nested)
        return type(reference)(
            [_coerce_value(r, v) for r, v in zip(reference, interpolated, strict=True)]
        )
    return interpolated


def _make_interpolator(p_func: Any) -> Any:
    """Adapter from p-transformers to interpolator function."""

    def _interp(p: float, v1: Any, v2: Any) -> Any:
        return v1 + (v2 - v1) * p_func(p)

    return _interp


class EasingFunction(Enum):
    """Easing functions for keyframe segments.

    Each member is callable as ``f(p, v_start, v_end) -> value`` where *p* ∈
    [0, 1] is the normalised progress within a segment.  The return value is
    the interpolated value between *v_start* and *v_end*.

    All members except ``Step`` perform arithmetic interpolation and are
    suitable for numeric types and numpy arrays.  ``Step`` switches at
    p = 0.5 and works with *any* type.

    Implementation note: the raw functions are wrapped in a one-tuple so that
    Python's Enum machinery does not mistake them for method descriptors (which
    would prevent them from becoming proper enum members).
    """

    Linear = (_make_interpolator(linear_interpolation),)
    Quadratic = (_make_interpolator(quadratic_ease_in_out),)
    Cubic = (_make_interpolator(cubic_ease_in_out),)
    Quintic = (_make_interpolator(quintic_ease_in_out),)
    Sine = (_make_interpolator(sine_ease_in_out),)
    Circular = (_make_interpolator(circular_ease_in_out),)
    Exponential = (_make_interpolator(exponential_ease_in_out),)
    Elastic = (_make_interpolator(elastic_ease_in_out),)
    Back = (_make_interpolator(back_ease_in_out),)
    Bounce = (_make_interpolator(bounce_ease_in_out),)
    Step = (_easing_step,)

    @staticmethod
    def get_allowed_easings(value):
        """Get the allowed easings for the given value depending on type."""
        if isinstance(value, str | bool | Enum | NoneType):
            return [EasingFunction.Step]
        return list(EasingFunction)

    def __call__(self, p: float, v1: Any, v2: Any) -> Any:
        """Interpolate between v1 and v2 at p, using this easing function.

        Falls back to Step when it can't interpolate otherwise.
        """
        # str and bool should always fall back to step
        # (even though in some cases they can be cast to numbers)
        if (
            self == EasingFunction.Step
            or isinstance(v1, str | bool | Enum | NoneType)
            or isinstance(v2, str | bool | Enum | NoneType)
        ):
            # with Step type is conserved, no need to cast
            return EasingFunction.Step.value[0](p, v1, v2)

        reference = v1
        if isinstance(v1, dict) and isinstance(v2, dict):
            if not v1.keys() == v2.keys():
                raise ValueError("Cannot interpolate between dicts with different keys")
            interp = {k: self(p, v1[k], v2[k]) for k in v1}
            return _coerce_value(reference, interp)

        # try catch all to have always the step fallback
        try:
            # collections should be treated as arrays if possible
            if _is_collection(v1) or _is_collection(v2):
                try:
                    v1_arr = np.asarray(v1)
                    v2_arr = np.asarray(v2)
                    if not _is_numeric_array(v1_arr):
                        raise ValueError
                except ValueError:
                    # may happen if it's not a homogeneous shape. Some other cases?
                    # So in this case go nested by element
                    interp = [
                        self(p, el1, el2) for el1, el2 in zip(v1, v2, strict=True)
                    ]
                    return _coerce_value(reference, interp)
                else:
                    interp = self.value[0](p, v1_arr, v2_arr)
            else:
                interp = self.value[0](p, v1, v2)
            return _coerce_value(reference, interp)
        except (ValueError, TypeError):
            logger.info(
                "could not interpolate %s -> %s using %s function."
                " Falling back to Step.",
                v1,
                v2,
                self.name,
            )
            return EasingFunction.Step.value[0](p, v1, v2)

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler: GetCoreSchemaHandler):
        """Serialize with name, not value (function)."""
        schema = handler(source)

        return core_schema.no_info_after_validator_function(
            cls,
            schema,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda v: v.name
            ),
        )

    @classmethod
    def _missing_(cls, value):
        # needed to cast back to enum if the name is passed
        if isinstance(value, str):
            return cls[value]
        return None
