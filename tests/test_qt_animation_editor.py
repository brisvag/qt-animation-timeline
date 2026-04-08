import os

import pytest
from qtpy.QtCore import QEvent, QRect, Qt
from qtpy.QtGui import QKeyEvent
from qtpy.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import qt_animation_editor
from qt_animation_editor.editor import (
    AnimationTimelineWidget,
    EasingFunction,
    Keyframe,
    Track,
)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_imports_with_version():
    assert isinstance(qt_animation_editor.__version__, str)


class TestEasingFunction:
    def test_linear_midpoint(self):
        assert EasingFunction.Linear(0.5) == pytest.approx(0.5)

    def test_linear_bounds(self):
        assert EasingFunction.Linear(0.0) == pytest.approx(0.0)
        assert EasingFunction.Linear(1.0) == pytest.approx(1.0)

    def test_bool_before_end(self):
        assert EasingFunction.Bool(0.0) == pytest.approx(0.0)
        assert EasingFunction.Bool(0.999) == pytest.approx(0.0)

    def test_bool_at_end(self):
        assert EasingFunction.Bool(1.0) == pytest.approx(1.0)

    def test_members_are_callable(self):
        for ef in EasingFunction:
            assert callable(ef)


class TestKeyframe:
    def test_clamps_negative_t(self):
        assert Keyframe(-5).t == 0

    def test_default_easing(self):
        assert Keyframe(10).easing is EasingFunction.Linear

    def test_custom_easing(self):
        kf = Keyframe(5, easing=EasingFunction.Bool)
        assert kf.easing is EasingFunction.Bool


class TestTrack:
    def test_add_keyframe(self):
        t = Track("X")
        kf = t.add_keyframe(10)
        assert kf.t == 10
        assert kf in t.keyframes

    def test_duplicate_raises(self):
        t = Track("X")
        t.add_keyframe(10)
        with pytest.raises(KeyError):
            t.add_keyframe(10)

    def test_keyframes_sorted(self):
        t = Track("X")
        t.add_keyframe(30)
        t.add_keyframe(10)
        t.add_keyframe(20)
        assert [kf.t for kf in t.keyframes] == [10, 20, 30]

    def test_default_color_is_valid(self):
        assert Track("X").color.isValid()


class TestAnimationTimelineWidget:
    def test_coordinate_roundtrip(self, qapp):
        w = AnimationTimelineWidget()
        for frame in [0, 10, 100, 500]:
            assert w.x_to_frame(w.frame_to_x(frame)) == frame

    def test_track_center_y(self, qapp):
        w = AnimationTimelineWidget()
        expected = w.top_margin + w.track_height / 2
        assert w.track_center_y(0) == expected

    def test_add_track_emits_signal(self, qapp):
        w = AnimationTimelineWidget()
        received = []
        w.track_added.connect(received.append)
        track = w.add_track("A")
        assert track in w.tracks
        assert received == [track]

    def test_add_track_returns_track(self, qapp):
        w = AnimationTimelineWidget()
        track = w.add_track("A")
        assert isinstance(track, Track)
        assert track.name == "A"

    def test_add_track_default_name_from_options(self, qapp):
        """Without an explicit name, the first track_options key is used."""
        w = AnimationTimelineWidget()
        w.track_options = {"X": lambda v: None, "Y": lambda v: None}
        track = w.add_track()
        assert track.name == "X"

    def test_track_colors_are_settable(self, qapp):
        from qtpy.QtGui import QColor

        w = AnimationTimelineWidget()
        red = QColor(255, 0, 0)
        w.track_colors = [red]
        track = w.add_track("A")
        assert track.color == red

    def test_easing_options_are_settable(self, qapp):
        w = AnimationTimelineWidget()
        w.easing_options = [EasingFunction.Bool]
        assert w.easing_options == [EasingFunction.Bool]

    def test_set_playhead_emits_signal(self, qapp):
        w = AnimationTimelineWidget()
        frames = []
        w.playhead_moved.connect(frames.append)
        w._set_playhead(10)
        assert w.current_frame == 10
        assert frames == [10]

    def test_set_playhead_no_duplicate_signal(self, qapp):
        """Setting the playhead to the same frame must not re-emit the signal."""
        w = AnimationTimelineWidget()
        w._set_playhead(5)
        frames = []
        w.playhead_moved.connect(frames.append)
        w._set_playhead(5)
        assert frames == []

    def test_pos_to_keyframe_hit(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        w.tracks[0].add_keyframe(10)
        x = w.frame_to_x(10)
        y = w.track_center_y(0)
        assert w.pos_to_keyframe(x, y) is not None

    def test_pos_to_keyframe_miss(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        w.tracks[0].add_keyframe(10)
        assert w.pos_to_keyframe(0, 0) is None

    def test_keyframes_in_rect(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        w.tracks[0].add_keyframe(10)
        w.tracks[0].add_keyframe(100)
        # Build a rect that contains frame 10 but not frame 100.
        cx10 = int(w.frame_to_x(10))
        cy = int(w.track_center_y(0))
        rect = QRect(cx10 - 20, cy - 20, 40, 40)
        hits = w._keyframes_in_rect(rect)
        assert len(hits) == 1
        assert hits[0].t == 10

    def test_delete_keyframes_emits_signal(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        kf = w.tracks[0].add_keyframe(10)
        w.selected_keyframes = [kf]

        removed = []
        w.keyframes_removed.connect(removed.append)

        press = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier
        )
        w.keyPressEvent(press)
        assert len(w.tracks[0].keyframes) == 0
        assert removed == [[kf]]


class TestInterpolation:
    def _make_widget(self, qapp):
        w = AnimationTimelineWidget()
        w.add_track("A")
        return w

    def test_no_keyframes_returns_none(self, qapp):
        w = self._make_widget(qapp)
        assert w._interpolate_track(w.tracks[0], 50) is None

    def test_single_keyframe_returns_its_value(self, qapp):
        w = self._make_widget(qapp)
        w.tracks[0].add_keyframe(10, value=7.0)
        assert w._interpolate_track(w.tracks[0], 5) == pytest.approx(7.0)
        assert w._interpolate_track(w.tracks[0], 10) == pytest.approx(7.0)
        assert w._interpolate_track(w.tracks[0], 20) == pytest.approx(7.0)

    def test_linear_interpolation_midpoint(self, qapp):
        w = self._make_widget(qapp)
        w.tracks[0].add_keyframe(0, value=0.0)
        w.tracks[0].add_keyframe(100, value=10.0)
        assert w._interpolate_track(w.tracks[0], 50) == pytest.approx(5.0)

    def test_before_first_keyframe_clamps(self, qapp):
        w = self._make_widget(qapp)
        w.tracks[0].add_keyframe(50, value=3.0)
        w.tracks[0].add_keyframe(100, value=6.0)
        assert w._interpolate_track(w.tracks[0], 0) == pytest.approx(3.0)

    def test_after_last_keyframe_clamps(self, qapp):
        w = self._make_widget(qapp)
        w.tracks[0].add_keyframe(0, value=0.0)
        w.tracks[0].add_keyframe(100, value=5.0)
        assert w._interpolate_track(w.tracks[0], 200) == pytest.approx(5.0)

    def test_bool_easing_holds_then_jumps(self, qapp):
        w = self._make_widget(qapp)
        # Segment uses Bool easing: holds 0 until the very end of the interval.
        w.tracks[0].add_keyframe(0, value=0.0, easing=EasingFunction.Bool)
        w.tracks[0].add_keyframe(100, value=1.0)
        assert w._interpolate_track(w.tracks[0], 50) == pytest.approx(0.0)
        assert w._interpolate_track(w.tracks[0], 100) == pytest.approx(1.0)


class TestTrackCallbackDispatch:
    def test_callback_called_on_playhead_move(self, qapp):
        w = AnimationTimelineWidget()
        received = []
        w.track_options = {"A": received.append}
        w.add_track("A")
        w.tracks[0].add_keyframe(0, value=0.0)
        w.tracks[0].add_keyframe(100, value=10.0)

        w._set_playhead(50)
        assert len(received) == 1
        assert received[0] == pytest.approx(5.0)

    def test_no_callback_for_unregistered_track(self, qapp):
        w = AnimationTimelineWidget()
        received = []
        w.track_options = {"A": received.append}
        w.add_track("B")  # name not in track_options
        w.tracks[0].add_keyframe(0, value=0.0)
        w.tracks[0].add_keyframe(100, value=10.0)

        w._set_playhead(50)
        assert received == []
