import numpy as np
import pytest

from qt_animation_timeline.easing import EasingFunction


@pytest.mark.parametrize(
    ("v1", "v2", "p", "easing", "expected"),
    [
        (False, True, 0.4, EasingFunction.Linear, False),
        (0, 2, 0.4, EasingFunction.Step, 0),
        (0, 2, 0.4, EasingFunction.Linear, 1),
        (0.0, 2.0, 0.4, EasingFunction.Linear, 0.8),
        (
            {"a": 0.0, "b": False},
            {"a": -1.0, "b": True},
            0.7,
            EasingFunction.Linear,
            {"a": -0.7, "b": True},
        ),
        ([1, [2, 3]], [3, [4, 5]], 0.5, EasingFunction.Linear, [2, [3, 4]]),
        (
            np.arange(10),
            np.arange(10, 20),
            0.5,
            EasingFunction.Linear,
            np.arange(5, 15),
        ),
    ],
)
def test_easing_linear(v1, v2, p, easing, expected):
    interp = easing(p, v1, v2)
    if isinstance(v1, np.ndarray):
        np.testing.assert_almost_equal(interp, expected)
    else:
        assert interp == expected
