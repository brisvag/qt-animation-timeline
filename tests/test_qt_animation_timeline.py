import dataclasses
import os
from typing import ClassVar

import numpy as np
import pytest
from pydantic import BaseModel
from pydantic_extra_types.color import Color
from qtpy.QtCore import QEvent, QPointF, QRect, Qt
from qtpy.QtGui import QColor, QKeyEvent, QMouseEvent
from qtpy.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qt_animation_timeline.easing import EasingFunction, _coerce_value
from qt_animation_timeline.models import Animation, PlayMode
from qt_animation_timeline.qt_timeline import (
    _BUTTON_ICONS,
    _DEFAULT_COLORS,
    _PLAY_MODE_ICONS,
    AnimationTimelineWidget,
)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="function")
def timeline(qapp):
    timeline = AnimationTimelineWidget()

    class MyModel(BaseModel):
        x: int = 1

    timeline.animation.track_options = {"A": (MyModel(), "x")}
    return timeline


def test_coordinate_roundtrip(timeline):
    for frame in [0, 10, 100, 500]:
        assert timeline.x_to_frame(timeline.frame_to_x(frame)) == frame
    assert timeline.left_timeline_pad > 0
    assert timeline.frame_to_x(0) > timeline.left_margin


def test_track_center_y(timeline):
    assert timeline.track_center_y(0) == timeline.top_margin + timeline.track_height / 2


def test_track_color_cycle(timeline):
    red = QColor(255, 0, 0)
    timeline.track_color_cycle = [red]
    track = timeline.add_track("A")
    assert track.color == Color((255, 0, 0))


def test_set_playhead(timeline):
    frames = []
    timeline.animation.events.current_frame.connect(frames.append)
    timeline._set_playhead(10)
    assert timeline.animation.current_frame == 10 and frames == [10]
    timeline._set_playhead(10)
    assert frames == [10]  # no duplicate signal


def test_pos_to_keyframe(timeline):
    timeline.resize(800, 300)
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(10)
    x, y = timeline.frame_to_x(10), timeline.track_center_y(0)
    assert timeline.pos_to_keyframe(x, y) is not None
    assert timeline.pos_to_keyframe(0, 0) is None


def test_keyframes_in_rect(timeline):
    timeline.resize(800, 300)
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(10)
    timeline.animation.tracks["A"].add_keyframe(100)
    cx10 = int(timeline.frame_to_x(10))
    cy = int(timeline.track_center_y(0))
    rect = QRect(cx10 - 20, cy - 20, 40, 40)
    hits = timeline._keyframes_in_rect(rect)
    assert len(hits) == 1 and hits[0].t == 10


def test_delete_keyframes(timeline):
    timeline.resize(800, 300)
    timeline.add_track("A")
    kf = timeline.animation.tracks["A"].add_keyframe(10)
    timeline.selected_keyframes = [kf]
    removed = []
    timeline.animation.keyframes_removed.connect(removed.append)
    press = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier
    )
    timeline.keyPressEvent(press)
    assert len(timeline.animation.tracks["A"].keyframes) == 0
    assert removed == [[kf]]


def _combo_options(timeline, track):
    """Return ``{label: enabled}`` for the track-change combo of a given track."""
    return dict(timeline._get_track_change_options(track))


def test_unique_track_options(timeline):
    timeline.animation.track_options = {"A": (object(), "x"), "B": (object(), "y")}
    timeline.add_track("A")
    track = timeline.add_track("B")
    options = _combo_options(timeline, track)
    assert options.get("A") is False  # A is used by track 0 -> disabled for track 1
    assert options.get("B") is True  # B is the current track's own name


def _make_press(x, y, shift=False, button=Qt.MouseButton.LeftButton):
    mod = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y), button, button, mod)


def test_rubber_band_selection(timeline):
    timeline.resize(800, 300)
    timeline.add_track("A")
    x = int(timeline.left_margin + 50)
    y = int(timeline.track_center_y(0))
    # Shift+click starts rubber-band; plain click does not.
    timeline.mousePressEvent(_make_press(x, y, shift=True))
    assert timeline._box_start is not None


def test_interpolation(timeline):
    timeline.add_track("A")
    track = timeline.animation.tracks["A"]
    assert timeline.animation.interpolate_track(track, 50)

    kf = track.add_keyframe(10, value=7.0)
    assert timeline.animation.interpolate_track(track, 5) == pytest.approx(7.0)
    assert timeline.animation.interpolate_track(track, 10) == pytest.approx(7.0)
    assert timeline.animation.interpolate_track(track, 20) == pytest.approx(7.0)

    track.remove_keyframe(kf)
    timeline.animation.tracks["A"].add_keyframe(0, value=0.0)
    timeline.animation.tracks["A"].add_keyframe(100, value=10.0)
    assert timeline.animation.interpolate_track(
        timeline.animation.tracks["A"], 50
    ) == pytest.approx(5.0)
    assert timeline.animation.interpolate_track(
        timeline.animation.tracks["A"], 0
    ) == pytest.approx(0.0)
    assert timeline.animation.interpolate_track(
        timeline.animation.tracks["A"], 200
    ) == pytest.approx(10.0)


def test_interpolation_step_easing(timeline):
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(
        0, value=0.0, easing=EasingFunction.Step
    )
    timeline.animation.tracks["A"].add_keyframe(100, value=1.0)
    assert timeline.animation.interpolate_track(
        timeline.animation.tracks["A"], 49
    ) == pytest.approx(0.0)
    assert timeline.animation.interpolate_track(
        timeline.animation.tracks["A"], 50
    ) == pytest.approx(1.0)
    assert timeline.animation.interpolate_track(
        timeline.animation.tracks["A"], 100
    ) == pytest.approx(1.0)


def test_segment_left_keyframe(timeline):
    timeline.resize(800, 300)
    timeline.add_track("A")
    k1 = timeline.animation.tracks["A"].add_keyframe(0)
    timeline.animation.tracks["A"].add_keyframe(100)
    x = int(timeline.frame_to_x(50))
    y = int(timeline.track_center_y(0))
    assert timeline._segment_left_keyframe_at(x, y) is k1

    k2 = timeline.animation.tracks["A"].add_keyframe(50)
    x2 = int(timeline.frame_to_x(80))
    y2 = int(timeline.track_center_y(0))
    assert timeline._segment_left_keyframe_at(x2, y2) is k2

    timeline.animation.remove_keyframes([k1, k2])
    assert (
        timeline._segment_left_keyframe_at(
            int(timeline.frame_to_x(10)), int(timeline.track_center_y(0))
        )
        is None
    )


def test_track_model_dispatch(timeline):
    class Model:
        x = 0.0
        n = 0
        flag = False

    m = Model()
    timeline.animation.track_options = {"A": (m, "x")}
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(0, value=0.0)
    timeline.animation.tracks["A"].add_keyframe(100, value=10.0)
    timeline._set_playhead(50)
    assert m.x == pytest.approx(5.0)
    timeline.animation.remove_track("A")

    timeline.animation.track_options = {"A": (m, "n")}
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(0, value=0)
    timeline.animation.tracks["A"].add_keyframe(10, value=10)
    timeline._set_playhead(3)
    assert isinstance(m.n, int) and m.n == 3
    timeline.animation.remove_track("A")

    timeline.animation.track_options = {"A": (m, "flag")}
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(
        0, value=0.0, easing=EasingFunction.Step
    )
    timeline.animation.tracks["A"].add_keyframe(100, value=1.0)
    timeline._set_playhead(49)
    assert m.flag == 0
    timeline._set_playhead(50)
    assert m.flag == 1


def test_dispatch_on_easing_and_keyframe_change(timeline):
    class Model:
        x = 0.0

    m = Model()
    timeline.animation.track_options = {"A": (m, "x")}
    timeline.add_track("A")
    kf = timeline.animation.tracks["A"].add_keyframe(0, value=0.0)
    timeline.animation.tracks["A"].add_keyframe(100, value=10.0)
    timeline._set_playhead(50)
    assert m.x == pytest.approx(5.0)

    # Changing easing should re-dispatch.
    timeline.animation.change_easing(kf, EasingFunction.Step)
    assert m.x == pytest.approx(10.0)

    # Adding a keyframe at the playhead should re-dispatch.
    kf = timeline.animation.add_keyframe("A", 50, value=99.0)
    assert m.x == pytest.approx(99.0)


def test_can_add_track(timeline):
    # No track_options -> cannot add (popup has nothing to show)
    timeline.animation.track_options = {}
    assert timeline._can_add_track() is False

    timeline.animation.track_options = {"A": (object(), "x"), "B": (object(), "y")}
    assert timeline._can_add_track() is True
    timeline.add_track("A")
    assert timeline._can_add_track() is True  # B still available
    timeline.add_track("B")
    assert timeline._can_add_track() is False  # all used


def test_zoom_step(timeline):
    for fw in [0.05, 0.1, 0.2, 1, 5, 15, 50, 60]:
        timeline.frame_width = fw
        step = timeline.zoom_step()
        assert step >= 1
        s = step
        while s > 9:
            s //= 10
        assert s in (1, 2, 5)
    timeline.frame_width = 0.1
    assert timeline.zoom_step() >= 100
    timeline.frame_width = 60.0
    assert timeline.zoom_step() == 1


def test_easing_preselection(timeline):
    class Model:
        flag: bool = True
        x: float = 0.0

    m = Model()
    timeline.animation.track_options = {"flag": (m, "flag"), "x": (m, "x")}
    t_bool = timeline.add_track("flag")
    t_float = timeline.add_track("x")

    assert timeline._get_allowed_easings_for_track(t_bool) == [EasingFunction.Step]
    allowed_float = timeline._get_allowed_easings_for_track(t_float)
    assert (
        EasingFunction.Linear in allowed_float and EasingFunction.Step in allowed_float
    )


def test_right_double_click_ignored(timeline):
    timeline.resize(800, 300)
    timeline.add_track("A")
    x = int(timeline.frame_to_x(50))
    y = int(timeline.track_center_y(0))
    event = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        QPointF(x, y),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    timeline.mouseDoubleClickEvent(event)
    assert len(timeline.animation.tracks["A"].keyframes) == 0


def test_is_on_track_line(timeline):
    timeline.resize(800, 300)
    timeline.add_track("A")
    cy = timeline.track_center_y(0)
    x = int(timeline.frame_to_x(10))
    assert timeline._is_on_track_line(x, int(cy)) is False
    assert timeline._is_on_track_line(x, int(cy) + timeline.track_height) is False
    assert timeline._is_on_track_line(x, int(cy) + timeline.line_thickness + 4) is False

    # with a line, it should say yes when appropriate
    timeline.animation.add_keyframe("A", 0, 0)
    timeline.animation.add_keyframe("A", 20, 0)
    assert timeline._is_on_track_line(x, int(cy)) is True
    assert timeline._is_on_track_line(x, int(cy) + timeline.track_height) is False
    assert timeline._is_on_track_line(x, int(cy) + timeline.line_thickness + 4) is True

    # No tracks: always False
    assert AnimationTimelineWidget()._is_on_track_line(200, 60) is False


def test_reset_view(timeline):
    timeline.resize(800, 300)
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(0, value=0.0)
    timeline.animation.tracks["A"].add_keyframe(200, value=1.0)
    timeline._reset_view()
    assert timeline.scroll_x == 0
    assert timeline.frame_to_x(0) == pytest.approx(
        timeline.left_margin + timeline.left_timeline_pad
    )
    assert timeline.frame_to_x(200) < timeline.width()

    timeline.resize(800, 300)
    timeline._reset_view()
    assert timeline.scroll_x == 0 and timeline.frame_width > 0


def test_default_colors(timeline):
    from qt_animation_timeline.qt_timeline import _DEFAULT_TRACK_COLORS

    assert len(_DEFAULT_TRACK_COLORS) == 7
    for c in _DEFAULT_TRACK_COLORS:
        assert c.isValid()
    c0 = _DEFAULT_TRACK_COLORS[0]
    assert (c0.red(), c0.green(), c0.blue()) == (0, 114, 178)


def test_numpy_interpolation(timeline):
    v0 = np.array([0.0, 0.0, 0.0])
    v1 = np.array([10.0, 20.0, 30.0])
    np.testing.assert_allclose(EasingFunction.Linear(0.5, v0, v1), [5.0, 10.0, 15.0])
    np.testing.assert_allclose(EasingFunction.Linear(0.0, v0[:2], v1[:2]), v0[:2])
    np.testing.assert_allclose(EasingFunction.Linear(1.0, v0[:2], v1[:2]), v1[:2])

    va, vb = np.array([1.0, 2.0]), np.array([3.0, 4.0])
    assert EasingFunction.Step(0.3, va, vb) is va
    assert EasingFunction.Step(0.5, va, vb) is vb

    arr = np.array([1.0, 2.0, 3.0])
    np.testing.assert_allclose(_coerce_value(arr, arr * 2), [2.0, 4.0, 6.0])

    timeline.animation.track_options = {"A": (object(), "angles")}
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(0, value=np.array([0.0, 0.0]))
    timeline.animation.tracks["A"].add_keyframe(100, value=np.array([10.0, 20.0]))
    np.testing.assert_allclose(
        timeline.animation.interpolate_track(timeline.animation.tracks["A"], 50),
        [5.0, 10.0],
    )
    timeline.animation.remove_track("A")

    class Model:
        angles = np.array([0.0, 0.0, 0.0])

    m = Model()
    timeline.animation.track_options = {"A": (m, "angles")}
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(0, value=np.array([0.0, 0.0, 0.0]))
    timeline.animation.tracks["A"].add_keyframe(100, value=np.array([10.0, 20.0, 30.0]))
    timeline._set_playhead(50)
    np.testing.assert_allclose(m.angles, [5.0, 10.0, 15.0])


def test_arrow_keys(timeline):
    def key_press(key):
        return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)

    timeline._set_playhead(5)
    timeline.keyPressEvent(key_press(Qt.Key.Key_Right))
    assert timeline.animation.current_frame == 6
    timeline.keyPressEvent(key_press(Qt.Key.Key_Left))
    assert timeline.animation.current_frame == 5
    timeline._set_playhead(0)
    timeline.keyPressEvent(key_press(Qt.Key.Key_Left))
    assert timeline.animation.current_frame == 0


def test_play_modes(timeline):
    state = Animation()
    assert state.play_mode == PlayMode.NORMAL
    state.cycle_play_mode()
    assert state.play_mode == PlayMode.LOOP
    state.cycle_play_mode()
    assert state.play_mode == PlayMode.PINGPONG
    state.cycle_play_mode()
    assert state.play_mode == PlayMode.NORMAL


def test_loop_btn_color_distinct(timeline):
    assert timeline.loop_btn_color != timeline.control_btn_color
    assert timeline.loop_btn_color != timeline.play_btn_color
    assert timeline.loop_btn_color.isValid()
    assert "loop_btn_color" in _DEFAULT_COLORS


def test_play_mode_icons():
    for key in _PLAY_MODE_ICONS.values():
        assert key in _BUTTON_ICONS
    assert len(set(_PLAY_MODE_ICONS.values())) == len(_PLAY_MODE_ICONS)
    assert _PLAY_MODE_ICONS[PlayMode.NORMAL] not in (
        _PLAY_MODE_ICONS[PlayMode.LOOP],
        _PLAY_MODE_ICONS[PlayMode.PINGPONG],
    )


def test_left_margin_auto_adjusts(timeline):
    timeline.resize(800, 300)
    assert (
        timeline.left_margin == timeline._left_margin_min
    )  # no tracks: stays at minimum

    timeline.add_track("A")
    timeline.update_scrollbars()
    margin_short = timeline.left_margin

    timeline.animation.track_options = {
        "A": (object(), "x"),
        "A very long track label name": (object(), "y"),
    }
    timeline.add_track("A very long track label name")
    timeline.update_scrollbars()
    margin_long = timeline.left_margin

    assert margin_long > margin_short >= timeline._left_margin_min


def test_coerce_value_list(timeline):
    ref = [1.0, 2.0, 3.0]
    result = _coerce_value(ref, np.array([1.5, 2.5, 3.5]))
    assert isinstance(result, list)
    assert result == pytest.approx([1.5, 2.5, 3.5])


def test_coerce_value_tuple(timeline):
    ref = (1.0, 2.0)
    result = _coerce_value(ref, np.array([0.5, 1.5]))
    assert isinstance(result, tuple) and result == pytest.approx((0.5, 1.5))


def test_coerce_value_nested_list(timeline):
    ref = [[1.0, 2.0], [3.0, 4.0]]
    result = _coerce_value(ref, np.array([[1.5, 2.5], [3.5, 4.5]]))
    assert isinstance(result, list) and isinstance(result[0], list)
    assert result[0] == pytest.approx([1.5, 2.5])
    assert result[1] == pytest.approx([3.5, 4.5])


def test_interpolate_list_and_tuple_values(timeline):
    timeline.animation.track_options = {"A": (object(), "x"), "B": (object(), "y")}
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(0, value=[0.0, 0.0])
    timeline.animation.tracks["A"].add_keyframe(100, value=[10.0, 20.0])
    assert timeline.animation.interpolate_track(
        timeline.animation.tracks["A"], 50
    ) == pytest.approx([5.0, 10.0])

    timeline.add_track("B")
    timeline.animation.tracks["B"].add_keyframe(0, value=(0.0, 100.0))
    timeline.animation.tracks["B"].add_keyframe(100, value=(100.0, 0.0))
    result = timeline.animation.interpolate_track(timeline.animation.tracks["B"], 50)
    np.testing.assert_allclose(result, [50.0, 50.0])


def test_dispatch_list_and_tuple_cast_back(timeline):
    class Model:
        pos_list: ClassVar = [0.0, 0.0]
        pos_tuple = (0.0, 0.0)

    m = Model()
    timeline.animation.track_options = {"A": (m, "pos_list"), "B": (m, "pos_tuple")}
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(0, value=[0.0, 0.0])
    timeline.animation.tracks["A"].add_keyframe(100, value=[10.0, 20.0])
    timeline.add_track("B")
    timeline.animation.tracks["B"].add_keyframe(0, value=(0.0, 0.0))
    timeline.animation.tracks["B"].add_keyframe(100, value=(10.0, 20.0))
    timeline._set_playhead(50)
    assert isinstance(m.pos_list, list) and m.pos_list == pytest.approx([5.0, 10.0])
    assert isinstance(m.pos_tuple, tuple) and m.pos_tuple == pytest.approx((5.0, 10.0))


def test_dispatch_dataclass(timeline):
    import dataclasses

    @dataclasses.dataclass
    class Pose:
        x: float = 0.0
        y: float = 0.0

    pose = Pose(x=0.0, y=0.0)

    class Model:
        state = pose

    m = Model()
    timeline.animation.track_options = {"A": (m, "state")}
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(
        0, value=Pose(x=0.0, y=0.0), easing=EasingFunction.Step
    )
    timeline.animation.tracks["A"].add_keyframe(100, value=Pose(x=10.0, y=20.0))
    timeline._set_playhead(50)
    assert m.state is pose  # updated in-place, not replaced
    assert m.state.x == pytest.approx(10.0) and m.state.y == pytest.approx(20.0)


def test_dispatch_dataclass_skips_properties(timeline):
    import dataclasses

    @dataclasses.dataclass
    class Rect:
        timeline: float = 2.0
        h: float = 3.0

        @property
        def area(self) -> float:
            return self.timeline * self.h

    r = Rect()

    class Model:
        shape = r

    m = Model()
    timeline.animation.track_options = {"A": (m, "shape")}
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(
        0, value=Rect(timeline=2.0, h=3.0), easing=EasingFunction.Step
    )
    timeline.animation.tracks["A"].add_keyframe(100, value=Rect(timeline=4.0, h=6.0))
    timeline._set_playhead(50)
    assert m.shape.timeline == pytest.approx(4.0)


def test_dispatch_dataclass_with_update_method(timeline):
    import dataclasses

    @dataclasses.dataclass
    class Config:
        speed: float = 1.0
        enabled: bool = True

        def update(self, data: dict) -> None:
            for k, v in data.items():
                setattr(self, k, v)

    cfg = Config()

    class Model:
        config = cfg

    m = Model()
    timeline.animation.track_options = {"A": (m, "config")}
    timeline.add_track("A")
    timeline.animation.tracks["A"].add_keyframe(
        0, value=Config(speed=1.0, enabled=True), easing=EasingFunction.Step
    )
    timeline.animation.tracks["A"].add_keyframe(
        100, value=Config(speed=5.0, enabled=False)
    )
    timeline._set_playhead(50)
    assert m.config is cfg and m.config.speed == pytest.approx(5.0)


def test_size_hint(timeline):
    from qtpy.QtCore import QSize

    sh = timeline.sizeHint()
    msh = timeline.minimumSizeHint()
    assert sh.height() >= timeline.top_margin + 4 * timeline.track_height
    assert sh.width() > timeline._left_margin_min
    assert msh.width() <= sh.width() and msh.height() <= sh.height()
    assert isinstance(sh, QSize) and isinstance(msh, QSize)


def test_model_field_interpolation(timeline):
    """Keyframe values that are dataclass instances are interpolated field-by-field."""

    @dataclasses.dataclass
    class Pose:
        x: float = 0.0
        y: float = 0.0
        label: str = "start"

    class Obj:
        def __init__(self):
            self.pos = Pose(0.0, 0.0, "start")

    obj = Obj()
    state = Animation(track_options={"pos": (obj, "pos")})
    track = state.add_track("pos")
    track.add_keyframe(0, Pose(0.0, 0.0, "start"))
    track.add_keyframe(100, Pose(10.0, 20.0, "end"))

    # At 25% of the segment: numeric fields linearly interpolated.
    state.current_frame = 25
    assert obj.pos.x == pytest.approx(2.5)
    assert obj.pos.y == pytest.approx(5.0)
    # String field: Step fallback — holds "start" until p >= 0.5
    assert obj.pos.label == "start"

    # At 60%: string flips to "end" via Step fallback.
    state.current_frame = 60
    assert obj.pos.x == pytest.approx(6.0)
    assert obj.pos.label == "end"
