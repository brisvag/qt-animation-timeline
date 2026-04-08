"""Animation timeline editor widget."""

from __future__ import annotations

import itertools
import math
from typing import Any

from qtpy.QtCore import QPoint, QRect, Qt, QTimer, Signal
from qtpy.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from qtpy.QtWidgets import QMenu, QScrollBar, QToolTip, QWidget

from qt_animation_editor.easing import EasingFunction
from qt_animation_editor.models import Keyframe, Track, _coerce_value

# Special placeholder track name — always available and never unique-enforced.
_PLACEHOLDER_TRACK = "..."

# Default frame width in pixels (used by reset-view).
_DEFAULT_FRAME_WIDTH: float = 15.0

# Multiplicative zoom factor per scroll step (Ctrl+wheel).
_ZOOM_FACTOR: float = 1.15

_DEFAULT_TRACK_COLORS = [
    QColor(255, 100, 100),
    QColor(100, 200, 100),
    QColor(100, 150, 255),
    QColor(255, 200, 80),
    QColor(200, 100, 255),
    QColor(80, 220, 200),
]


class AnimationTimelineWidget(QWidget):
    """Interactive animation timeline widget."""

    # Emitted when the playhead moves to a new frame.
    playhead_moved = Signal(int)
    # Emitted when a track is added or removed.
    track_added = Signal(object)
    track_removed = Signal(object)
    # Emitted when a track's option/name is changed via the context menu.
    track_changed = Signal(object)
    # Emitted when a keyframe is created by the user.
    keyframe_added = Signal(object, object)
    # Emitted after one or more keyframes are deleted.
    keyframes_removed = Signal(list)
    # Emitted at the end of a keyframe drag operation.
    keyframes_moved = Signal(list)
    # Emitted when the easing of one or more keyframes changes.
    easing_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.bg_color = QColor(30, 30, 30)
        self.track_bg_color = QColor(50, 50, 50)
        self.time_line_color = QColor(180, 180, 180, 120)
        self.time_label_color = QColor(200, 200, 200)
        self.current_frame_color = QColor(255, 0, 0)
        self.add_button_color = QColor(80, 150, 80)
        self.remove_button_color = QColor(180, 80, 80)
        self.rubber_band_fill = QColor(100, 150, 255, 50)
        self.rubber_band_border = QColor(100, 150, 255, 200)
        self.control_btn_color = QColor(60, 60, 80)
        self.control_btn_text_color = QColor(200, 200, 220)
        self.play_btn_color = QColor(60, 80, 60)
        self.play_btn_text_color = QColor(180, 220, 180)

        self.keyframe_size: int = 10
        self.line_thickness: int = 2
        self.frame_width: float = _DEFAULT_FRAME_WIDTH
        self.track_height: int = 40
        self.left_margin: int = 120
        self.top_margin: int = 40
        # Allow near-infinite zoom out; zoom_step() adapts via magnitude.
        self.min_frame_width: float = 0.05
        self.max_frame_width: float = 80.0

        # Colours cycled through when adding new tracks.  Replace to customise.
        self.track_colors: list[QColor] = list(_DEFAULT_TRACK_COLORS)

        # Easing options shown in the right-click menu.  Replace to restrict choices.
        self.easing_options: list[EasingFunction] = list(EasingFunction)

        self.tracks: list[Track] = []

        # Maps real track names to (model_instance, field_name) bindings.
        # When the playhead moves the field is set to the interpolated value.
        # When a keyframe is created the current field value is used as its value.
        # The "..." placeholder track is always available and needs no binding.
        # Example: ``{"x": (my_object, "x"), "y": (my_object, "y")}``
        self.track_options: dict[str, tuple[Any, str]] = {}

        self.current_frame: int = 0

        self.scroll_x: int = 0
        self.scroll_y: int = 0

        self.selected_keyframes: list[Keyframe] = []
        # Anchor keyframe used to compute deltas during a multi-keyframe drag.
        self._drag_pivot: Keyframe | None = None
        self._drag_offset: int = 0
        self._dragging_keyframes: bool = False

        self._scrubbing: bool = False

        # Rubber-band box-selection state (activated by Shift+left-click).
        self._box_start: QPoint | None = None
        self._box_rect: QRect | None = None

        # Playback state.
        self._playing: bool = False
        self._play_fps: int = 30
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._advance_playhead)

        self.h_scroll = QScrollBar(Qt.Orientation.Horizontal, self)
        self.v_scroll = QScrollBar(Qt.Orientation.Vertical, self)
        self.h_scroll.valueChanged.connect(self._on_hscroll)
        self.v_scroll.valueChanged.connect(self._on_vscroll)

        self.label_font = QFont("Arial", 10)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Enable hover events for keyframe value tooltips.
        self.setMouseTracking(True)

    # ------------------------------------------------------------------ #
    # Coordinate helpers                                                   #
    # ------------------------------------------------------------------ #

    def frame_to_x(self, frame: int | float) -> float:
        """Convert a frame number to a pixel x coordinate."""
        return self.left_margin + frame * self.frame_width - self.scroll_x

    def x_to_frame(self, x: float) -> int:
        """Convert a pixel x coordinate to the nearest frame number."""
        return round((x - self.left_margin + self.scroll_x) / self.frame_width)

    def y_to_track_index(self, y: float) -> int:
        """Convert a pixel y coordinate to a track index (may be out of range)."""
        return int((y - self.top_margin + self.scroll_y) / self.track_height)

    def track_center_y(self, track_index: int) -> float:
        """Return the pixel y coordinate of the vertical centre of a track row."""
        return (
            self.top_margin
            + track_index * self.track_height
            - self.scroll_y
            + self.track_height / 2
        )

    # ------------------------------------------------------------------ #
    # Scrollbars / resize                                                  #
    # ------------------------------------------------------------------ #

    def resizeEvent(self, event) -> None:
        vsw = 20 if self.v_scroll.isVisible() else 0
        self.h_scroll.setGeometry(0, self.height() - 20, self.width() - vsw, 20)
        self.v_scroll.setGeometry(self.width() - 20, 0, 20, self.height() - 20)
        self.update_scrollbars()

    def update_scrollbars(self) -> None:
        """Recalculate scrollbar ranges based on content size."""
        max_frame = max((kf.t for t in self.tracks for kf in t.keyframes), default=0)
        content_width = (max_frame + 20) * self.frame_width
        page_w = self.width() - self.left_margin
        self.h_scroll.setMaximum(max(0, int(content_width - page_w)))
        self.h_scroll.setPageStep(int(page_w))

        total_tracks_height = len(self.tracks) * self.track_height
        page_h = self.height() - self.top_margin
        need_vscroll = total_tracks_height > page_h
        self.v_scroll.setVisible(need_vscroll)
        if need_vscroll:
            self.v_scroll.setMaximum(total_tracks_height - page_h)
            self.v_scroll.setPageStep(page_h)
        else:
            self.scroll_y = 0
            self.v_scroll.setMaximum(0)

    def _on_hscroll(self, v: int) -> None:
        self.scroll_x = v
        self.update()

    def _on_vscroll(self, v: int) -> None:
        self.scroll_y = v
        self.update()

    # ------------------------------------------------------------------ #
    # Zoom                                                                 #
    # ------------------------------------------------------------------ #

    def zoom_step(self) -> int:
        """Return the frame-label interval appropriate for the current zoom level.

        Uses order-of-magnitude arithmetic so the step adapts gracefully at
        any zoom level, including very zoomed-out views where frame_width is a
        fraction of a pixel.
        """
        if self.frame_width <= 0:
            return 1000
        # How many frames fit in ~100 px at the current zoom?
        frames_per_100px = 100.0 / self.frame_width
        if frames_per_100px <= 1.0:
            return 1
        magnitude = 10 ** math.floor(math.log10(frames_per_100px))
        ratio = frames_per_100px / magnitude
        if ratio >= 5:
            step = 5 * magnitude
        elif ratio >= 2:
            step = 2 * magnitude
        else:
            step = magnitude
        return max(1, int(step))

    # ------------------------------------------------------------------ #
    # Painting                                                             #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.bg_color)
        painter.setFont(self.label_font)
        metrics = painter.fontMetrics()

        self._draw_track_backgrounds(painter)
        self._draw_grid(painter, metrics)

        # Clip track content to the right of the label column.
        painter.save()
        painter.setClipRect(
            self.left_margin,
            self.top_margin,
            self.width() - self.left_margin,
            self.height() - self.top_margin,
        )
        for i, track in enumerate(self.tracks):
            self.draw_track(painter, i, track)
        if self._box_rect is not None:
            self._draw_rubber_band(painter)
        painter.restore()

        self._draw_labels(painter, metrics)
        self._draw_add_button(painter)
        self._draw_control_buttons(painter, metrics)

        # Playhead — only when to the right of the label column.
        x = self.frame_to_x(self.current_frame)
        if x >= self.left_margin:
            xi = int(x)
            painter.setPen(QPen(self.current_frame_color, 2))
            painter.drawLine(xi, 0, xi, self.height())
            # Downward-pointing triangle at the very top of the playhead.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.current_frame_color)
            s = 7
            pts = [QPoint(xi - s, 0), QPoint(xi + s, 0), QPoint(xi, s + 5)]
            painter.drawPolygon(pts)

    def _draw_track_backgrounds(self, painter: QPainter) -> None:
        for i in range(len(self.tracks)):
            y = self.top_margin + i * self.track_height - self.scroll_y
            painter.fillRect(
                self.left_margin,
                y,
                self.width() - self.left_margin,
                self.track_height,
                self.track_bg_color,
            )

    def _draw_grid(self, painter: QPainter, metrics: QFontMetrics) -> None:
        """Draw frame-number tick marks and vertical grid lines.

        Only the visible portion of the timeline is iterated, so performance
        is O(viewport_width / step_pixels) regardless of zoom level.
        """
        step = self.zoom_step()
        if self.frame_width <= 0:
            return
        first_frame = max(0, int(self.scroll_x / self.frame_width))
        last_frame = int((self.scroll_x + self.width()) / self.frame_width) + step
        start_frame = (first_frame // step) * step
        for frame in range(start_frame, last_frame + step, step):
            x = self.frame_to_x(frame)
            if x > self.width():
                break
            if x < self.left_margin:
                continue
            painter.setPen(self.time_line_color)
            painter.drawLine(int(x), self.top_margin, int(x), self.height())
            painter.setPen(self.time_label_color)
            label = str(frame)
            painter.drawText(
                int(x) - metrics.horizontalAdvance(label) // 2,
                self.top_margin - 10,
                label,
            )

    def _draw_labels(self, painter: QPainter, metrics: QFontMetrics) -> None:
        btn_size = 14
        for i, track in enumerate(self.tracks):
            y = self.top_margin + i * self.track_height - self.scroll_y
            if y < -self.track_height or y > self.height():
                continue

            painter.setPen(track.color)
            painter.drawText(
                40,
                y + self.track_height // 2 + metrics.ascent() // 2,
                track.name,
            )

            bx = 8
            by = y + (self.track_height - btn_size) // 2
            painter.setBrush(self.remove_button_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(bx, by, btn_size, btn_size)
            painter.setPen(Qt.GlobalColor.black)
            lx = bx + (btn_size - metrics.horizontalAdvance("-")) // 2
            ly = by + (btn_size + metrics.ascent() - metrics.descent()) // 2
            painter.drawText(lx, ly, "-")

    def _draw_add_button(self, painter: QPainter) -> None:
        """Draw the add-track (+) button below all track labels.

        The button is greyed out when no further track options are available.
        """
        ay = self.top_margin + len(self.tracks) * self.track_height - self.scroll_y
        can_add = self._can_add_track()
        color = self.add_button_color if can_add else QColor(60, 60, 60)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, ay, self.left_margin, self.track_height)
        cross_color = Qt.GlobalColor.black if can_add else QColor(100, 100, 100)
        painter.setPen(cross_color)
        cx = self.left_margin // 2
        cy = ay + self.track_height // 2
        painter.drawLine(cx - 8, cy, cx + 8, cy)
        painter.drawLine(cx, cy - 8, cx, cy + 8)

    def _draw_control_buttons(self, painter: QPainter, metrics: QFontMetrics) -> None:
        """Draw the reset-view and play/pause buttons in the top-left corner."""
        btn_w = self.left_margin // 2
        h = self.top_margin

        # Reset / home button (left half).
        painter.fillRect(0, 0, btn_w, h, self.control_btn_color)
        painter.setPen(self.control_btn_text_color)
        painter.drawText(
            QRect(0, 0, btn_w, h),
            Qt.AlignmentFlag.AlignCenter,
            "\u2302",  # ⌂ house symbol
        )

        # Play / pause button (right half).
        painter.fillRect(btn_w, 0, btn_w, h, self.play_btn_color)
        painter.setPen(self.play_btn_text_color)
        painter.drawText(
            QRect(btn_w, 0, btn_w, h),
            Qt.AlignmentFlag.AlignCenter,
            "\u23f8" if self._playing else "\u25b6",  # ⏸ / ▶
        )

    def _draw_rubber_band(self, painter: QPainter) -> None:
        assert self._box_rect is not None
        painter.setBrush(self.rubber_band_fill)
        painter.setPen(QPen(self.rubber_band_border, 1))
        painter.drawRect(self._box_rect)

    def draw_track(self, painter: QPainter, index: int, track: Track) -> None:
        """Draw the connecting line and all keyframes for *track*."""
        cy = int(self.track_center_y(index))

        if len(track.keyframes) >= 2:
            painter.setPen(QPen(track.color, self.line_thickness))
            for k1, k2 in itertools.pairwise(track.keyframes):
                painter.drawLine(
                    int(self.frame_to_x(k1.t)),
                    cy,
                    int(self.frame_to_x(k2.t)),
                    cy,
                )

        for kf in track.keyframes:
            self.draw_keyframe(painter, index, track, kf)

    def draw_keyframe(
        self, painter: QPainter, track_index: int, track: Track, kf: Keyframe
    ) -> None:
        """Draw a single keyframe as a filled diamond."""
        x = self.frame_to_x(kf.t)
        y = self.track_center_y(track_index)
        color = (
            track.color if kf not in self.selected_keyframes else QColor(255, 255, 0)
        )
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        s = self.keyframe_size / 2
        pts = [
            QPoint(int(x), int(y - s)),
            QPoint(int(x + s), int(y)),
            QPoint(int(x), int(y + s)),
            QPoint(int(x - s), int(y)),
        ]
        painter.drawPolygon(pts)

    # ------------------------------------------------------------------ #
    # Mouse events                                                         #
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        x, y = event.x(), event.y()

        # Top strip (ruler + control buttons).
        if y < self.top_margin:
            if x < self.left_margin:
                self._handle_control_click(x, y)
            else:
                self._scrubbing = True
                self._set_playhead(max(0, self.x_to_frame(x)))
            return

        # Label column: remove button and add button.
        if x < self.left_margin:
            self._handle_label_click(x, y)
            return

        # Timeline content — keyframes take priority.
        kf = self.pos_to_keyframe(x, y)
        if kf is not None:
            self._start_keyframe_drag(event, kf, x)
            return

        # Empty content area: Shift+click starts rubber-band selection.
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.selected_keyframes.clear()
            self._box_start = QPoint(x, y)
            self._box_rect = None
        else:
            self.selected_keyframes.clear()
        self.update()

    def _handle_control_click(self, x: int, _y: int) -> None:
        """Handle a click in the top-left control area (reset / play)."""
        btn_w = self.left_margin // 2
        if x < btn_w:
            self._reset_view()
        else:
            self._toggle_playback()

    def _handle_label_click(self, x: int, y: int) -> None:
        """Handle a left-click inside the label column (remove/add buttons)."""
        for i in range(len(self.tracks)):
            ty = self.top_margin + i * self.track_height - self.scroll_y
            if 8 <= x <= 22 and ty + 13 <= y <= ty + 27:
                removed = self.tracks.pop(i)
                self.update_scrollbars()
                self.update()
                self.track_removed.emit(removed)
                return

        ay = self.top_margin + len(self.tracks) * self.track_height - self.scroll_y
        if ay <= y <= ay + self.track_height and self._can_add_track():
            self.add_track()

    def _start_keyframe_drag(self, event: QMouseEvent, kf: Keyframe, x: int) -> None:
        """Set up drag state for the clicked keyframe."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if kf in self.selected_keyframes:
                self.selected_keyframes.remove(kf)
            else:
                self.selected_keyframes.append(kf)
        elif kf not in self.selected_keyframes:
            self.selected_keyframes = [kf]

        self._drag_pivot = kf
        self._drag_offset = self.x_to_frame(x) - kf.t
        self._dragging_keyframes = False
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x, y = event.x(), event.y()

        if self._scrubbing:
            self._set_playhead(max(0, self.x_to_frame(x)))
            return

        if self._drag_pivot is not None:
            self._move_selected_keyframes(x)
            self._dragging_keyframes = True
            return

        if self._box_start is not None:
            self._update_box_select(QPoint(x, y))
            return

        # Hover tooltip: show keyframe value when mousing over a diamond.
        if x >= self.left_margin and y >= self.top_margin:
            kf = self.pos_to_keyframe(x, y)
            if kf is not None:
                QToolTip.showText(
                    event.globalPos(),
                    f"t={kf.t}  value={kf.value!r}",
                    self,
                )
            else:
                QToolTip.hideText()

    def _move_selected_keyframes(self, x: int) -> None:
        assert self._drag_pivot is not None
        target = max(0, self.x_to_frame(x) - self._drag_offset)
        delta = target - self._drag_pivot.t
        if delta == 0:
            return
        for kf in self.selected_keyframes:
            kf.t = max(0, kf.t + delta)
        for track in self.tracks:
            track.keyframes.sort(key=lambda k: k.t)
        self.update_scrollbars()
        self.update()

    def _update_box_select(self, current: QPoint) -> None:
        assert self._box_start is not None
        self._box_rect = QRect(self._box_start, current).normalized()
        self.selected_keyframes = self._keyframes_in_rect(self._box_rect)
        self.update()

    def _keyframes_in_rect(self, rect: QRect) -> list[Keyframe]:
        """Return all keyframes whose centre point lies within *rect*."""
        result = []
        for i, track in enumerate(self.tracks):
            cy = int(self.track_center_y(i))
            for kf in track.keyframes:
                cx = int(self.frame_to_x(kf.t))
                if rect.contains(cx, cy):
                    result.append(kf)
        return result

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging_keyframes and self.selected_keyframes:
            self.keyframes_moved.emit(list(self.selected_keyframes))
            # Playhead might be inside a moved segment — update the model.
            self._dispatch_track_callbacks(self.current_frame)

        self._scrubbing = False
        self._drag_pivot = None
        self._dragging_keyframes = False
        self._box_start = None
        self._box_rect = None
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # Only left double-click creates keyframes; ignore right-click.
        if event.button() != Qt.MouseButton.LeftButton:
            return

        x, y = event.x(), event.y()

        # Ignore double-clicks outside the timeline content area.
        if x < self.left_margin or y < self.top_margin:
            return

        track_index = self.y_to_track_index(y)
        if not (0 <= track_index < len(self.tracks)):
            return

        frame = max(0, self.x_to_frame(x))
        track = self.tracks[track_index]

        # Capture the current field value from the model binding, if available.
        binding = self.track_options.get(track.name)
        if binding is not None:
            model, field = binding
            initial_value = getattr(model, field)
        else:
            initial_value = 0

        try:
            kf = track.add_keyframe(frame, value=initial_value)
        except KeyError:
            return

        self.update_scrollbars()
        self.update()
        self.keyframe_added.emit(track, kf)
        # The new keyframe may affect the current playhead position.
        self._dispatch_track_callbacks(self.current_frame)

    def pos_to_keyframe(self, x: float, y: float) -> Keyframe | None:
        """Return the keyframe at screen position *(x, y)*, or ``None``."""
        track_index = self.y_to_track_index(y)
        if not (0 <= track_index < len(self.tracks)):
            return None
        track = self.tracks[track_index]
        cy = self.track_center_y(track_index)
        for kf in track.keyframes:
            kx = self.frame_to_x(kf.t)
            if abs(kx - x) <= self.keyframe_size and abs(cy - y) <= self.keyframe_size:
                return kf
        return None

    # ------------------------------------------------------------------ #
    # Context menus                                                        #
    # ------------------------------------------------------------------ #

    def contextMenuEvent(self, event) -> None:
        x, y = event.pos().x(), event.pos().y()
        # Ignore right-clicks in the ruler/control strip.
        if y < self.top_margin:
            return
        if x >= self.left_margin:
            self._show_easing_menu(x, y, event.globalPos())
        else:
            self._show_track_change_menu(y, event.globalPos())

    def _segment_left_keyframe_at(self, x: int, y: int) -> Keyframe | None:
        """Return the left keyframe of the segment under *(x, y)*, or ``None``.

        Searches from left to right; returns the keyframe that starts the
        segment (or the last keyframe when clicking after all keyframes).
        Returns ``None`` when the track has no keyframes.
        """
        track_index = self.y_to_track_index(y)
        if not (0 <= track_index < len(self.tracks)):
            return None
        track = self.tracks[track_index]
        kfs = track.keyframes
        if not kfs:
            return None
        frame = self.x_to_frame(x)
        for k1, k2 in itertools.pairwise(kfs):
            if k1.t <= frame <= k2.t:
                return k1
        if frame > kfs[-1].t:
            return kfs[-1]
        return None

    def _get_allowed_easings_for_track(self, track: Track) -> list[EasingFunction]:
        """Return the subset of ``easing_options`` appropriate for *track*'s type.

        For ``bool`` fields only ``Step`` is offered since linear interpolation
        of 0/1 produces non-boolean intermediates.  All other types get the
        full ``easing_options`` list.
        """
        binding = self.track_options.get(track.name)
        if binding is None or track.name == _PLACEHOLDER_TRACK:
            return self.easing_options
        model, field = binding
        try:
            value = getattr(model, field)
        except AttributeError:
            return self.easing_options
        # isinstance(True, bool) must come before isinstance(True, int).
        if isinstance(value, bool):
            return [ef for ef in self.easing_options if ef is EasingFunction.Step]
        return self.easing_options

    def _show_easing_menu(self, x: int, y: int, global_pos: object) -> None:
        """Show easing options for the segment under the cursor.

        The target keyframe is found by first checking for a direct hit on a
        keyframe diamond, then by segment lookup so that clicking anywhere on
        a track row between (or after) keyframes also works.
        """
        kf = self.pos_to_keyframe(x, y)
        if kf is None:
            kf = self._segment_left_keyframe_at(x, y)
        if kf is None:
            return

        # Determine allowed easings based on the field type of this track.
        track_index = self.y_to_track_index(y)
        track = (
            self.tracks[track_index]
            if 0 <= track_index < len(self.tracks)
            else None
        )
        allowed = (
            self._get_allowed_easings_for_track(track)
            if track is not None
            else self.easing_options
        )

        targets = self.selected_keyframes if kf in self.selected_keyframes else [kf]
        menu = QMenu(self)

        for ef in allowed:
            action = menu.addAction(ef.name)
            action.setCheckable(True)
            action.setChecked(all(k.easing is ef for k in targets))

            def _set(checked: bool, _ef: EasingFunction = ef) -> None:
                for k in targets:
                    k.easing = _ef
                self.update()
                self.easing_changed.emit(list(targets))
                # Playhead may be in an affected segment — update the model.
                self._dispatch_track_callbacks(self.current_frame)

            action.triggered.connect(_set)

        menu.exec(global_pos)

    def _show_track_change_menu(self, y: int, global_pos: object) -> None:
        """Show a context menu for changing a track to one of the configured options.

        The ``...`` placeholder is always available.  Named options that are
        already used by *other* tracks are shown but disabled to enforce
        uniqueness.
        """
        track_index = self.y_to_track_index(y)
        if not (0 <= track_index < len(self.tracks)):
            return

        track = self.tracks[track_index]
        used_by_others = {
            t.name
            for t in self.tracks
            if t is not track and t.name != _PLACEHOLDER_TRACK
        }

        menu = QMenu(self)
        for option in [_PLACEHOLDER_TRACK, *self.track_options]:
            action = menu.addAction(option)
            action.setCheckable(True)
            action.setChecked(track.name == option)
            if option != _PLACEHOLDER_TRACK and option in used_by_others:
                action.setEnabled(False)

            def _change(
                checked: bool, _t: Track = track, _n: str = option
            ) -> None:
                _t.name = _n
                self.update()
                self.track_changed.emit(_t)

            action.triggered.connect(_change)
        menu.exec(global_pos)

    # ------------------------------------------------------------------ #
    # Wheel / keyboard                                                     #
    # ------------------------------------------------------------------ #

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Multiplicative zoom keeps steps proportional at any zoom level.
            steps = event.angleDelta().y() / 120
            factor = _ZOOM_FACTOR**steps
            self.frame_width = max(
                self.min_frame_width,
                min(self.frame_width * factor, self.max_frame_width),
            )
            self.update_scrollbars()
            self.update()
            return

        self.scroll_x -= event.angleDelta().y()
        self.scroll_x = max(0, min(self.scroll_x, self.h_scroll.maximum()))
        self.h_scroll.setValue(self.scroll_x)
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete:
            removed = list(self.selected_keyframes)
            for track in self.tracks:
                track.keyframes = [
                    kf for kf in track.keyframes if kf not in self.selected_keyframes
                ]
            self.selected_keyframes.clear()
            self.update_scrollbars()
            self.update()
            if removed:
                self.keyframes_removed.emit(removed)
        elif event.key() == Qt.Key.Key_Space:
            self._toggle_playback()

    # ------------------------------------------------------------------ #
    # Playback                                                             #
    # ------------------------------------------------------------------ #

    def _toggle_playback(self) -> None:
        """Start or stop playback."""
        if self._playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self) -> None:
        self._playing = True
        self._play_timer.start(max(1, 1000 // self._play_fps))
        self.update()

    def _stop_playback(self) -> None:
        self._playing = False
        self._play_timer.stop()
        self.update()

    def _advance_playhead(self) -> None:
        """Advance by one frame; stop if there are no keyframes to play through."""
        self._set_playhead(self.current_frame + 1)

    # ------------------------------------------------------------------ #
    # Reset view                                                           #
    # ------------------------------------------------------------------ #

    def _reset_view(self) -> None:
        """Scroll to the origin and restore the default zoom level."""
        self.scroll_x = 0
        self.scroll_y = 0
        self.frame_width = _DEFAULT_FRAME_WIDTH
        self.h_scroll.setValue(0)
        self.v_scroll.setValue(0)
        self.update_scrollbars()
        self.update()

    # ------------------------------------------------------------------ #
    # Playhead & interpolation                                             #
    # ------------------------------------------------------------------ #

    def _set_playhead(self, frame: int) -> None:
        """Move the playhead to *frame*, dispatch callbacks, emit ``playhead_moved``."""
        if frame != self.current_frame:
            self.current_frame = frame
            self.playhead_moved.emit(frame)
            self._dispatch_track_callbacks(frame)
        self.update()

    def _dispatch_track_callbacks(self, frame: int) -> None:
        """Set each bound model field to the interpolated track value at *frame*."""
        for track in self.tracks:
            if track.name == _PLACEHOLDER_TRACK:
                continue
            binding = self.track_options.get(track.name)
            if binding is None:
                continue
            model, field = binding
            value = self._interpolate_track(track, frame)
            if value is None:
                continue
            reference = getattr(model, field)
            setattr(model, field, _coerce_value(reference, value))

    def _interpolate_track(self, track: Track, frame: int) -> Any | None:
        """Return the interpolated value of *track* at *frame*, or ``None`` if empty.

        Easing is per-segment: the keyframe at the start of each interval
        controls the interpolation curve.  Values before the first keyframe
        and after the last keyframe are held constant.
        """
        kfs = track.keyframes
        if not kfs:
            return None
        if len(kfs) == 1 or frame <= kfs[0].t:
            return kfs[0].value
        if frame >= kfs[-1].t:
            return kfs[-1].value
        for k1, k2 in itertools.pairwise(kfs):
            if k1.t <= frame < k2.t:
                span = k2.t - k1.t
                if span == 0:
                    return k2.value
                p = (frame - k1.t) / span
                return k1.easing(p, k1.value, k2.value)
        return kfs[-1].value  # unreachable, but keeps type-checker happy

    # ------------------------------------------------------------------ #
    # Track management                                                     #
    # ------------------------------------------------------------------ #

    def _can_add_track(self) -> bool:
        """Return ``True`` if there is at least one unused track option.

        When ``track_options`` is empty (no bindings configured) there is no
        constraint and any number of tracks may be added.
        """
        if not self.track_options:
            return True
        used = {t.name for t in self.tracks if t.name != _PLACEHOLDER_TRACK}
        return len(used) < len(self.track_options)

    def add_track(self, name: str | None = None) -> Track:
        """Add a new track with an auto-assigned colour and return it.

        When *name* is ``None`` the track is created as the ``"..."``
        placeholder, which can later be changed via the context menu.
        """
        if self.track_colors:
            color = self.track_colors[len(self.tracks) % len(self.track_colors)]
        else:
            color = QColor(180, 180, 180)
        track = Track(name if name is not None else _PLACEHOLDER_TRACK, color)
        self.tracks.append(track)
        self.update_scrollbars()
        self.update()
        self.track_added.emit(track)
        return track
