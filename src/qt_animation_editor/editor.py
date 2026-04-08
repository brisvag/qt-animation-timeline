"""Animation timeline editor widget."""

from __future__ import annotations

import itertools
import math
from typing import Any

from qtpy.QtCore import QByteArray, QPoint, QRect, QRectF, Qt, QTimer, Signal
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
from qtpy.QtSvg import QSvgRenderer

from qt_animation_editor.easing import EasingFunction, _coerce_value
from qt_animation_editor.models import Keyframe, Track

# Special placeholder track name — always available and never unique-enforced.
_PLACEHOLDER_TRACK = "..."

# Default frame width in pixels (used by reset-view).
_DEFAULT_FRAME_WIDTH: float = 15.0

# Multiplicative zoom factor per scroll step (Ctrl+wheel).
_ZOOM_FACTOR: float = 1.15

# Okabe-Ito colorblind-friendly palette (seven distinguishable colors).
_DEFAULT_TRACK_COLORS = [
    QColor(0, 114, 178),  # blue
    QColor(230, 159, 0),  # orange
    QColor(0, 158, 115),  # bluish green
    QColor(86, 180, 233),  # sky blue
    QColor(213, 94, 0),  # vermilion
    QColor(240, 228, 66),  # yellow
    QColor(204, 121, 167),  # reddish purple
]

# Default values for all configurable colors.
_DEFAULT_COLORS: dict[str, QColor] = {
    "bg_color": QColor(30, 30, 30),
    "track_bg_color": QColor(50, 50, 50),
    "time_line_color": QColor(180, 180, 180, 120),
    "time_label_color": QColor(200, 200, 200),
    "current_frame_color": QColor(255, 0, 0),
    "add_button_color": QColor(80, 150, 80),
    "remove_button_color": QColor(180, 80, 80),
    "rubber_band_fill": QColor(100, 150, 255, 50),
    "rubber_band_border": QColor(100, 150, 255, 200),
    "control_btn_color": QColor(60, 60, 80),
    "control_btn_text_color": QColor(200, 200, 220),
    "loop_btn_color": QColor(60, 80, 100),
    "loop_btn_text_color": QColor(180, 210, 230),
    "play_btn_color": QColor(60, 80, 60),
    "play_btn_text_color": QColor(180, 220, 180),
    "keyframe_selected_border_color": QColor(255, 255, 0),
}

# Play-mode constants.
_PLAY_NORMAL = 0
_PLAY_LOOP = 1
_PLAY_PINGPONG = 2
# Icon keys (into _BUTTON_ICONS) for each play mode shown on the mode-toggle button.
_PLAY_MODE_ICONS = {_PLAY_NORMAL: "play_once", _PLAY_LOOP: "loop", _PLAY_PINGPONG: "pingpong"}

# SVG path data (Material Design, viewBox "0 0 24 24") for every button icon.
# Paths are filled shapes — colour is injected at render time via _render_svg_icon.
_BUTTON_ICONS: dict[str, str] = {
    "home":      "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z",
    "play":      "M8 5v14l11-7z",
    "pause":     "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
    "play_once": "M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z",
    "loop":      "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v5z",
    "pingpong":  "M6.99 11L3 15l3.99 4v-3H14v-2H6.99v-3zM21 9l-3.99-4v3H10v2h7.01v3L21 9z",
    "plus":      "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
    "minus":     "M19 13H5v-2h14v2z",
}


def _render_svg_icon(painter: QPainter, rect: QRect, icon_key: str, color: QColor) -> None:
    """Render a named SVG icon centred within *rect* using *color* as the fill.

    The icon is always drawn as a square region centred inside *rect* so that
    non-square buttons (e.g. the wide add-track row) don't stretch the shape.
    The icon path is looked up from ``_BUTTON_ICONS`` and rendered via
    ``QSvgRenderer`` so that it scales cleanly at any button size.
    """
    path_d = _BUTTON_ICONS[icon_key]
    hex_color = color.name()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<path fill="{hex_color}" d="{path_d}"/>'
        f"</svg>"
    )
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    # Compute a square sub-rect centred in the button; padding scales with size.
    side = min(rect.width(), rect.height())
    pad = max(2, side // 6)
    icon_side = side - 2 * pad
    cx = rect.x() + rect.width() / 2
    cy = rect.y() + rect.height() / 2
    icon_rect = QRectF(cx - icon_side / 2, cy - icon_side / 2, icon_side, icon_side)
    renderer.render(painter, icon_rect)


class AnimationTimelineWidget(QWidget):
    """Interactive animation timeline widget."""

    playhead_moved = Signal(int)
    track_added = Signal(object)
    track_removed = Signal(object)
    track_changed = Signal(object)
    keyframe_added = Signal(object, object)
    keyframes_removed = Signal(list)
    keyframes_moved = Signal(list)
    easing_changed = Signal(list)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        font_size: int = 10,
        track_color_cycle: list[QColor] | None = None,
        track_options: dict[str, tuple[Any, str]] | None = None,
        playback_speed: float = 1.0,
        **color_kwargs: QColor,
    ) -> None:
        super().__init__(parent)

        for name, default in _DEFAULT_COLORS.items():
            setattr(self, name, color_kwargs.get(name, default))

        self.keyframe_size: int = 16
        self.line_thickness: int = 6
        self.frame_width: float = _DEFAULT_FRAME_WIDTH
        self.track_height: int = 28
        self.left_margin: int = 120
        # Extra pixel space to the left of frame 0 so the "0" label is never
        # clipped by the label column when scrolled to the origin.
        self.left_timeline_pad: int = 20
        self.top_margin: int = 40
        # Allow near-infinite zoom out; zoom_step() adapts via magnitude.
        self.min_frame_width: float = 0.05
        self.max_frame_width: float = 80.0

        # Colours cycled through when adding new tracks.  Replace to customise.
        self.track_color_cycle: list[QColor] = (
            list(track_color_cycle) if track_color_cycle is not None else list(_DEFAULT_TRACK_COLORS)
        )

        # Easing options shown in the right-click menu.  Replace to restrict choices.
        self.easing_options: list[EasingFunction] = list(EasingFunction)

        self.tracks: list[Track] = []

        # Maps real track names to (model_instance, field_name) bindings.
        # When the playhead moves the field is set to the interpolated value.
        # When a keyframe is created the current field value is used as its value.
        # The "..." placeholder track is always available and needs no binding.
        # Example: ``{"x": (my_object, "x"), "y": (my_object, "y")}``
        self.track_options: dict[str, tuple[Any, str]] = (
            dict(track_options) if track_options is not None else {}
        )

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
        self.playback_speed: float = playback_speed
        self._play_mode: int = _PLAY_NORMAL
        self._play_direction: int = 1
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._advance_playhead)

        self.h_scroll = QScrollBar(Qt.Orientation.Horizontal, self)
        self.v_scroll = QScrollBar(Qt.Orientation.Vertical, self)
        self.h_scroll.valueChanged.connect(self._on_hscroll)
        self.v_scroll.valueChanged.connect(self._on_vscroll)

        self.font_size: int = font_size
        self.label_font = QFont("Arial", font_size)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Enable hover events for keyframe value tooltips.
        self.setMouseTracking(True)

    def frame_to_x(self, frame: int | float) -> float:
        """Convert a frame number to a pixel x coordinate."""
        offset = self.left_margin + self.left_timeline_pad
        return offset + frame * self.frame_width - self.scroll_x

    def x_to_frame(self, x: float) -> int:
        """Convert a pixel x coordinate to the nearest frame number."""
        return round(
            (x - self.left_margin - self.left_timeline_pad + self.scroll_x)
            / self.frame_width
        )

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
        content_width = self.left_timeline_pad + (max_frame + 20) * self.frame_width
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
        self._draw_control_buttons(painter)

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
            _render_svg_icon(
                painter, QRect(bx, by, btn_size, btn_size), "minus", QColor(0, 0, 0)
            )

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
        icon_color = QColor(0, 0, 0) if can_add else QColor(100, 100, 100)
        _render_svg_icon(
            painter, QRect(0, ay, self.left_margin, self.track_height), "plus", icon_color
        )

    def _draw_control_buttons(self, painter: QPainter) -> None:
        """Draw the home, play-mode, and play/pause buttons in the top-left corner."""
        btn_w = self.left_margin // 3
        h = self.top_margin
        btn_rect = QRect(0, 0, btn_w, h)

        # Home / reset-view button (left third).
        painter.fillRect(btn_rect, self.control_btn_color)
        _render_svg_icon(painter, btn_rect, "home", self.control_btn_text_color)

        # Play-mode toggle button (middle third) — distinct color from neighbours.
        btn_rect.moveLeft(btn_w)
        painter.fillRect(btn_rect, self.loop_btn_color)
        _render_svg_icon(painter, btn_rect, _PLAY_MODE_ICONS[self._play_mode], self.loop_btn_text_color)

        # Play / pause button (right third).
        btn_rect.moveLeft(2 * btn_w)
        painter.fillRect(btn_rect, self.play_btn_color)
        play_icon = "pause" if self._playing else "play"
        _render_svg_icon(painter, btn_rect, play_icon, self.play_btn_text_color)

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
        selected = kf in self.selected_keyframes
        painter.setBrush(track.color)
        if selected:
            painter.setPen(QPen(self.keyframe_selected_border_color, 2))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        s = self.keyframe_size / 2
        pts = [
            QPoint(int(x), int(y - s)),
            QPoint(int(x + s), int(y)),
            QPoint(int(x), int(y + s)),
            QPoint(int(x - s), int(y)),
        ]
        painter.drawPolygon(pts)

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
        """Handle a click in the top-left control area (home / play-mode / play)."""
        btn_w = self.left_margin // 3
        if x < btn_w:
            self._reset_view()
        elif x < 2 * btn_w:
            self._cycle_play_mode()
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
        # Only left double-click is handled; ignore right-click.
        if event.button() != Qt.MouseButton.LeftButton:
            return

        x, y = event.x(), event.y()

        # Double-click on the top-left control area counts as a second click
        # (e.g. double-clicking the play button toggles playback again).
        if y < self.top_margin and x < self.left_margin:
            self._handle_control_click(x, y)
            return

        # Ignore double-clicks in the ruler strip or label column.
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

    def _is_on_track_line(self, x: int, y: int) -> bool:
        """Return ``True`` if *(x, y)* is vertically close to a track centre line.

        Only pixels within ``line_thickness + 4`` of the track's horizontal
        connecting line qualify.  This is used to restrict the right-click
        easing menu to actual track content rather than empty row space.
        """
        track_index = self.y_to_track_index(y)
        if not (0 <= track_index < len(self.tracks)):
            return False
        cy = self.track_center_y(track_index)
        return abs(y - cy) <= self.line_thickness + 4

    def _show_easing_menu(self, x: int, y: int, global_pos: object) -> None:
        """Show easing options for the segment under the cursor.

        Only opens when the click lands directly on a keyframe diamond or
        within ``line_thickness + 4`` pixels of a track's centre line.
        Clicking in empty space between tracks does nothing.
        """
        kf = self.pos_to_keyframe(x, y)
        if kf is None:
            # Only fall back to segment lookup when on the actual track line.
            if not self._is_on_track_line(x, y):
                return
            kf = self._segment_left_keyframe_at(x, y)
        if kf is None:
            return

        # Determine allowed easings based on the field type of this track.
        track_index = self.y_to_track_index(y)
        track = (
            self.tracks[track_index] if 0 <= track_index < len(self.tracks) else None
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

            def _change(checked: bool, _t: Track = track, _n: str = option) -> None:
                _t.name = _n
                self.update()
                self.track_changed.emit(_t)

            action.triggered.connect(_change)
        menu.exec(global_pos)

    def _scroll_x_for_zoom(self, mouse_x: int, old_fw: float, new_fw: float) -> int:
        """Compute the ``scroll_x`` that keeps the frame under *mouse_x* fixed.

        Solves for *new_scroll_x* such that the exact frame position under the
        mouse cursor maps to the same screen x coordinate after a zoom change
        from *old_fw* to *new_fw* pixels-per-frame.
        """
        frame_at_mouse = (
            mouse_x - self.left_margin - self.left_timeline_pad + self.scroll_x
        ) / old_fw
        new_scroll_x = int(
            self.left_margin
            + self.left_timeline_pad
            + frame_at_mouse * new_fw
            - mouse_x
        )
        return max(0, new_scroll_x)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = event.angleDelta().y() / 120
            factor = _ZOOM_FACTOR**steps
            old_fw = self.frame_width
            new_fw = max(
                self.min_frame_width,
                min(old_fw * factor, self.max_frame_width),
            )
            if new_fw == old_fw:
                return
            self.frame_width = new_fw
            self.scroll_x = self._scroll_x_for_zoom(event.x(), old_fw, new_fw)
            self.update_scrollbars()
            self.h_scroll.blockSignals(True)
            self.h_scroll.setValue(self.scroll_x)
            self.h_scroll.blockSignals(False)
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
        elif event.key() == Qt.Key.Key_Left:
            self._set_playhead(max(0, self.current_frame - 1))
        elif event.key() == Qt.Key.Key_Right:
            self._set_playhead(self.current_frame + 1)

    def _toggle_playback(self) -> None:
        """Start or stop playback."""
        if self._playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self) -> None:
        self._playing = True
        interval = max(1, int(1000 / (self._play_fps * self.playback_speed)))
        self._play_timer.start(interval)
        self.update()

    def _stop_playback(self) -> None:
        self._playing = False
        self._play_timer.stop()
        self.update()

    def _cycle_play_mode(self) -> None:
        """Cycle through normal → loop → pingpong → normal play modes."""
        self._play_mode = (self._play_mode + 1) % 3
        self._play_direction = 1
        self.update()

    def _advance_playhead(self) -> None:
        """Advance by one frame according to the current play mode.

        Normal: stop at the last keyframe.
        Loop: wrap back to frame 0 after the last keyframe.
        Pingpong: reverse direction at each end.
        """
        max_frame = max((kf.t for t in self.tracks for kf in t.keyframes), default=0)
        next_frame = self.current_frame + self._play_direction
        if self._play_mode == _PLAY_NORMAL:
            if next_frame > max_frame:
                self._stop_playback()
                self._set_playhead(max_frame)
                return
        elif self._play_mode == _PLAY_LOOP:
            if next_frame > max_frame:
                next_frame = 0
        elif self._play_mode == _PLAY_PINGPONG:
            if next_frame > max_frame:
                self._play_direction = -1
                next_frame = max(0, max_frame - 1)
            elif next_frame < 0:
                self._play_direction = 1
                next_frame = min(1, max_frame)
        self._set_playhead(next_frame)

    def _reset_view(self) -> None:
        """Fit the entire keyframe range in the viewport and scroll to the origin.

        The zoom level is chosen so that all keyframes from frame 0 to the last
        keyframe (plus a 10 % buffer, minimum 10 frames) fill the available
        timeline width.  Falls back to the default zoom when there are no
        keyframes or the widget has no width yet.
        """
        max_frame = max((kf.t for t in self.tracks for kf in t.keyframes), default=0)
        # When there are no keyframes, buffer alone provides a small visible range.
        buffer = max(10, max_frame // 10)
        total_frames = max_frame + buffer
        available = self.width() - self.left_margin - self.left_timeline_pad
        if available > 0 and total_frames > 0:
            new_fw = available / total_frames
            new_fw = max(self.min_frame_width, min(new_fw, self.max_frame_width))
        else:
            new_fw = _DEFAULT_FRAME_WIDTH
        self.frame_width = new_fw
        self.scroll_x = 0
        self.scroll_y = 0
        self.h_scroll.blockSignals(True)
        self.h_scroll.setValue(0)
        self.h_scroll.blockSignals(False)
        self.v_scroll.setValue(0)
        self.update_scrollbars()
        self.update()

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
        if self.track_color_cycle:
            color = self.track_color_cycle[len(self.tracks) % len(self.track_color_cycle)]
        else:
            color = QColor(180, 180, 180)
        track = Track(name if name is not None else _PLACEHOLDER_TRACK, color)
        self.tracks.append(track)
        self.update_scrollbars()
        self.update()
        self.track_added.emit(track)
        return track
