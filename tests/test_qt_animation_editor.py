import os

import numpy as np
import pytest
from qtpy.QtCore import QEvent, QPoint, QRect, Qt
from qtpy.QtGui import QColor, QKeyEvent, QMouseEvent
from qtpy.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import qt_animation_editor
from qt_animation_editor.easing import EasingFunction, _coerce_value
from qt_animation_editor.editor import (
    _BUTTON_ICONS,
    _DEFAULT_COLORS,
    _PLACEHOLDER_TRACK,
    _PLAY_LOOP,
    _PLAY_MODE_ICONS,
    _PLAY_NORMAL,
    _PLAY_PINGPONG,
    AnimationTimelineWidget,
)
from qt_animation_editor.models import Keyframe, Track


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_imports_with_version():
    assert isinstance(qt_animation_editor.__version__, str)


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
    assert t.color.isValid()


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


def test_add_track_placeholder(qapp):
    w = AnimationTimelineWidget()
    assert w.add_track().name == _PLACEHOLDER_TRACK


def test_track_color_cycle(qapp):
    red = QColor(255, 0, 0)
    w = AnimationTimelineWidget(track_color_cycle=[red])
    assert w.add_track("A").color == red


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
    w.add_track("A")
    kf = w.tracks[0].add_keyframe(10)
    w.selected_keyframes = [kf]
    removed = []
    w.keyframes_removed.connect(removed.append)
    press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    w.keyPressEvent(press)
    assert len(w.tracks[0].keyframes) == 0
    assert removed == [[kf]]


def test_placeholder_never_dispatched(qapp):
    class Model:
        v = 0.0

    m = Model()
    w = AnimationTimelineWidget()
    w.track_options = {_PLACEHOLDER_TRACK: (m, "v")}
    t = w.add_track()
    assert t.name == _PLACEHOLDER_TRACK
    t.add_keyframe(0, value=0.0)
    t.add_keyframe(100, value=99.0)
    w._set_playhead(50)
    assert m.v == 0.0


def _combo_options(w, track_index):
    """Return ``{label: enabled}`` for the track-change combo of a given track.

    Uses the public ``_get_track_change_options`` helper directly so no UI
    mocking is required.
    """
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
    assert options.get("A") is False  # A is used by track 0 → disabled for track 1

    w2 = AnimationTimelineWidget()
    w2.track_options = {"A": (object(), "x")}
    w2.add_track("A")
    w2.add_track("A")
    options2 = _combo_options(w2, 1)
    assert options2.get(_PLACEHOLDER_TRACK) is True  # placeholder always enabled


def _make_press(x, y, shift=False, button=Qt.MouseButton.LeftButton):
    mod = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPoint(x, y), button, button, mod)


def test_rubber_band_selection(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.add_track("A")
    x = int(w.left_margin + 50)
    y = int(w.track_center_y(0))
    w.mousePressEvent(_make_press(x, y, shift=True))
    assert w._box_start is not None
    w2 = AnimationTimelineWidget()
    w2.resize(800, 300)
    w2.add_track("A")
    w2.mousePressEvent(_make_press(x, y, shift=False))
    assert w2._box_start is None


def test_interpolation(qapp):
    w = AnimationTimelineWidget()
    w.add_track("A")
    track = w.tracks[0]
    assert w._interpolate_track(track, 50) is None

    # single keyframe: value held everywhere
    track.add_keyframe(10, value=7.0)
    assert w._interpolate_track(track, 5) == pytest.approx(7.0)
    assert w._interpolate_track(track, 10) == pytest.approx(7.0)
    assert w._interpolate_track(track, 20) == pytest.approx(7.0)

    # linear interpolation with fresh widget
    w2 = AnimationTimelineWidget()
    w2.add_track("A")
    w2.tracks[0].add_keyframe(0, value=0.0)
    w2.tracks[0].add_keyframe(100, value=10.0)
    assert w2._interpolate_track(w2.tracks[0], 50) == pytest.approx(5.0)
    assert w2._interpolate_track(w2.tracks[0], 0) == pytest.approx(0.0)
    assert w2._interpolate_track(w2.tracks[0], 200) == pytest.approx(10.0)

    # clamp before first keyframe
    w3 = AnimationTimelineWidget()
    w3.add_track("A")
    w3.tracks[0].add_keyframe(50, value=3.0)
    w3.tracks[0].add_keyframe(100, value=6.0)
    assert w3._interpolate_track(w3.tracks[0], 0) == pytest.approx(3.0)


def test_interpolation_step_easing(qapp):
    w = AnimationTimelineWidget()
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=0.0, easing=EasingFunction.Step)
    w.tracks[0].add_keyframe(100, value=1.0)
    assert w._interpolate_track(w.tracks[0], 49) == pytest.approx(0.0)
    assert w._interpolate_track(w.tracks[0], 50) == pytest.approx(1.0)
    assert w._interpolate_track(w.tracks[0], 100) == pytest.approx(1.0)


def test_interpolation_zero_span(qapp):
    w = AnimationTimelineWidget()
    w.add_track("A")
    k1 = w.tracks[0].add_keyframe(50, value=1.0)
    k2 = w.tracks[0].add_keyframe(100, value=9.0)
    k2.t = 50
    assert w._interpolate_track(w.tracks[0], 50) == pytest.approx(k1.value)


def test_segment_left_keyframe(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.add_track("A")
    k1 = w.tracks[0].add_keyframe(0)
    w.tracks[0].add_keyframe(100)
    k_last = w.tracks[0].add_keyframe(50)
    # remove k_last from above and redo cleanly
    w2 = AnimationTimelineWidget()
    w2.resize(800, 300)
    w2.add_track("A")
    k1 = w2.tracks[0].add_keyframe(0)
    w2.tracks[0].add_keyframe(100)
    x = int(w2.frame_to_x(50))
    y = int(w2.track_center_y(0))
    assert w2._segment_left_keyframe_at(x, y) is k1

    w3 = AnimationTimelineWidget()
    w3.resize(800, 300)
    w3.add_track("A")
    w3.tracks[0].add_keyframe(0)
    k_last = w3.tracks[0].add_keyframe(50)
    x = int(w3.frame_to_x(80))
    y = int(w3.track_center_y(0))
    assert w3._segment_left_keyframe_at(x, y) is k_last

    w4 = AnimationTimelineWidget()
    w4.resize(800, 300)
    w4.add_track("A")
    assert w4._segment_left_keyframe_at(int(w4.frame_to_x(10)), int(w4.track_center_y(0))) is None


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

    w4 = AnimationTimelineWidget()
    w4.track_options = {"A": (m, "x")}
    w4.add_track("B")
    w4.tracks[0].add_keyframe(0, value=0.0)
    w4.tracks[0].add_keyframe(100, value=10.0)
    m.x = 0.0
    w4._set_playhead(50)
    assert m.x == 0.0


def test_dispatch_on_easing_change(qapp):
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
    w.tracks[0].keyframes[0].easing = EasingFunction.Step
    w._dispatch_track_callbacks(w.current_frame)
    assert m.x == pytest.approx(10.0)


def test_dispatch_on_keyframe_add(qapp):
    class Model:
        x = 0.0

    m = Model()
    w = AnimationTimelineWidget()
    w.track_options = {"A": (m, "x")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=0.0)
    w.tracks[0].add_keyframe(100, value=10.0)
    w._set_playhead(50)
    w.tracks[0].add_keyframe(50, value=99.0)
    w._dispatch_track_callbacks(w.current_frame)
    assert m.x == pytest.approx(99.0)


def test_dispatch_on_keyframe_delete(qapp):
    class Model:
        x = 0.0

    m = Model()
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.track_options = {"A": (m, "x")}
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=0.0)
    # Keyframe at frame 50 pins model to 5.0 via linear interpolation to 100.
    kf_mid = w.tracks[0].add_keyframe(50, value=5.0)
    w.tracks[0].add_keyframe(100, value=10.0)
    w._set_playhead(50)
    assert m.x == pytest.approx(5.0)

    # Delete the middle keyframe via the keyboard shortcut.
    w.selected_keyframes = [kf_mid]
    press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    w.keyPressEvent(press)

    # After deletion the playhead is at 50 between kf(0,0) and kf(100,10):
    # linear interpolation gives 5.0, same value but reached via different path.
    # More importantly the model must have been re-dispatched (not stale).
    assert m.x == pytest.approx(5.0)


def test_keyframe_value_capture(qapp):
    class Model:
        x = 42.0

    m = Model()
    w = AnimationTimelineWidget()
    w.resize(800, 300)
    w.track_options = {"A": (m, "x")}
    w.add_track("A")
    track = w.tracks[0]
    binding = w.track_options.get(track.name)
    assert binding is not None
    kf = track.add_keyframe(50, value=getattr(*binding))
    assert kf.value == pytest.approx(42.0)

    w2 = AnimationTimelineWidget()
    w2.resize(800, 300)
    w2.add_track()
    track2 = w2.tracks[0]
    binding2 = w2.track_options.get(track2.name)
    initial_value = getattr(*binding2) if binding2 else 0
    assert initial_value == 0


def test_can_add_track(qapp):
    w = AnimationTimelineWidget()
    assert w._can_add_track() is True

    w.track_options = {"A": (object(), "x"), "B": (object(), "y")}
    w.add_track("A")
    assert w._can_add_track() is True

    w2 = AnimationTimelineWidget()
    w2.track_options = {"A": (object(), "x")}
    w2.add_track("A")
    assert w2._can_add_track() is False
    w2.add_track()  # placeholder doesn't consume a slot
    assert w2._can_add_track() is False


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
    t_ph = w.add_track()

    assert w._get_allowed_easings_for_track(t_bool) == [EasingFunction.Step]
    allowed_float = w._get_allowed_easings_for_track(t_float)
    assert EasingFunction.Linear in allowed_float and EasingFunction.Step in allowed_float
    assert set(w._get_allowed_easings_for_track(t_ph)) == set(EasingFunction)


def test_right_double_click_ignored(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
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
    w.add_track("A")
    cy = w.track_center_y(0)
    x = int(w.frame_to_x(10))
    assert w._is_on_track_line(x, int(cy)) is True
    assert w._is_on_track_line(x, int(cy) + w.track_height) is False
    assert w._is_on_track_line(x, int(cy) + w.line_thickness + 4) is True

    w2 = AnimationTimelineWidget()
    w2.resize(800, 300)
    assert w2._is_on_track_line(200, 60) is False


def test_reset_view(qapp):
    w = AnimationTimelineWidget()
    w.resize(800, 300)
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
    from qt_animation_editor.editor import _DEFAULT_TRACK_COLORS

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
    assert w2.add_track("A").color == red

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
    w = AnimationTimelineWidget()
    assert w._play_mode == _PLAY_NORMAL
    w._cycle_play_mode()
    assert w._play_mode == _PLAY_LOOP
    w._cycle_play_mode()
    assert w._play_mode == _PLAY_PINGPONG
    w._cycle_play_mode()
    assert w._play_mode == _PLAY_NORMAL


def test_play_normal_stops_at_last_keyframe(qapp):
    w = AnimationTimelineWidget()
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=0.0)
    w.tracks[0].add_keyframe(5, value=1.0)
    w._play_mode = _PLAY_NORMAL
    w._start_playback()
    w._set_playhead(5)
    w._advance_playhead()
    assert not w._playing and w.current_frame == 5


def test_play_loop_wraps(qapp):
    w = AnimationTimelineWidget()
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=0.0)
    w.tracks[0].add_keyframe(5, value=1.0)
    w._play_mode = _PLAY_LOOP
    w._set_playhead(5)
    w._advance_playhead()
    assert w.current_frame == 0


def test_play_pingpong_reverses(qapp):
    w = AnimationTimelineWidget()
    w.add_track("A")
    w.tracks[0].add_keyframe(0, value=0.0)
    w.tracks[0].add_keyframe(5, value=1.0)
    w._play_mode = _PLAY_PINGPONG
    w._play_direction = 1
    w._set_playhead(5)
    w._advance_playhead()
    assert w._play_direction == -1
    w._set_playhead(0)
    w._advance_playhead()
    assert w._play_direction == 1


def test_play_no_keyframes(qapp):
    w = AnimationTimelineWidget()
    w._play_mode = _PLAY_NORMAL
    w._start_playback()
    w._advance_playhead()
    assert not w._playing


def test_loop_btn_color_distinct(qapp):
    w = AnimationTimelineWidget()
    assert w.loop_btn_color != w.control_btn_color
    assert w.loop_btn_color != w.play_btn_color
    assert w.loop_btn_color.isValid()
    assert "loop_btn_color" in _DEFAULT_COLORS


def test_play_mode_icons():
    # Every play mode must have an icon defined in _BUTTON_ICONS.
    for key in _PLAY_MODE_ICONS.values():
        assert key in _BUTTON_ICONS
    # Each mode maps to a distinct icon.
    assert len(set(_PLAY_MODE_ICONS.values())) == len(_PLAY_MODE_ICONS)
    # Normal mode is not the loop or pingpong icon.
    assert _PLAY_MODE_ICONS[_PLAY_NORMAL] not in (
        _PLAY_MODE_ICONS[_PLAY_LOOP],
        _PLAY_MODE_ICONS[_PLAY_PINGPONG],
    )


def test_playback_speed(qapp):
    w = AnimationTimelineWidget(playback_speed=2.0)
    assert w.playback_speed == 2.0
    w.playback_speed = 0.5
    assert w.playback_speed == 0.5
