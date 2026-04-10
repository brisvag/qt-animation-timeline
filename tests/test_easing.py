from enum import Enum

import numpy as np
import pytest

from qt_animation_timeline.easing import EasingFunction


class X(Enum):
    a = 0
    b = 0


@pytest.mark.parametrize(
    ("v1", "v2", "p", "easing", "expected"),
    [
        # fall back to step in non numerical cases
        (False, True, 0.4, EasingFunction.Linear, False),
        (None, 1, 0.4, EasingFunction.Linear, None),
        (X.a, X.b, 0.4, EasingFunction.Linear, X.a),
        # ints should stay ints
        (0, 2, 0.4, EasingFunction.Step, 0),
        (0, 2, 0.4, EasingFunction.Linear, 1),
        # actual linear interpolation with various types
        (0.0, 2.0, 0.4, EasingFunction.Linear, 0.8),
        (
            {"a": 0.0, "b": False},
            {"a": -1.0, "b": True},
            0.7,
            EasingFunction.Linear,
            {"a": -0.7, "b": True},
        ),
        ([1, [2, 3.0]], [3, [4, 5.0]], 0.4, EasingFunction.Linear, [2, [3, 3.8]]),
        # strings should be left alone
        (("0", "1"), ("2", "3"), 0.4, EasingFunction.Linear, ("0", "1")),
        (
            np.arange(10),
            np.arange(10, 20),
            0.5,
            EasingFunction.Linear,
            np.arange(5, 15),
        ),
    ],
)
def test_easing(v1, v2, p, easing, expected):
    interp = easing(p, v1, v2)
    if isinstance(v1, np.ndarray):
        np.testing.assert_almost_equal(interp, expected)
    else:
        assert interp == expected
