import os

import pytest
from qtpy.QtCore import QEvent, QRect, Qt
from qtpy.QtGui import QKeyEvent
from qtpy.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import qt_animation_editor
from qt_animation_editor.editor import (
    EASING_OPTIONS,
    AnimationTimelineWidget,
    Keyframe,
    Track,
)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_imports_with_version():
    assert isinstance(qt_animation_editor.__version__, str)


class TestKeyframe:
    def test_clamps_negative_t(self):
        assert Keyframe(-5).t == 0

    def test_default_easing(self):
        kf = Keyframe(10)
        assert kf.easing_in == "Linear"
        assert kf.easing_out == "Linear"

    def test_custom_easing(self):
        kf = Keyframe(5, easing_in="Ease In", easing_out="Ease Out")
        assert kf.easing_in == "Ease In"
        assert kf.easing_out == "Ease Out"


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


class TestEasingOptions:
    def test_contains_linear(self):
        assert "Linear" in EASING_OPTIONS

    def test_non_empty(self):
        assert len(EASING_OPTIONS) >= 3


class TestAnimationTimelineWidget:
    def test_coordinate_roundtrip(self, qapp):
        w = AnimationTimelineWidget()
        for frame in [0, 10, 100, 500]:
            assert w.x_to_frame(w.frame_to_x(frame)) == frame

    def test_track_center_y(self, qapp):
        w = AnimationTimelineWidget()
        # With no scrolling: centre of track 0 is top_margin + track_height/2.
        expected = w.top_margin + w.track_height / 2
        assert w.track_center_y(0) == expected

    def test_add_track_emits_signal(self, qapp):
        w = AnimationTimelineWidget()
        received = []
        w.track_added.connect(received.append)
        track = w.add_track("Rotation")
        assert track in w.tracks
        assert received == [track]

    def test_add_track_returns_track(self, qapp):
        w = AnimationTimelineWidget()
        track = w.add_track("Location X")
        assert isinstance(track, Track)
        assert track.name == "Location X"

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
        w.add_track("X")
        w.tracks[0].add_keyframe(10)
        x = w.frame_to_x(10)
        y = w.track_center_y(0)
        assert w.pos_to_keyframe(x, y) is not None

    def test_pos_to_keyframe_miss(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("X")
        w.tracks[0].add_keyframe(10)
        # Far away from the keyframe.
        assert w.pos_to_keyframe(0, 0) is None

    def test_keyframes_in_rect(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("X")
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
        w.add_track("X")
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
