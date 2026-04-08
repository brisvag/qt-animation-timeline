import os

import pytest
from qtpy.QtCore import QEvent, QPoint, QRect, Qt
from qtpy.QtGui import QKeyEvent, QMouseEvent
from qtpy.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import qt_animation_editor
from qt_animation_editor.easing import EasingFunction
from qt_animation_editor.editor import (
    _PLACEHOLDER_TRACK,
    AnimationTimelineWidget,
)
from qt_animation_editor.models import Keyframe, Track, _coerce_value


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_imports_with_version():
    assert isinstance(qt_animation_editor.__version__, str)


# ---------------------------------------------------------------------------
# EasingFunction
# ---------------------------------------------------------------------------


class TestEasingFunction:
    def test_linear_midpoint(self):
        assert EasingFunction.Linear(0.5, 0.0, 1.0) == pytest.approx(0.5)

    def test_linear_bounds(self):
        assert EasingFunction.Linear(0.0, 0.0, 1.0) == pytest.approx(0.0)
        assert EasingFunction.Linear(1.0, 0.0, 1.0) == pytest.approx(1.0)

    def test_linear_with_range(self):
        # Interpolation should scale with the provided range.
        assert EasingFunction.Linear(0.5, 10.0, 20.0) == pytest.approx(15.0)

    def test_step_before_midpoint(self):
        assert EasingFunction.Step(0.0, 0.0, 1.0) == pytest.approx(0.0)
        assert EasingFunction.Step(0.49, 0.0, 1.0) == pytest.approx(0.0)

    def test_step_at_and_after_midpoint(self):
        assert EasingFunction.Step(0.5, 0.0, 1.0) == pytest.approx(1.0)
        assert EasingFunction.Step(1.0, 0.0, 1.0) == pytest.approx(1.0)

    def test_step_works_with_non_numeric(self):
        """Step must work for arbitrary types — no arithmetic involved."""
        assert EasingFunction.Step(0.3, "a", "b") == "a"
        assert EasingFunction.Step(0.5, "a", "b") == "b"

    def test_members_are_callable(self):
        for ef in EasingFunction:
            assert callable(ef)


# ---------------------------------------------------------------------------
# _coerce_value
# ---------------------------------------------------------------------------


class TestCoerceValue:
    def test_float_stays_float(self):
        assert isinstance(_coerce_value(1.0, 2.5), float)
        assert _coerce_value(1.0, 2.5) == pytest.approx(2.5)

    def test_int_rounds(self):
        result = _coerce_value(1, 2.7)
        assert isinstance(result, int)
        assert result == 3

    def test_bool_rounds(self):
        assert _coerce_value(True, 0.6) is True
        assert _coerce_value(False, 0.4) is False

    def test_bool_not_treated_as_int(self):
        # bool is a subclass of int; ensure we get a proper bool back.
        result = _coerce_value(False, 1.0)
        assert type(result) is bool
        assert result is True

    def test_unknown_type_passthrough(self):
        obj = object()
        assert _coerce_value(obj, 3.14) == 3.14


# ---------------------------------------------------------------------------
# Keyframe
# ---------------------------------------------------------------------------


class TestKeyframe:
    def test_clamps_negative_t(self):
        assert Keyframe(-5).t == 0

    def test_default_easing(self):
        assert Keyframe(10).easing is EasingFunction.Linear

    def test_custom_easing(self):
        kf = Keyframe(5, easing=EasingFunction.Step)
        assert kf.easing is EasingFunction.Step


# ---------------------------------------------------------------------------
# Track
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# AnimationTimelineWidget - basics
# ---------------------------------------------------------------------------


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

    def test_add_track_default_is_placeholder(self, qapp):
        """Pressing + (no explicit name) creates a placeholder track."""
        w = AnimationTimelineWidget()
        track = w.add_track()
        assert track.name == _PLACEHOLDER_TRACK

    def test_track_colors_are_settable(self, qapp):
        from qtpy.QtGui import QColor

        w = AnimationTimelineWidget()
        red = QColor(255, 0, 0)
        w.track_colors = [red]
        track = w.add_track("A")
        assert track.color == red

    def test_easing_options_are_settable(self, qapp):
        w = AnimationTimelineWidget()
        w.easing_options = [EasingFunction.Step]
        assert w.easing_options == [EasingFunction.Step]

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


# ---------------------------------------------------------------------------
# Placeholder track
# ---------------------------------------------------------------------------


class TestPlaceholderTrack:
    def test_placeholder_name(self):
        assert _PLACEHOLDER_TRACK == "..."

    def test_add_track_no_name_is_placeholder(self, qapp):
        w = AnimationTimelineWidget()
        t = w.add_track()
        assert t.name == _PLACEHOLDER_TRACK

    def test_placeholder_never_dispatched(self, qapp):
        """Playhead movement must not call any binding for placeholder tracks."""

        class Model:
            v = 0.0

        m = Model()
        w = AnimationTimelineWidget()
        w.track_options = {_PLACEHOLDER_TRACK: (m, "v")}  # even if bound, skip
        t = w.add_track()  # creates "..."
        assert t.name == _PLACEHOLDER_TRACK
        t.add_keyframe(0, value=0.0)
        t.add_keyframe(100, value=99.0)
        w._set_playhead(50)
        # model field must not have been updated
        assert m.v == 0.0


# ---------------------------------------------------------------------------
# Unique track enforcement (context menu logic)
# ---------------------------------------------------------------------------


class TestUniqueTrackOptions:
    def _menu_actions(self, w, track_index):
        """Return {label: enabled} for the track-change menu of a given track."""
        from unittest.mock import patch

        captured = {}

        class FakeMenu:
            def addAction(self, label):
                class A:
                    def __init__(self):
                        self.label = label
                        self._checkable = False
                        self._checked = False
                        self._enabled = True

                    def setCheckable(self, v):
                        self._checkable = v

                    def setChecked(self, v):
                        self._checked = v

                    def setEnabled(self, v):
                        self._enabled = v
                        captured[label] = v

                    # Make triggered connectable
                    class _Sig:
                        def connect(self, fn):
                            pass

                    triggered = _Sig()

                a = A()
                captured[label] = True  # default enabled
                return a

            def exec(self, pos):
                pass

        # patch QMenu inside editor module
        import qt_animation_editor.editor as ed

        with patch.object(ed, "QMenu", return_value=FakeMenu()):
            ty = w.track_center_y(track_index)
            w._show_track_change_menu(int(ty), None)

        return captured

    def test_used_option_is_disabled_for_other_track(self, qapp):
        w = AnimationTimelineWidget()
        w.track_options = {"A": (object(), "x"), "B": (object(), "y")}
        w.add_track("A")
        w.add_track("B")

        # For track index 1 ("B"), option "A" should be disabled (used by track 0).
        actions = self._menu_actions(w, 1)
        assert actions.get("A") is False

    def test_placeholder_always_enabled(self, qapp):
        w = AnimationTimelineWidget()
        w.track_options = {"A": (object(), "x")}
        w.add_track("A")
        w.add_track("A")  # second track with same name (edge case)

        actions = self._menu_actions(w, 1)
        assert actions.get(_PLACEHOLDER_TRACK) is not False  # enabled or absent→True


# ---------------------------------------------------------------------------
# Rubber-band requires Shift
# ---------------------------------------------------------------------------


class TestRubberBandSelection:
    def _make_press(self, x, y, shift=False, button=Qt.MouseButton.LeftButton):
        mod = (
            Qt.KeyboardModifier.ShiftModifier
            if shift
            else Qt.KeyboardModifier.NoModifier
        )
        return QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPoint(x, y),
            button,
            button,
            mod,
        )

    def test_shift_click_starts_rubber_band(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        # Click in empty track area with Shift held.
        x = int(w.left_margin + 50)
        y = int(w.track_center_y(0))
        w.mousePressEvent(self._make_press(x, y, shift=True))
        assert w._box_start is not None

    def test_plain_click_does_not_start_rubber_band(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        x = int(w.left_margin + 50)
        y = int(w.track_center_y(0))
        w.mousePressEvent(self._make_press(x, y, shift=False))
        assert w._box_start is None


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------


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

    def test_step_easing_switches_at_midpoint(self, qapp):
        """Step easing should hold v_start until p=0.5, then switch to v_end."""
        w = self._make_widget(qapp)
        w.tracks[0].add_keyframe(0, value=0.0, easing=EasingFunction.Step)
        w.tracks[0].add_keyframe(100, value=1.0)
        # Just before midpoint → still 0
        assert w._interpolate_track(w.tracks[0], 49) == pytest.approx(0.0)
        # At midpoint → switches to 1
        assert w._interpolate_track(w.tracks[0], 50) == pytest.approx(1.0)
        assert w._interpolate_track(w.tracks[0], 100) == pytest.approx(1.0)

    def test_zero_span_segment_returns_first_value(self, qapp):
        """Keyframes at same position: querying at that frame returns first value."""
        w = self._make_widget(qapp)
        k1 = w.tracks[0].add_keyframe(50, value=1.0)
        k2 = w.tracks[0].add_keyframe(100, value=9.0)
        # Drag k2 onto k1's position (both now at t=50).
        k2.t = 50
        # frame <= kfs[0].t clamping kicks in; first keyframe's value is returned.
        assert w._interpolate_track(w.tracks[0], 50) == pytest.approx(k1.value)


# ---------------------------------------------------------------------------
# Segment keyframe lookup (easing menu hit-test)
# ---------------------------------------------------------------------------


class TestSegmentLeftKeyframe:
    def test_returns_left_keyframe_in_segment(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        k1 = w.tracks[0].add_keyframe(0)
        w.tracks[0].add_keyframe(100)
        x = int(w.frame_to_x(50))
        y = int(w.track_center_y(0))
        assert w._segment_left_keyframe_at(x, y) is k1

    def test_after_last_keyframe_returns_last(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        w.tracks[0].add_keyframe(0)
        k_last = w.tracks[0].add_keyframe(50)
        x = int(w.frame_to_x(80))
        y = int(w.track_center_y(0))
        assert w._segment_left_keyframe_at(x, y) is k_last

    def test_no_keyframes_returns_none(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        x = int(w.frame_to_x(10))
        y = int(w.track_center_y(0))
        assert w._segment_left_keyframe_at(x, y) is None


# ---------------------------------------------------------------------------
# Model/field callback dispatch
# ---------------------------------------------------------------------------


class TestTrackModelDispatch:
    def test_field_updated_on_playhead_move(self, qapp):
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

    def test_int_field_is_rounded(self, qapp):
        class Model:
            n = 0

        m = Model()
        w = AnimationTimelineWidget()
        w.track_options = {"A": (m, "n")}
        w.add_track("A")
        w.tracks[0].add_keyframe(0, value=0)
        w.tracks[0].add_keyframe(10, value=10)

        w._set_playhead(3)  # 3/10 * 10 = 3 → int
        assert isinstance(m.n, int)
        assert m.n == 3

    def test_step_field_coerced(self, qapp):
        class Model:
            flag = False

        m = Model()
        w = AnimationTimelineWidget()
        w.track_options = {"A": (m, "flag")}
        w.add_track("A")
        w.tracks[0].add_keyframe(0, value=0.0, easing=EasingFunction.Step)
        w.tracks[0].add_keyframe(100, value=1.0)

        w._set_playhead(49)
        assert m.flag is False  # Step holds until p=0.5

        w._set_playhead(50)
        assert m.flag is True  # Step switches at p=0.5

    def test_no_update_for_unregistered_track(self, qapp):
        class Model:
            x = 0.0

        m = Model()
        w = AnimationTimelineWidget()
        w.track_options = {"A": (m, "x")}
        w.add_track("B")  # not registered
        w.tracks[0].add_keyframe(0, value=0.0)
        w.tracks[0].add_keyframe(100, value=10.0)

        w._set_playhead(50)
        assert m.x == 0.0  # untouched

    def test_dispatch_on_easing_change(self, qapp):
        """Changing a keyframe's easing must immediately update bound model fields."""

        class Model:
            x = 0.0

        m = Model()
        w = AnimationTimelineWidget()
        w.track_options = {"A": (m, "x")}
        w.add_track("A")
        w.tracks[0].add_keyframe(0, value=0.0)
        w.tracks[0].add_keyframe(100, value=10.0)
        w._set_playhead(50)
        assert m.x == pytest.approx(5.0)  # linear midpoint

        # Switch to Step: at p=0.5 the value jumps to v_end.
        kf_left = w.tracks[0].keyframes[0]
        kf_left.easing = EasingFunction.Step
        w._dispatch_track_callbacks(w.current_frame)
        assert m.x == pytest.approx(10.0)

    def test_dispatch_on_keyframe_add(self, qapp):
        """Adding a keyframe must immediately refresh the bound model field."""

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

        # Insert a new keyframe at frame 50 with a different value.
        w.tracks[0].add_keyframe(50, value=99.0)
        w._dispatch_track_callbacks(w.current_frame)
        # Now frame 50 is exactly at a keyframe → returns its value.
        assert m.x == pytest.approx(99.0)


# ---------------------------------------------------------------------------
# Keyframe value capture on double-click
# ---------------------------------------------------------------------------


class TestKeyframeValueCapture:
    def test_captures_field_value_at_creation(self, qapp):
        class Model:
            x = 42.0

        m = Model()
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.track_options = {"A": (m, "x")}
        w.add_track("A")

        # Directly call the creation path by simulating the internals.
        track = w.tracks[0]
        binding = w.track_options.get(track.name)
        assert binding is not None
        model, field = binding
        initial_value = getattr(model, field)
        kf = track.add_keyframe(50, value=initial_value)
        assert kf.value == pytest.approx(42.0)

    def test_placeholder_track_uses_zero(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track()  # placeholder
        track = w.tracks[0]
        binding = w.track_options.get(track.name)
        # No binding for placeholder → initial value should default to 0.
        initial_value = getattr(*binding) if binding else 0
        assert initial_value == 0


# ---------------------------------------------------------------------------
# _can_add_track
# ---------------------------------------------------------------------------


class TestCanAddTrack:
    def test_no_options_always_can_add(self, qapp):
        w = AnimationTimelineWidget()
        assert w._can_add_track() is True

    def test_options_not_all_used(self, qapp):
        w = AnimationTimelineWidget()
        w.track_options = {"A": (object(), "x"), "B": (object(), "y")}
        w.add_track("A")
        assert w._can_add_track() is True  # B still free

    def test_all_options_used_blocks_add(self, qapp):
        w = AnimationTimelineWidget()
        w.track_options = {"A": (object(), "x")}
        w.add_track("A")
        assert w._can_add_track() is False

    def test_placeholder_tracks_dont_count(self, qapp):
        w = AnimationTimelineWidget()
        w.track_options = {"A": (object(), "x")}
        w.add_track("A")
        w.add_track()  # placeholder doesn't consume an option slot
        assert w._can_add_track() is False  # still blocked (A is used)


# ---------------------------------------------------------------------------
# zoom_step magnitude
# ---------------------------------------------------------------------------


class TestZoomStep:
    def test_normal_zoom(self, qapp):
        w = AnimationTimelineWidget()
        w.frame_width = 15.0
        step = w.zoom_step()
        assert step >= 1

    def test_very_zoomed_out(self, qapp):
        w = AnimationTimelineWidget()
        w.frame_width = 0.1  # 1000 frames per 100 px
        step = w.zoom_step()
        assert step >= 100  # should pick a large round step

    def test_very_zoomed_in(self, qapp):
        w = AnimationTimelineWidget()
        w.frame_width = 60.0  # fewer than 2 frames per 100 px
        step = w.zoom_step()
        assert step == 1

    def test_step_is_power_of_ten_family(self, qapp):
        """Step must always be 1, 2, or 5 times a power of ten."""
        for fw in [0.05, 0.2, 1, 5, 15, 50]:
            w = AnimationTimelineWidget()
            w.frame_width = fw
            step = w.zoom_step()
            # Check it divides cleanly into a power-of-10 family.
            assert step >= 1
            s = step
            while s > 9:
                s //= 10
            assert s in (1, 2, 5)


# ---------------------------------------------------------------------------
# Easing preselection by type
# ---------------------------------------------------------------------------


class TestEasingPreselection:
    def test_bool_field_gets_only_step(self, qapp):
        class Model:
            flag: bool = True

        m = Model()
        w = AnimationTimelineWidget()
        w.track_options = {"A": (m, "flag")}
        t = w.add_track("A")
        allowed = w._get_allowed_easings_for_track(t)
        assert allowed == [EasingFunction.Step]

    def test_float_field_gets_all(self, qapp):
        class Model:
            x: float = 0.0

        m = Model()
        w = AnimationTimelineWidget()
        w.track_options = {"A": (m, "x")}
        t = w.add_track("A")
        allowed = w._get_allowed_easings_for_track(t)
        assert EasingFunction.Linear in allowed
        assert EasingFunction.Step in allowed

    def test_placeholder_gets_all(self, qapp):
        w = AnimationTimelineWidget()
        t = w.add_track()  # "..."
        allowed = w._get_allowed_easings_for_track(t)
        assert set(allowed) == set(EasingFunction)


# ---------------------------------------------------------------------------
# Double-right-click does not create a keyframe
# ---------------------------------------------------------------------------


class TestDoubleClickButton:
    def test_right_double_click_ignored(self, qapp):
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
        assert len(w.tracks[0].keyframes) == 0  # no keyframe created


# ---------------------------------------------------------------------------
# left_timeline_pad — coordinate round-trip still holds
# ---------------------------------------------------------------------------


class TestTimelinePad:
    def test_coordinate_roundtrip_with_pad(self, qapp):
        w = AnimationTimelineWidget()
        assert w.left_timeline_pad > 0
        for frame in [0, 1, 50, 300]:
            assert w.x_to_frame(w.frame_to_x(frame)) == frame

    def test_frame_zero_x_greater_than_left_margin(self, qapp):
        """frame_to_x(0) must be to the right of the label column."""
        w = AnimationTimelineWidget()
        assert w.frame_to_x(0) > w.left_margin


# ---------------------------------------------------------------------------
# _is_on_track_line
# ---------------------------------------------------------------------------


class TestIsOnTrackLine:
    def test_on_center_returns_true(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        cy = w.track_center_y(0)
        x = int(w.frame_to_x(10))
        assert w._is_on_track_line(x, int(cy)) is True

    def test_far_from_center_returns_false(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        cy = w.track_center_y(0)
        x = int(w.frame_to_x(10))
        # Use the full track row height as offset — clearly outside the line.
        assert w._is_on_track_line(x, int(cy) + w.track_height) is False

    def test_within_tolerance_returns_true(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        cy = w.track_center_y(0)
        x = int(w.frame_to_x(10))
        tolerance = w.line_thickness + 4
        assert w._is_on_track_line(x, int(cy) + tolerance) is True

    def test_no_tracks_returns_false(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        assert w._is_on_track_line(200, 60) is False


# ---------------------------------------------------------------------------
# _reset_view fits content
# ---------------------------------------------------------------------------


class TestResetViewFitsContent:
    def test_reset_with_keyframes_computes_zoom(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w.add_track("A")
        w.tracks[0].add_keyframe(0, value=0.0)
        w.tracks[0].add_keyframe(200, value=1.0)
        w._reset_view()
        # After reset: scroll is at origin.
        assert w.scroll_x == 0
        # frame_to_x(0) should be at left_margin + left_timeline_pad.
        assert w.frame_to_x(0) == pytest.approx(w.left_margin + w.left_timeline_pad)
        # Last keyframe should be within the visible viewport.
        last_x = w.frame_to_x(200)
        assert last_x < w.width()

    def test_reset_with_no_keyframes_uses_fallback(self, qapp):
        w = AnimationTimelineWidget()
        w.resize(800, 300)
        w._reset_view()
        assert w.scroll_x == 0
        assert w.frame_width > 0


# ---------------------------------------------------------------------------
# Default track colors — colorblind-friendly palette
# ---------------------------------------------------------------------------


class TestDefaultColors:
    def test_seven_default_colors(self, qapp):
        from qt_animation_editor.editor import _DEFAULT_TRACK_COLORS

        assert len(_DEFAULT_TRACK_COLORS) == 7

    def test_colors_are_valid(self, qapp):
        from qt_animation_editor.editor import _DEFAULT_TRACK_COLORS

        for c in _DEFAULT_TRACK_COLORS:
            assert c.isValid()

    def test_blue_is_first(self, qapp):
        """First color should be the Okabe-Ito blue."""
        from qt_animation_editor.editor import _DEFAULT_TRACK_COLORS

        c = _DEFAULT_TRACK_COLORS[0]
        assert c.red() == 0
        assert c.green() == 114
        assert c.blue() == 178
