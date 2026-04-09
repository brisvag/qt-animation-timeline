import os
import dataclasses

import numpy as np
import pytest
from qtpy.QtCore import QEvent, QPoint, QRect, Qt
from qtpy.QtGui import QColor, QKeyEvent, QMouseEvent
from qtpy.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import qt_animation_timeline
from qt_animation_timeline.easing import EasingFunction, _coerce_value
from qt_animation_timeline.editor import (
    _BUTTON_ICONS,
    _DEFAULT_COLORS,
    _PLAY_MODE_ICONS,
    AnimationTimelineWidget,
)
from qt_animation_timeline.models import (
    Animation,
    Keyframe,
    PLAY_LOOP,
    PLAY_NORMAL,
    PLAY_PINGPONG,
    Track,
)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_imports_with_version():
    assert isinstance(qt_animation_timeline.__version__, str)
    assert hasattr(qt_animation_timeline, "Animation")



def test_easing_linear(qapp):
    assert EasingFunction.Linear(0.0, 0.0, 1.0) == pytest.approx(0.0)
    assert EasingFunction.Linear(0.5, 0.0, 1.0) == pytest.approx(0.5)
    assert EasingFunction.Linear(1.0, 0.0, 1.0) == pytest.approx(1.0)
    assert EasingFunction.Linear(0.5, 10.0, 20.0) == pytest.approx(15.0)


def test_easing_step(qapp):
    assert EasingFunction.Step(0.0, 0.0, 1.0) == pytest.approx(0.0)
    assert EasingFunction.Step(0.49, 0.0, 1.0) == pytest.approx(0.0)
    assert EasingFunction.Step(0.5, 0.0, 1.0) == pytest.approx(1.0)
    assert EasingFunction.Step(1.0, 0.0, 1.0) == pytest.approx(1.0)
    assert EasingFunction.Step(0.3, "a", "b") == "a"
    assert EasingFunction.Step(0.5, "a", "b") == "b"


def test_easing_members_callable():
    for ef in EasingFunction:
        assert callable(ef)


def test_coerce_value():
    assert isinstance(_coerce_value(1.0, 2.5), float)
    assert _coerce_value(1.0, 2.5) == pytest.approx(2.5)
    result = _coerce_value(1, 2.7)
    assert isinstance(result, int) and result == 3
    assert _coerce_value(True, 0.6) is True
    assert _coerce_value(False, 0.4) is False
    assert type(_coerce_value(False, 1.0)) is bool
    obj = object()
    assert _coerce_value(obj, 3.14) == 3.14


def test_keyframe():
    assert Keyframe(-5).t == 0
    assert Keyframe(10).easing is EasingFunction.Linear
    kf = Keyframe(5, easing=EasingFunction.Step)
    assert kf.easing is EasingFunction.Step


def test_track():
    t = Track("X")
    kf = t.add_keyframe(10)
    assert kf.t == 10 and kf in t.keyframes
    with pytest.raises(KeyError):
        t.add_keyframe(10)
    t.add_keyframe(30)
    t.add_keyframe(5)
    assert [k.t for k in t.keyframes] == [5, 10, 30]
    assert len(t.color) == 3  # RGB tuple
    assert all(isinstance(c, int) for c in t.color)


def test_coordinate_roundtrip(qapp):
    w = AnimationTimelineWidget()
    for frame in [0, 10, 100, 500]:
        assert w.x_to_frame(w.frame_to_x(frame)) == frame
    assert w.left_timeline_pad > 0
    assert w.frame_to_x(0) > w.left_margin


def test_track_center_y(qapp):
    w = AnimationTimelineWidget()
    assert w.track_center_y(0) == w.top_margin + w.track_height / 2


def test_add_track(qapp):
    w = AnimationTimelineWidget()
    received = []
    w.track_added.connect(received.append)
    track = w.add_track("A")
    assert isinstance(track, Track)
    assert track.name == "A"
    assert track in w.tracks
    assert received == [track]


def test_track_color_cycle(qapp):
    red = QColor(255, 0, 0)
    w = AnimationTimelineWidget(track_color_cycle=[red])
    track = w.add_track("A")
    assert track.color == (255, 0, 0)


def test_easing_options_settable(qapp):
    w = AnimationTimelineWidget()
    w.easing_options = [EasingFunction.Step]
    assert w.easing_options == [EasingFunction.Step]


def test_set_playhead(qapp):
    w = AnimationTimelineWidget()
    frames = []
    w.playhead_moved.connect(frames.append)
    w._set_playhead(10)
    assert w.current_frame == 10 and frames == [10]
    w._set_playhead(10)
    assert frames == [10]  # no duplicate signal


def test_pos_to_keyframe(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.add_track("A")
    w.tracks[0].add_keyframe(10)
    x, y = w.frame_to_x(10), w.track_center_y(0)
    assert w.pos_to_keyframe(x, y) is not None
    assert w.pos_to_keyframe(0, 0) is None


def test_keyframes_in_rect(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.add_track("A")
    w.tracks[0].add_keyframe(10)
    w.tracks[0].add_keyframe(100)
    cx10 = int(w.frame_to_x(10))
    cy = int(w.track_center_y(0))
    rect = QRect(cx10 - 20, cy - 20, 40, 40)
    hits = w._keyframes_in_rect(rect)
    assert len(hits) == 1 and hits[0].t == 10


def test_delete_keyframes(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.track_options = {"A": (object(), "x")}
    w.add_track("A")
    kf = w.tracks[0].add_keyframe(10)
    w.selected_keyframes = [kf]
    removed = []
    w.keyframes_removed.connect(removed.append)
    press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    w.keyPressEvent(press)
    assert len(w.tracks[0].keyframes) == 0
    assert removed == [[kf]]


def _combo_options(w, track_index):
    """Return ``{label: enabled}`` for the track-change combo of a given track."""
    if not (0 <= track_index < len(w.tracks)):
        return {}
    track = w.tracks[track_index]
    return dict(w._get_track_change_options(track))


def test_unique_track_options(qapp):
    w = AnimationTimelineWidget()
    w.track_options = {"A": (object(), "x"), "B": (object(), "y")}
    w.add_track("A")
    w.add_track("B")
    options = _combo_options(w, 1)
    assert options.get("A") is False  # A is used by track 0 -> disabled for track 1
    assert options.get("B") is True   # B is the current track's own name


def _make_press(x, y, shift=False, button=Qt.MouseButton.LeftButton):
    mod = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPoint(x, y), button, button, mod)


def test_rubber_band_selection(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.add_track("A")
    x = int(w.left_margin + 50)
    y = int(w.track_center_y(0))
    # Shift+click starts rubber-band; plain click does not.
    w.mousePressEvent(_make_press(x, y, shift=True))
    assert w._box_start is not None
    w2 = AnimationTimelineWidget()
    w2.resize(800, 300)
    w2.add_track("A")
    w2.mousePressEvent(_make_press(x, y, shift=False))
    assert w2._box_start is None


def test_interpolation(qapp):
    w = AnimationTimelineWidget()
    w.track_options = {"A": (object(), "x")}
    w.add_track("A")
    track = w.tracks[0]
    assert w._interpolate_track(track, 50) is None

    track.add_keyframe(10, value=7.0)
    assert w._interpolate_track(track, 5) == pytest.approx(7.0)
    assert w._interpolate_track(track, 10) == pytest.approx(7.0)
    assert w._interpolate_track(track, 20) == pytest.approx(7.0)

    w2 = AnimationTimelineWidget()
    w2.track_options = {"A": (object(), "x")}
    w2.add_track("A")
    w2.tracks[0].add_keyframe(0, value=0.0)
    w2.tracks[0].add_keyframe(100, value=10.0)
    assert w2._interpolate_track(w2.tracks[0], 50) == pytest.approx(5.0)
    assert w2._interpolate_track(w2.tracks[0], 0) == pytest.approx(0.0)
    assert w2._interpolate_track(w2.tracks[0], 200) == pytest.approx(10.0)

    # clamp before first keyframe
    w3 = AnimationTimelineWidget()
    w3.track_options = {"A": (object(), "x")}
    w3.add_track("A")
    w3.tracks[0].add_keyframe(50, value=3.0)
    w3.tracks[0].add_keyframe(100, value=6.0)
    assert w3._interpolate_track(w3.tracks[0], 0) == pytest.approx(3.0)


def test_interpolation_step_easing(qapp):
    w = AnimationTimelineWidget()
    w.track_options = {"A": (object(), "x")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=0.0, easing=EasingFunction.Step)
    w.tracks[0].add_keyframe(100, value=1.0)
    assert w._interpolate_track(w.tracks[0], 49) == pytest.approx(0.0)
    assert w._interpolate_track(w.tracks[0], 50) == pytest.approx(1.0)
    assert w._interpolate_track(w.tracks[0], 100) == pytest.approx(1.0)


def test_interpolation_zero_span(qapp):
    w = AnimationTimelineWidget()
    w.track_options = {"A": (object(), "x")}
    w.add_track("A")
    k1 = w.tracks[0].add_keyframe(50, value=1.0)
    k2 = w.tracks[0].add_keyframe(100, value=9.0)
    k2.t = 50
    assert w._interpolate_track(w.tracks[0], 50) == pytest.approx(k1.value)


def test_segment_left_keyframe(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.track_options = {"A": (object(), "x")}
    w.add_track("A")
    k1 = w.tracks[0].add_keyframe(0)
    w.tracks[0].add_keyframe(100)
    x = int(w.frame_to_x(50))
    y = int(w.track_center_y(0))
    assert w._segment_left_keyframe_at(x, y) is k1

    w2 = AnimationTimelineWidget()
    w2.resize(800, 300)
    w2.track_options = {"A": (object(), "x")}
    w2.add_track("A")
    w2.tracks[0].add_keyframe(0)
    k_last = w2.tracks[0].add_keyframe(50)
    x2 = int(w2.frame_to_x(80))
    y2 = int(w2.track_center_y(0))
    assert w2._segment_left_keyframe_at(x2, y2) is k_last

    # empty track returns None
    w3 = AnimationTimelineWidget()
    w3.resize(800, 300)
    w3.track_options = {"A": (object(), "x")}
    w3.add_track("A")
    assert w3._segment_left_keyframe_at(int(w3.frame_to_x(10)), int(w3.track_center_y(0))) is None


def test_track_model_dispatch(qapp):
    class Model:
        x = 0.0
        n = 0
        flag = False

    m = Model()
    w = AnimationTimelineWidget()
    w.track_options = {"A": (m, "x")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=0.0)
    w.tracks[0].add_keyframe(100, value=10.0)
    w._set_playhead(50)
    assert m.x == pytest.approx(5.0)

    w2 = AnimationTimelineWidget()
    w2.track_options = {"A": (m, "n")}
    w2.add_track("A")
    w2.tracks[0].add_keyframe(0, value=0)
    w2.tracks[0].add_keyframe(10, value=10)
    w2._set_playhead(3)
    assert isinstance(m.n, int) and m.n == 3

    w3 = AnimationTimelineWidget()
    w3.track_options = {"A": (m, "flag")}
    w3.add_track("A")
    w3.tracks[0].add_keyframe(0, value=0.0, easing=EasingFunction.Step)
    w3.tracks[0].add_keyframe(100, value=1.0)
    w3._set_playhead(49)
    assert m.flag is False
    w3._set_playhead(50)
    assert m.flag is True

    # unbound track (no matching option) should not dispatch
    w4 = AnimationTimelineWidget()
    w4.track_options = {"A": (m, "x")}
    w4.add_track("B")  # "B" has no binding
    w4.tracks[0].add_keyframe(0, value=0.0)
    w4.tracks[0].add_keyframe(100, value=10.0)
    m.x = 0.0
    w4._set_playhead(50)
    assert m.x == 0.0


def test_dispatch_on_easing_and_keyframe_change(qapp):
    class Model:
        x = 0.0

    m = Model()
    w = AnimationTimelineWidget()
    w.track_options = {"A": (m, "x")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=0.0)
    w.tracks[0].add_keyframe(100, value=10.0)
    w._set_playhead(50)
    assert m.x == pytest.approx(5.0)

    # Changing easing should re-dispatch.
    w.tracks[0].keyframes[0].easing = EasingFunction.Step
    w._dispatch_track_callbacks(w.current_frame)
    assert m.x == pytest.approx(10.0)

    # Adding a keyframe at the playhead should re-dispatch.
    w.state.add_keyframe(w.tracks[0], 50, value=99.0)
    assert m.x == pytest.approx(99.0)


def test_can_add_track(qapp):
    w = AnimationTimelineWidget()
    # No track_options -> cannot add (popup has nothing to show)
    assert w._can_add_track() is False

    w2 = AnimationTimelineWidget()
    w2.track_options = {"A": (object(), "x"), "B": (object(), "y")}
    assert w2._can_add_track() is True
    w2.add_track("A")
    assert w2._can_add_track() is True  # B still available
    w2.add_track("B")
    assert w2._can_add_track() is False  # all used


def test_available_track_options(qapp):
    state = Animation(track_options={"A": (object(), "x"), "B": (object(), "y")})
    state.add_track("A")
    avail = state.available_track_options()
    assert "B" in avail and "A" not in avail


def test_zoom_step(qapp):
    w = AnimationTimelineWidget()
    for fw in [0.05, 0.1, 0.2, 1, 5, 15, 50, 60]:
        w.frame_width = fw
        step = w.zoom_step()
        assert step >= 1
        s = step
        while s > 9:
            s //= 10
        assert s in (1, 2, 5)
    w.frame_width = 0.1
    assert w.zoom_step() >= 100
    w.frame_width = 60.0
    assert w.zoom_step() == 1


def test_easing_preselection(qapp):
    class Model:
        flag: bool = True
        x: float = 0.0

    m = Model()
    w = AnimationTimelineWidget()
    w.track_options = {"flag": (m, "flag"), "x": (m, "x")}
    t_bool = w.add_track("flag")
    t_float = w.add_track("x")

    assert w._get_allowed_easings_for_track(t_bool) == [EasingFunction.Step]
    allowed_float = w._get_allowed_easings_for_track(t_float)
    assert EasingFunction.Linear in allowed_float and EasingFunction.Step in allowed_float


def test_right_double_click_ignored(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.track_options = {"A": (object(), "x")}
    w.add_track("A")
    x = int(w.frame_to_x(50))
    y = int(w.track_center_y(0))
    event = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        QPoint(x, y),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    w.mouseDoubleClickEvent(event)
    assert len(w.tracks[0].keyframes) == 0


def test_is_on_track_line(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.track_options = {"A": (object(), "x")}
    w.add_track("A")
    cy = w.track_center_y(0)
    x = int(w.frame_to_x(10))
    assert w._is_on_track_line(x, int(cy)) is True
    assert w._is_on_track_line(x, int(cy) + w.track_height) is False
    assert w._is_on_track_line(x, int(cy) + w.line_thickness + 4) is True
    # No tracks: always False
    assert AnimationTimelineWidget()._is_on_track_line(200, 60) is False


def test_reset_view(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.track_options = {"A": (object(), "x")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=0.0)
    w.tracks[0].add_keyframe(200, value=1.0)
    w._reset_view()
    assert w.scroll_x == 0
    assert w.frame_to_x(0) == pytest.approx(w.left_margin + w.left_timeline_pad)
    assert w.frame_to_x(200) < w.width()

    w2 = AnimationTimelineWidget()
    w2.resize(800, 300)
    w2._reset_view()
    assert w2.scroll_x == 0 and w2.frame_width > 0


def test_default_colors(qapp):
    from qt_animation_timeline.editor import _DEFAULT_TRACK_COLORS

    assert len(_DEFAULT_TRACK_COLORS) == 7
    for c in _DEFAULT_TRACK_COLORS:
        assert c.isValid()
    c0 = _DEFAULT_TRACK_COLORS[0]
    assert (c0.red(), c0.green(), c0.blue()) == (0, 114, 178)


def test_numpy_interpolation(qapp):
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

    w = AnimationTimelineWidget()
    w.track_options = {"A": (object(), "angles")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=np.array([0.0, 0.0]))
    w.tracks[0].add_keyframe(100, value=np.array([10.0, 20.0]))
    np.testing.assert_allclose(w._interpolate_track(w.tracks[0], 50), [5.0, 10.0])

    class Model:
        angles = np.array([0.0, 0.0, 0.0])

    m = Model()
    w2 = AnimationTimelineWidget()
    w2.track_options = {"A": (m, "angles")}
    w2.add_track("A")
    w2.tracks[0].add_keyframe(0, value=np.array([0.0, 0.0, 0.0]))
    w2.tracks[0].add_keyframe(100, value=np.array([10.0, 20.0, 30.0]))
    w2._set_playhead(50)
    np.testing.assert_allclose(m.angles, [5.0, 10.0, 15.0])


def test_constructor_kwargs(qapp):
    red = QColor(255, 0, 0)
    w = AnimationTimelineWidget(bg_color=red)
    assert w.bg_color == red

    for key in _DEFAULT_COLORS:
        assert hasattr(AnimationTimelineWidget(), key)

    w2 = AnimationTimelineWidget(track_color_cycle=[red])
    assert w2.add_track("A").color == (255, 0, 0)

    class Model:
        x = 0.0

    m = Model()
    w3 = AnimationTimelineWidget(track_options={"A": (m, "x")})
    assert "A" in w3.track_options

    w4 = AnimationTimelineWidget(font_size=14)
    assert w4.font_size == 14 and w4.label_font.pointSize() == 14

    w5 = AnimationTimelineWidget(playback_speed=2.0)
    assert w5.playback_speed == 2.0


def test_arrow_keys(qapp):
    def key_press(key):
        return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)

    w = AnimationTimelineWidget()
    w._set_playhead(5)
    w.keyPressEvent(key_press(Qt.Key.Key_Right))
    assert w.current_frame == 6
    w.keyPressEvent(key_press(Qt.Key.Key_Left))
    assert w.current_frame == 5
    w._set_playhead(0)
    w.keyPressEvent(key_press(Qt.Key.Key_Left))
    assert w.current_frame == 0


def test_play_modes(qapp):
    state = Animation()
    assert state.play_mode == PLAY_NORMAL
    state.cycle_play_mode()
    assert state.play_mode == PLAY_LOOP
    state.cycle_play_mode()
    assert state.play_mode == PLAY_PINGPONG
    state.cycle_play_mode()
    assert state.play_mode == PLAY_NORMAL


def test_play_normal_stops_at_last_keyframe(qapp):
    state = Animation()
    state.add_track("A")
    state.tracks[0].add_keyframe(0, value=0.0)
    state.tracks[0].add_keyframe(5, value=1.0)
    state.play_mode = PLAY_NORMAL
    state.playing = True
    state.current_frame = 5
    state.advance_playhead()
    assert not state.playing and state.current_frame == 5


def test_play_loop_wraps(qapp):
    state = Animation()
    state.add_track("A")
    state.tracks[0].add_keyframe(0, value=0.0)
    state.tracks[0].add_keyframe(5, value=1.0)
    state.play_mode = PLAY_LOOP
    state.current_frame = 5
    state.advance_playhead()
    assert state.current_frame == 0


def test_play_pingpong_reverses(qapp):
    state = Animation()
    state.add_track("A")
    state.tracks[0].add_keyframe(0, value=0.0)
    state.tracks[0].add_keyframe(5, value=1.0)
    state.play_mode = PLAY_PINGPONG
    state.play_direction = 1
    state.current_frame = 5
    state.advance_playhead()
    assert state.play_direction == -1
    state.current_frame = 0
    state.advance_playhead()
    assert state.play_direction == 1


def test_play_no_keyframes(qapp):
    state = Animation()
    state.play_mode = PLAY_NORMAL
    state.playing = True
    state.advance_playhead()
    assert not state.playing


def test_loop_btn_color_distinct(qapp):
    w = AnimationTimelineWidget()
    assert w.loop_btn_color != w.control_btn_color
    assert w.loop_btn_color != w.play_btn_color
    assert w.loop_btn_color.isValid()
    assert "loop_btn_color" in _DEFAULT_COLORS


def test_play_mode_icons():
    for key in _PLAY_MODE_ICONS.values():
        assert key in _BUTTON_ICONS
    assert len(set(_PLAY_MODE_ICONS.values())) == len(_PLAY_MODE_ICONS)
    assert _PLAY_MODE_ICONS[PLAY_NORMAL] not in (
        _PLAY_MODE_ICONS[PLAY_LOOP],
        _PLAY_MODE_ICONS[PLAY_PINGPONG],
    )


def test_playback_speed(qapp):
    w = AnimationTimelineWidget(playback_speed=2.0)
    assert w.playback_speed == 2.0
    w.playback_speed = 0.5
    assert w.playback_speed == 0.5


def test_left_margin_auto_adjusts(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    assert w.left_margin == w._left_margin_min  # no tracks: stays at minimum

    w.track_options = {"A": (object(), "x")}
    w.add_track("A")
    w.update_scrollbars()
    margin_short = w.left_margin

    w.track_options = {"A": (object(), "x"), "A very long track label name": (object(), "y")}
    w.add_track("A very long track label name")
    w.update_scrollbars()
    margin_long = w.left_margin

    assert margin_long > margin_short >= w._left_margin_min


def test_coerce_value_list(qapp):
    ref = [1.0, 2.0, 3.0]
    result = _coerce_value(ref, np.array([1.5, 2.5, 3.5]))
    assert isinstance(result, list)
    assert result == pytest.approx([1.5, 2.5, 3.5])


def test_coerce_value_tuple(qapp):
    ref = (1.0, 2.0)
    result = _coerce_value(ref, np.array([0.5, 1.5]))
    assert isinstance(result, tuple) and result == pytest.approx((0.5, 1.5))


def test_coerce_value_nested_list(qapp):
    ref = [[1.0, 2.0], [3.0, 4.0]]
    result = _coerce_value(ref, np.array([[1.5, 2.5], [3.5, 4.5]]))
    assert isinstance(result, list) and isinstance(result[0], list)
    assert result[0] == pytest.approx([1.5, 2.5])
    assert result[1] == pytest.approx([3.5, 4.5])


def test_interpolate_list_and_tuple_values(qapp):
    w = AnimationTimelineWidget()
    w.track_options = {"A": (object(), "x"), "B": (object(), "y")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=[0.0, 0.0])
    w.tracks[0].add_keyframe(100, value=[10.0, 20.0])
    assert w._interpolate_track(w.tracks[0], 50) == pytest.approx([5.0, 10.0])

    w.add_track("B")
    w.tracks[1].add_keyframe(0, value=(0.0, 100.0))
    w.tracks[1].add_keyframe(100, value=(100.0, 0.0))
    result = w._interpolate_track(w.tracks[1], 50)
    np.testing.assert_allclose(result, [50.0, 50.0])


def test_dispatch_list_and_tuple_cast_back(qapp):
    class Model:
        pos_list = [0.0, 0.0]
        pos_tuple = (0.0, 0.0)

    m = Model()
    w = AnimationTimelineWidget()
    w.track_options = {"A": (m, "pos_list"), "B": (m, "pos_tuple")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=[0.0, 0.0])
    w.tracks[0].add_keyframe(100, value=[10.0, 20.0])
    w.add_track("B")
    w.tracks[1].add_keyframe(0, value=(0.0, 0.0))
    w.tracks[1].add_keyframe(100, value=(10.0, 20.0))
    w._set_playhead(50)
    assert isinstance(m.pos_list, list) and m.pos_list == pytest.approx([5.0, 10.0])
    assert isinstance(m.pos_tuple, tuple) and m.pos_tuple == pytest.approx((5.0, 10.0))


def test_dispatch_dataclass(qapp):
    import dataclasses

    @dataclasses.dataclass
    class Pose:
        x: float = 0.0
        y: float = 0.0

    pose = Pose(x=0.0, y=0.0)

    class Model:
        state = pose

    m = Model()
    w = AnimationTimelineWidget()
    w.track_options = {"A": (m, "state")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=Pose(x=0.0, y=0.0), easing=EasingFunction.Step)
    w.tracks[0].add_keyframe(100, value=Pose(x=10.0, y=20.0))
    w._set_playhead(50)
    assert m.state is pose  # updated in-place, not replaced
    assert m.state.x == pytest.approx(10.0) and m.state.y == pytest.approx(20.0)


def test_dispatch_dataclass_skips_properties(qapp):
    import dataclasses

    @dataclasses.dataclass
    class Rect:
        w: float = 2.0
        h: float = 3.0

        @property
        def area(self) -> float:
            return self.w * self.h

    r = Rect()

    class Model:
        shape = r

    m = Model()
    w = AnimationTimelineWidget()
    w.track_options = {"A": (m, "shape")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=Rect(w=2.0, h=3.0), easing=EasingFunction.Step)
    w.tracks[0].add_keyframe(100, value=Rect(w=4.0, h=6.0))
    w._set_playhead(50)
    assert m.shape.w == pytest.approx(4.0)


def test_dispatch_dataclass_with_update_method(qapp):
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
    w = AnimationTimelineWidget()
    w.track_options = {"A": (m, "config")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=Config(speed=1.0, enabled=True), easing=EasingFunction.Step)
    w.tracks[0].add_keyframe(100, value=Config(speed=5.0, enabled=False))
    w._set_playhead(50)
    assert m.config is cfg and m.config.speed == pytest.approx(5.0)


def test_track_removed_when_option_deleted(qapp):
    w = AnimationTimelineWidget()
    w.track_options = {"A": (object(), "x"), "B": (object(), "y")}
    w.add_track("A")
    w.add_track("B")

    removed = []
    w.track_removed.connect(removed.append)
    del w.track_options["B"]

    assert len(w.tracks) == 1 and w.tracks[0].name == "A"
    assert len(removed) == 1 and removed[0].name == "B"


def test_track_removed_on_options_reassign(qapp):
    w = AnimationTimelineWidget()
    w.track_options = {"A": (object(), "x"), "B": (object(), "y")}
    w.add_track("A")
    w.add_track("B")

    removed = []
    w.track_removed.connect(removed.append)
    w.track_options = {"A": (object(), "x")}

    assert len(w.tracks) == 1 and w.tracks[0].name == "A"
    assert len(removed) == 1


def test_track_options_pop_and_clear(qapp):
    w = AnimationTimelineWidget()
    w.track_options = {"A": (object(), "x"), "B": (object(), "y")}
    w.add_track("A")
    w.add_track("B")
    w.track_options.pop("A")
    assert all(t.name != "A" for t in w.tracks)

    w.track_options.clear()
    assert len(w.tracks) == 0


def test_selected_keyframes_cleared_on_cleanup(qapp):
    w = AnimationTimelineWidget()
    w.track_options = {"A": (object(), "x")}
    w.add_track("A")
    kf = w.tracks[0].add_keyframe(10)
    w.selected_keyframes = [kf]
    del w.track_options["A"]
    assert kf not in w.selected_keyframes


def test_size_hint(qapp):
    from qtpy.QtCore import QSize

    w = AnimationTimelineWidget()
    sh = w.sizeHint()
    msh = w.minimumSizeHint()
    assert sh.height() >= w.top_margin + 4 * w.track_height
    assert sh.width() > w._left_margin_min
    assert msh.width() <= sh.width() and msh.height() <= sh.height()
    assert isinstance(sh, QSize) and isinstance(msh, QSize)


def test_model_field_interpolation(qapp):
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


def test_model_field_step_fallback(qapp):
    """Non-numeric fields silently fall back to Step even when Linear is set."""
    from qt_animation_timeline.models import _interpolate_field

    # Linear on strings should not raise; should behave as Step.
    result_before = _interpolate_field(EasingFunction.Linear, 0.3, "a", "b")
    result_after = _interpolate_field(EasingFunction.Linear, 0.6, "a", "b")
    assert result_before == "a"
    assert result_after == "b"


def test_animation_state_signals(qapp):
    """Animation emits psygnal signals with no Qt dependency in signal logic."""
    state = Animation(track_options={"A": (object(), "x")})

    # Scalar field signals are on .events.<name> (EventedModel style)
    frames = []
    state.events.current_frame.connect(frames.append)
    state.current_frame = 10
    assert frames == [10]
    state.current_frame = 10  # no duplicate
    assert frames == [10]

    tracks_added = []
    state.track_added.connect(tracks_added.append)
    track = state.add_track("A")
    assert len(tracks_added) == 1 and tracks_added[0] is track

    removed = []
    state.track_removed.connect(removed.append)
    state.remove_track(track)
    assert len(removed) == 1 and removed[0] is track

    play_states = []
    state.events.playing.connect(play_states.append)
    state.playing = True
    state.playing = True   # no duplicate
    state.playing = False
    assert play_states == [True, False]


def test_state_keyframe_signals(qapp):
    class Model:
        x = 0.0

    m = Model()
    state = Animation(track_options={"A": (m, "x")})
    track = state.add_track("A")

    kf_events = []
    state.keyframe_added.connect(lambda t, kf: kf_events.append((t, kf)))
    kf = state.add_keyframe(track, 10, value=5.0)
    assert len(kf_events) == 1 and kf_events[0] == (track, kf)

    removed_events = []
    state.keyframes_removed.connect(removed_events.append)
    state.remove_keyframes([kf])
    assert removed_events == [[kf]]

    moved_events = []
    state.keyframes_moved.connect(moved_events.append)
    kf2 = state.add_keyframe(track, 20, value=3.0)
    kf2.t = 30
    state.notify_keyframes_moved([kf2])
    assert moved_events == [[kf2]]

    easing_events = []
    state.easing_changed.connect(easing_events.append)
    kf3 = state.add_keyframe(track, 50, value=1.0)
    kf3.easing = EasingFunction.Step
    state.notify_easing_changed([kf3])
    assert easing_events == [[kf3]]
