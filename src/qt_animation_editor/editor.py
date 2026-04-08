"""Animation timeline editor widget."""

from __future__ import annotations

import itertools
from enum import Enum
from typing import Any

from qtpy.QtCore import QPoint, QRect, QRectF, Qt, Signal
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
from qtpy.QtWidgets import QMenu, QScrollBar, QWidget

# Special placeholder track name - always available and never unique-enforced.
_PLACEHOLDER_TRACK = "..."


def _easing_linear(p: float) -> float:
    return p


def _easing_bool(p: float) -> float:
    """Step function: holds the start value, then jumps to the end value at p=1."""
    return float(p >= 1.0)


class EasingFunction(Enum):
    """Easing functions for keyframe segments.

    Each member is callable as ``f(p) -> float`` where *p* ∈ [0, 1] is the
    normalised progress within a segment.  The return value is the interpolation
    factor applied to the value range ``(v_end - v_start)``.
    """

    Linear = _easing_linear
    Bool = _easing_bool

    def __call__(self, p: float) -> float:
        return self.value(p)


def _coerce_value(reference: Any, interpolated: Any) -> Any:
    """Coerce *interpolated* to match the type of *reference* for scalar types.

    Handles Python ``bool``, ``int``, and ``float`` precisely.  Array-like
    values (e.g. numpy arrays) are returned as-is because element-wise
    arithmetic already produces the correct type.
    """
    # bool must be checked before int - bool is a subclass of int.
    if isinstance(reference, bool):
        return bool(round(float(interpolated)))
    if isinstance(reference, int):
        return round(float(interpolated))
    if isinstance(reference, float):
        return float(interpolated)
    # numpy arrays and other array-like types: arithmetic preserves the type.
    return interpolated


_DEFAULT_TRACK_COLORS = [
    QColor(255, 100, 100),
    QColor(100, 200, 100),
    QColor(100, 150, 255),
    QColor(255, 200, 80),
    QColor(200, 100, 255),
    QColor(80, 220, 200),
]


class Keyframe:
    """A keyframe: time position, value, and easing for the segment after it."""

    def __init__(
        self,
        t: int,
        value: Any = 0,
        easing: EasingFunction = EasingFunction.Linear,
    ) -> None:
        self.t = max(0, int(t))
        self.value = value
        # Controls the interpolation curve from this keyframe to the next one.
        self.easing = easing


class Track:
    """A named animation track holding an ordered list of keyframes."""

    def __init__(self, name: str, color: QColor | None = None) -> None:
        self.name = name
        self.color = color or QColor(180, 180, 180)
        self.keyframes: list[Keyframe] = []

    def add_keyframe(
        self,
        t: int,
        value: Any = 0,
        easing: EasingFunction = EasingFunction.Linear,
    ) -> Keyframe:
        """Add a keyframe at frame *t*, raising `KeyError` if one already exists."""
        t = max(0, int(t))
        for kf in self.keyframes:
            if kf.t == t:
                msg = f"keyframe at frame {t} already exists in track \"{self.name}\""
                raise KeyError(msg)
        kf = Keyframe(t, value, easing)
        self.keyframes.append(kf)
        self.keyframes.sort(key=lambda k: k.t)
        return kf


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

        self.keyframe_size: int = 10
        self.line_thickness: int = 2
        self.frame_width: float = 15
        self.track_height: int = 40
        self.left_margin: int = 120
        self.top_margin: int = 40
        self.min_frame_width: float = 2
        self.max_frame_width: float = 50

        # Colours cycled through when adding new tracks.  Replace to customise.
        self.track_colors: list[QColor] = list(_DEFAULT_TRACK_COLORS)

        # Easing options shown in the right-click menu.  Replace to restrict choices.
        self.easing_options: list[EasingFunction] = list(EasingFunction)

        self.tracks: list[Track] = []

        # Maps real track names to (model_instance, field_name) bindings.
        # When the playhead moves the field is set to the interpolated value.
        # When a keyframe is created the current field value is used as its value.
        # The "..." placeholder track is always available and needs no binding.
        # Example: ``{"A": (my_object, "x"), "B": (my_object, "y")}``
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

        self.h_scroll = QScrollBar(Qt.Orientation.Horizontal, self)
        self.v_scroll = QScrollBar(Qt.Orientation.Vertical, self)
        self.h_scroll.valueChanged.connect(self._on_hscroll)
        self.v_scroll.valueChanged.connect(self._on_vscroll)

        self.label_font = QFont("Arial", 10)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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
        """Return the frame-label interval appropriate for the current zoom level."""
        w = self.frame_width
        if w < 3:
            return 500
        if w < 5:
            return 200
        if w < 10:
            return 100
        if w < 20:
            return 20
        if w < 40:
            return 10
        return 1

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

        # Playhead: only draw when it is to the right of the label column.
        x = self.frame_to_x(self.current_frame)
        if x >= self.left_margin:
            painter.setPen(QPen(self.current_frame_color, 2))
            painter.drawLine(int(x), self.top_margin, int(x), self.height())

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
        step = self.zoom_step()
        max_frame = int(
            (self.width() + self.scroll_x - self.left_margin) / self.frame_width
        )
        for frame in range(0, max_frame + 1, step):
            x = self.frame_to_x(frame)
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
            # Centre the '-' glyph within the button rectangle.
            lx = bx + (btn_size - metrics.horizontalAdvance("-")) // 2
            ly = by + (btn_size + metrics.ascent() - metrics.descent()) // 2
            painter.drawText(lx, ly, "-")

    def _draw_add_button(self, painter: QPainter) -> None:
        """Draw the add-track (+) button, which fills the full label column."""
        ay = self.top_margin + len(self.tracks) * self.track_height - self.scroll_y
        painter.setBrush(self.add_button_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, ay, self.left_margin, self.track_height)
        painter.setPen(Qt.GlobalColor.black)
        cx = self.left_margin // 2
        cy = ay + self.track_height // 2
        painter.drawLine(cx - 8, cy, cx + 8, cy)
        painter.drawLine(cx, cy - 8, cx, cy + 8)

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
        """Draw a single keyframe as a filled circle."""
        x = self.frame_to_x(kf.t)
        y = self.track_center_y(track_index) - self.keyframe_size / 2
        color = (
            track.color if kf not in self.selected_keyframes else QColor(255, 255, 0)
        )
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QRectF(
                x - self.keyframe_size / 2,
                y,
                self.keyframe_size,
                self.keyframe_size,
            )
        )

    # ------------------------------------------------------------------ #
    # Mouse events                                                         #
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        x, y = event.x(), event.y()

        # Ruler area: click or drag here to scrub the playhead.
        if y < self.top_margin:
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
        if ay <= y <= ay + self.track_height:
            self.add_track()

    def _start_keyframe_drag(self, event: QMouseEvent, kf: Keyframe, x: int) -> None:
        """Set up drag state for the clicked keyframe."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if kf in self.selected_keyframes:
                self.selected_keyframes.remove(kf)
            else:
                self.selected_keyframes.append(kf)
        elif kf not in self.selected_keyframes:
            # Clicking an unselected keyframe replaces the selection;
            # clicking an already-selected one preserves the multi-selection.
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

        self._scrubbing = False
        self._drag_pivot = None
        self._dragging_keyframes = False
        self._box_start = None
        self._box_rect = None
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
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
        # Clicking after the last keyframe → easing of the last segment.
        if frame > kfs[-1].t:
            return kfs[-1]
        return None

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

        targets = self.selected_keyframes if kf in self.selected_keyframes else [kf]
        menu = QMenu(self)

        for ef in self.easing_options:
            action = menu.addAction(ef.name)
            action.setCheckable(True)
            action.setChecked(all(k.easing is ef for k in targets))

            def _set(checked: bool, _ef: EasingFunction = ef) -> None:
                for k in targets:
                    k.easing = _ef
                self.update()
                self.easing_changed.emit(list(targets))

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
        # Names currently used by tracks other than the one being changed.
        used_by_others = {
            t.name
            for t in self.tracks
            if t is not track and t.name != _PLACEHOLDER_TRACK
        }

        menu = QMenu(self)
        # Always offer the placeholder first.
        for option in [_PLACEHOLDER_TRACK, *self.track_options]:
            action = menu.addAction(option)
            action.setCheckable(True)
            action.setChecked(track.name == option)
            # Disable real options already used by another track.
            if option != _PLACEHOLDER_TRACK and option in used_by_others:
                action.setEnabled(False)

            def _change(checked: bool, _t: Track = track, _n: str = option) -> None:
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
            delta = event.angleDelta().y() / 120
            self.frame_width = max(
                self.min_frame_width,
                min(self.frame_width + delta * 2, self.max_frame_width),
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
                # Guard against duplicate positions produced by dragging.
                if span == 0:
                    return k2.value
                p = (frame - k1.t) / span
                return k1.value + (k2.value - k1.value) * k1.easing(p)
        return kfs[-1].value  # unreachable, but keeps type-checker happy

    # ------------------------------------------------------------------ #
    # Track management                                                     #
    # ------------------------------------------------------------------ #

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
