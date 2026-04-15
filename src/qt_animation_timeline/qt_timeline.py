"""Animation timeline editor widget."""

from __future__ import annotations

import itertools
import math
from typing import Any

from qtpy.QtCore import QByteArray, QPoint, QRect, QRectF, QSize, Qt, QTimer
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
from qtpy.QtSvg import QSvgRenderer
from qtpy.QtWidgets import QMenu, QScrollBar, QToolTip, QVBoxLayout, QWidget
from superqt import QSearchableComboBox

from qt_animation_timeline.easing import EasingFunction
from qt_animation_timeline.models import (
    Animation,
    Keyframe,
    PlayMode,
    Track,
)

_DEFAULT_FRAME_WIDTH: float = 15.0
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

_DEFAULT_COLORS: dict[str, QColor] = {
    "bg_color": QColor(30, 30, 30),
    "track_bg_color": QColor(50, 50, 50),
    "time_line_color": QColor(180, 180, 180, 120),
    "time_label_color": QColor(200, 200, 200),
    "current_frame_color": QColor(255, 0, 0),
    "selected_range_color": QColor(0, 0, 255),
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

_PLAY_MODE_ICONS = {
    PlayMode.NORMAL: "play_once",
    PlayMode.LOOP: "loop",
    PlayMode.PINGPONG: "pingpong",
}

# SVG path data (Material Design, viewBox "0 0 24 24") for every button icon.
_BUTTON_ICONS: dict[str, str] = {
    "home": "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z",
    "play": "M8 5v14l11-7z",
    "pause": "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
    "play_once": "M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z",
    "loop": "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v5z",
    "pingpong": "M6.99 11L3 15l3.99 4v-3H14v-2H6.99v-3zM21 9l-3.99-4v3H10v2h7.01v3L21 9z",  # noqa: E501
    "plus": "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
    "minus": "M19 13H5v-2h14v2z",
}


def _render_svg_icon(
    painter: QPainter, rect: QRect, icon_key: str, color: QColor
) -> None:
    """Render a named SVG icon centred within *rect* using *color* as the fill.

    The icon is always drawn as a square region centred inside *rect* so that
    non-square buttons don't stretch the shape.
    """
    path_d = _BUTTON_ICONS[icon_key]
    hex_color = color.name()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<path fill="{hex_color}" d="{path_d}"/>'
        f"</svg>"
    )
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    side = min(rect.width(), rect.height())
    pad = max(2, side // 6)
    icon_side = side - 2 * pad
    cx = rect.x() + rect.width() / 2
    cy = rect.y() + rect.height() / 2
    icon_rect = QRectF(cx - icon_side / 2, cy - icon_side / 2, icon_side, icon_side)
    renderer.render(painter, icon_rect)


class AnimationTimelineWidget(QWidget):
    """Interactive animation timeline widget.

    Wraps an :class:`~qt_animation_timeline.models.Animation` and provides
    a Qt paint/event surface on top of it.  All animation state is accessible
    and controllable programmatically through ``widget.animation``.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        font_size: int = 10,
        track_color_cycle: list[QColor] | None = None,
        track_options: dict[str, tuple[Any, str]] | None = None,
        play_fps: int = 30,
        **color_kwargs: QColor,
    ) -> None:
        super().__init__(parent)

        for name, default in _DEFAULT_COLORS.items():
            setattr(self, name, color_kwargs.get(name, default))

        self.keyframe_size: int = 16
        self.line_thickness: int = 6
        self.frame_width: float = _DEFAULT_FRAME_WIDTH
        self.track_height: int = 28
        self._left_margin_min: int = 80
        self.left_margin: int = self._left_margin_min
        self.left_timeline_pad: int = 20
        self.top_margin: int = 40
        self.min_frame_width: float = 0.05
        self.max_frame_width: float = 80.0

        self.track_color_cycle: list[QColor] = (
            list(track_color_cycle)
            if track_color_cycle is not None
            else list(_DEFAULT_TRACK_COLORS)
        )

        self.animation: Animation = Animation(
            track_options=track_options if track_options is not None else {},
            play_fps=play_fps,
        )

        self.selected_keyframes: list[Keyframe] = []
        self._drag_pivot: Keyframe | None = None
        self._drag_offset: int = 0
        self._dragging_keyframes: bool = False
        self._track_moved: bool = False
        self._scrubbing: bool = False
        self._selecting_range: bool = False
        self._play_range_start: int | None = None
        self._play_range: tuple[int, int] | None = None
        self._box_start: QPoint | None = None
        self._box_rect: QRect | None = None
        self._dragging_track: Track | None = None
        self._track_drag_x: int = 0

        self.scroll_x: int = 0
        self.scroll_y: int = 0

        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._on_timer_tick)
        self._frame_iterator = None

        self.h_scroll = QScrollBar(Qt.Orientation.Horizontal, self)
        self.v_scroll = QScrollBar(Qt.Orientation.Vertical, self)
        self.h_scroll.valueChanged.connect(self._on_hscroll)
        self.v_scroll.valueChanged.connect(self._on_vscroll)

        self.font_size: int = font_size
        self.label_font = QFont("Arial", font_size)

        self.animation.events.current_frame.connect(self._bare_update)
        self.animation.track_added.connect(self._update_geometry)
        self.animation.track_removed.connect(self._on_track_removed)
        self.animation.track_renamed.connect(self._update_geometry)
        self.animation.keyframes_added.connect(self._update_geometry)
        self.animation.keyframes_removed.connect(self._update_geometry)
        self.animation.keyframes_moved.connect(self._update_geometry)
        self.animation.easing_changed.connect(self._bare_update)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def _on_track_removed(self, track: Track) -> None:
        removed_ids = {id(kf) for kf in track.keyframes}
        self.selected_keyframes = [
            kf for kf in self.selected_keyframes if id(kf) not in removed_ids
        ]
        self._update_geometry()

    def _update_geometry(self) -> None:
        self.updateGeometry()
        self.update_scrollbars()
        self.update()

    def _bare_update(self):
        # needed for signals not to pass wrong arguments to qt update
        self.update()

    def sizeHint(self) -> QSize:
        """Return a size fitting current tracks and visible keyframe range."""
        n = max(4, len(self.animation.tracks))
        max_frame = max(
            (kf.t for t in self.animation.tracks for kf in t.keyframes), default=50
        )
        w = int(
            self._left_margin_min
            + self.left_timeline_pad
            + (max_frame + 20) * _DEFAULT_FRAME_WIDTH
        )
        h = self.top_margin + (n + 1) * self.track_height + 40
        return QSize(w, h)

    def minimumSizeHint(self) -> QSize:
        """Return the minimum useful size: 2 tracks high and 10 frames wide."""
        n = max(2, len(self.animation.tracks))
        w = int(
            self._left_margin_min + self.left_timeline_pad + 10 * _DEFAULT_FRAME_WIDTH
        )
        h = self.top_margin + (n + 1) * self.track_height + 40
        return QSize(w, h)

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

    def resizeEvent(self, event) -> None:
        vsw = 20 if self.v_scroll.isVisible() else 0
        hsw = 20 if self.h_scroll.isVisible() else 0
        self.h_scroll.setGeometry(0, self.height() - 20, self.width() - vsw, 20)
        self.v_scroll.setGeometry(self.width() - 20, 0, 20, self.height() - hsw)
        self.update_scrollbars()

    def update_scrollbars(self) -> None:
        """Recalculate scrollbar ranges based on content size."""
        self._update_left_margin()
        max_frame = max(
            (kf.t for t in self.animation.tracks for kf in t.keyframes), default=0
        )
        content_width = self.left_timeline_pad + (max_frame + 20) * self.frame_width
        page_w = self.width() - self.left_margin
        need_hscroll = content_width > page_w
        self.h_scroll.setVisible(need_hscroll)
        if need_hscroll:
            self.h_scroll.setMaximum(int(content_width - page_w))
            self.h_scroll.setPageStep(int(page_w))
        else:
            self.scroll_x = 0
            self.h_scroll.setMaximum(0)

        total_tracks_height = len(self.animation.tracks) * self.track_height
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

    def _update_left_margin(self) -> None:
        if not self.animation.tracks:
            self.left_margin = self._left_margin_min
            return
        metrics = QFontMetrics(self.label_font)
        max_text_w = max(
            metrics.horizontalAdvance(t.name) for t in self.animation.tracks
        )
        self.left_margin = max(self._left_margin_min, 40 + max_text_w + 10)

    def zoom_step(self) -> int:
        """Return the frame-label interval appropriate for the current zoom level.

        Uses order-of-magnitude arithmetic so the step adapts gracefully at
        any zoom level, including very zoomed-out views.
        """
        if self.frame_width <= 0:
            return 1000
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

        painter.save()
        painter.setClipRect(
            self.left_margin,
            self.top_margin,
            self.width() - self.left_margin,
            self.height() - self.top_margin,
        )
        for i, track in enumerate(self.animation.tracks):
            self.draw_track(painter, i, track)
        if self._box_rect is not None:
            self._draw_rubber_band(painter)
        painter.restore()

        self._draw_labels(painter, metrics)
        self._draw_add_button(painter)
        self._draw_control_buttons(painter)
        self._draw_play_range(painter)
        self._draw_playhead(painter)

    def _draw_playhead(self, painter: QPainter) -> None:
        x = self.frame_to_x(self.animation.current_frame)
        if x >= self.left_margin:
            xi = int(x)
            painter.setPen(QPen(self.current_frame_color, 2))
            painter.drawLine(xi, 0, xi, self.height())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.current_frame_color)
            s = 7
            pts = [QPoint(xi - s, 0), QPoint(xi + s, 0), QPoint(xi, s + 5)]
            painter.drawPolygon(pts)

    def _draw_play_range(self, painter: QPainter) -> None:
        if self._play_range is None:
            return
        start, end = (self.frame_to_x(s) for s in self._play_range)

        color_fill = QColor(self.bg_color)
        color_fill.setAlpha(150)

        if start > self.left_margin:
            painter.fillRect(
                self.left_margin,
                self.top_margin,
                int(start) - self.left_margin,
                self.height(),
                color_fill,
            )

        if end < self.width():
            painter.fillRect(
                int(end),
                self.top_margin,
                self.scroll_x + self.width(),
                self.height(),
                color_fill,
            )

        for x in (start, end):
            if self.left_margin <= x <= self.width():
                xi = int(x)
                painter.setPen(QPen(self.selected_range_color, 2))
                painter.drawLine(xi, 0, xi, self.height())

    def _draw_track_backgrounds(self, painter: QPainter) -> None:
        for i in range(len(self.animation.tracks)):
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
        for i, track in enumerate(self.animation.tracks):
            y = self.top_margin + i * self.track_height - self.scroll_y
            if y < -self.track_height or y > self.height():
                continue
            painter.setPen(QColor(*track.color.as_rgb_tuple()))
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
        """Draw the add-track (+) button below all track labels."""
        ay = (
            self.top_margin
            + len(self.animation.tracks) * self.track_height
            - self.scroll_y
        )
        can_add = self._can_add_track()
        color = self.add_button_color if can_add else QColor(60, 60, 60)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, ay, self.left_margin, self.track_height)
        icon_color = QColor(0, 0, 0) if can_add else QColor(100, 100, 100)
        icon_rect = QRect(0, ay, self.left_margin, self.track_height)
        _render_svg_icon(painter, icon_rect, "plus", icon_color)

    def _draw_control_buttons(self, painter: QPainter) -> None:
        btn_w = self.left_margin // 3
        # Last button extends to left_margin exactly to avoid a rounding gap.
        btn_w3 = self.left_margin - 2 * btn_w
        h = self.top_margin

        painter.fillRect(QRect(0, 0, btn_w, h), self.control_btn_color)
        _render_svg_icon(
            painter, QRect(0, 0, btn_w, h), "home", self.control_btn_text_color
        )

        painter.fillRect(QRect(btn_w, 0, btn_w, h), self.loop_btn_color)
        _render_svg_icon(
            painter,
            QRect(btn_w, 0, btn_w, h),
            _PLAY_MODE_ICONS[self.animation.play_mode],
            self.loop_btn_text_color,
        )

        play_icon = "pause" if self._frame_iterator is not None else "play"
        painter.fillRect(QRect(2 * btn_w, 0, btn_w3, h), self.play_btn_color)
        _render_svg_icon(
            painter, QRect(2 * btn_w, 0, btn_w3, h), play_icon, self.play_btn_text_color
        )

    def _draw_rubber_band(self, painter: QPainter) -> None:
        assert self._box_rect is not None
        painter.setBrush(self.rubber_band_fill)
        painter.setPen(QPen(self.rubber_band_border, 1))
        painter.drawRect(self._box_rect)

    def draw_track(self, painter: QPainter, index: int, track: Track) -> None:
        """Draw the connecting line and all keyframes for *track*."""
        cy = int(self.track_center_y(index))
        track_color = QColor(*track.color.as_rgb_tuple())
        kfs = track.keyframes

        if len(kfs) >= 2:
            painter.setPen(QPen(track_color, self.line_thickness))
            for k1, k2 in itertools.pairwise(kfs):
                painter.drawLine(
                    int(self.frame_to_x(k1.t)),
                    cy,
                    int(self.frame_to_x(k2.t)),
                    cy,
                )

        for kf in kfs:
            self.draw_keyframe(painter, index, track, kf)

    def draw_keyframe(
        self, painter: QPainter, track_index: int, track: Track, kf: Keyframe
    ) -> None:
        """Draw a single keyframe as a filled diamond."""
        x = self.frame_to_x(kf.t)
        y = self.track_center_y(track_index)
        selected = kf in self.selected_keyframes
        painter.setBrush(QColor(*track.color.as_rgb_tuple()))
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

        if y < self.top_margin:
            if x < self.left_margin:
                self._handle_control_click(x, y)
            else:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    frame = max(0, self.x_to_frame(x))
                    self._play_range = None
                    self._selecting_range = True
                    self._play_range_start = frame
                    self._frame_iterator = None
                else:
                    self._scrubbing = True
                    self._set_playhead(max(0, self.x_to_frame(x)))
            return

        if x < self.left_margin:
            self._handle_label_click(x, y, event.globalPos())
            return

        kf = self.pos_to_keyframe(x, y)
        if kf is not None:
            self._start_keyframe_drag(event, kf, x)
            return

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.selected_keyframes.clear()
            self._box_start = QPoint(x, y)
            self._box_rect = None
            self.update()
            return

        if self._is_on_track_line(x, y):
            track_index = self.y_to_track_index(y)
            if 0 <= track_index < len(self.animation.tracks):
                self._dragging_track = self.animation.tracks[track_index]
                self._track_drag_x = x
                return

        self.selected_keyframes.clear()
        self.update()

    def _handle_control_click(self, x: int, _y: int) -> None:
        btn_w = self.left_margin // 3
        if x < btn_w:
            self._reset_view()
        elif x < 2 * btn_w:
            self.animation.cycle_play_mode()
            self._frame_iterator = None
        else:
            self.toggle_playback()

    def _handle_label_click(self, x: int, y: int, global_pos: object) -> None:
        """Handle a left-click inside the label column (remove / add buttons)."""
        for i in range(len(self.animation.tracks)):
            ty = self.top_margin + i * self.track_height - self.scroll_y
            btn_size = 14
            by = ty + (self.track_height - btn_size) // 2
            if 8 <= x <= 8 + btn_size and by <= y <= by + btn_size:
                track = self.animation.tracks[i]
                self.animation.remove_track(track.name)
                return

        ay = (
            self.top_margin
            + len(self.animation.tracks) * self.track_height
            - self.scroll_y
        )
        if ay <= y <= ay + self.track_height and self._can_add_track():
            self._show_add_track_popup(global_pos)

    def _start_keyframe_drag(self, event: QMouseEvent, kf: Keyframe, x: int) -> None:
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

        if self._selecting_range:
            frame = max(0, self.x_to_frame(x))
            self._play_range = tuple(sorted((self._play_range_start, frame)))
            self._frame_iterator = None
            self.update()
            return

        if self._dragging_track is not None:
            self._move_track_keyframes(x)
            return

        if self._drag_pivot is not None:
            self._move_selected_keyframes(x)
            self._dragging_keyframes = True
            return

        if self._box_start is not None:
            self._update_box_select(QPoint(x, y))
            return

        if x >= self.left_margin and y >= self.top_margin:
            kf = self.pos_to_keyframe(x, y)
            if kf is not None:
                value_str = repr(kf.value)
                if len(value_str) > 40:
                    value_str = value_str[:37] + "..."
                QToolTip.showText(
                    event.globalPos(),
                    f"t={kf.t}  easing={kf.easing.name}  value={value_str}",
                    self,
                )
            else:
                QToolTip.hideText()

    def _move_track_keyframes(self, x: int) -> None:
        assert self._dragging_track is not None
        offset = self.x_to_frame(x) - self.x_to_frame(self._track_drag_x)
        if offset == 0:
            return
        self.animation.move_keyframes(self._dragging_track.keyframes, offset)
        self._track_drag_x = x
        self._track_moved = True
        self.update_scrollbars()
        self.update()

    def _move_selected_keyframes(self, x: int) -> None:
        assert self._drag_pivot is not None
        target = max(0, self.x_to_frame(x) - self._drag_offset)
        offset = target - self._drag_pivot.t
        if offset == 0:
            return
        self.animation.move_keyframes(self.selected_keyframes, offset)
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
        for i, track in enumerate(self.animation.tracks):
            cy = int(self.track_center_y(i))
            for kf in track.keyframes:
                cx = int(self.frame_to_x(kf.t))
                if rect.contains(cx, cy):
                    result.append(kf)
        return result

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging_track is not None:
            if self._track_moved:
                self.animation.keyframes_moved(list(self._dragging_track.keyframes))
                self.animation._update_bound_models()
            self._dragging_track = None
            self._track_moved = False

        if self._dragging_keyframes and self.selected_keyframes:
            self.animation.keyframes_moved(list(self.selected_keyframes))
            self.animation._update_bound_models()

        self._scrubbing = False
        self._selecting_range = False
        self._drag_pivot = None
        self._dragging_keyframes = False
        self._box_start = None
        self._box_rect = None
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        x, y = event.x(), event.y()

        # Double-click on the control area counts as a second click.
        if y < self.top_margin and x < self.left_margin:
            self._handle_control_click(x, y)
            return

        if x < self.left_margin or y < self.top_margin:
            return

        track_index = self.y_to_track_index(y)
        if not (0 <= track_index < len(self.animation.tracks)):
            return

        frame = max(0, self.x_to_frame(x))
        track = self.animation.tracks[track_index]

        model, attr = self.animation.track_options.get(track.name)
        initial_value = model if attr == "" else getattr(model, attr)

        try:
            self.animation.add_keyframe(track.name, frame, value=initial_value)
        except KeyError:
            return

    def pos_to_keyframe(self, x: float, y: float) -> Keyframe | None:
        """Return the keyframe at screen position *(x, y)*, or ``None``."""
        track_index = self.y_to_track_index(y)
        if not (0 <= track_index < len(self.animation.tracks)):
            return None
        track = self.animation.tracks[track_index]
        cy = self.track_center_y(track_index)
        for kf in track.keyframes:
            kx = self.frame_to_x(kf.t)
            if abs(kx - x) <= self.keyframe_size and abs(cy - y) <= self.keyframe_size:
                return kf
        return None

    def contextMenuEvent(self, event) -> None:
        x, y = event.pos().x(), event.pos().y()
        if y < self.top_margin:
            return
        if x >= self.left_margin:
            self._show_easing_menu(x, y, event.globalPos())
        else:
            self._show_track_change_menu(y, event.globalPos())

    def _segment_left_keyframe_at(self, x: int, y: int) -> Keyframe | None:
        """Return the left keyframe of the segment under *(x, y)*, or ``None``.

        Returns the keyframe that starts the segment, or the last keyframe when
        clicking past all keyframes.  Returns ``None`` when the track is empty.
        """
        track_index = self.y_to_track_index(y)
        if not (0 <= track_index < len(self.animation.tracks)):
            return None
        track = self.animation.tracks[track_index]
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
        """Return the subset of easing functions appropriate for *track*'s type.

        For ``str`` and ``bool`` fields only ``Step`` is offered since linear
        interpolation of those types produces invalid intermediates.
        """
        model, field = self.animation.track_options.get(track.name)
        try:
            value = getattr(model, field)
        except AttributeError:
            return list(EasingFunction)
        return EasingFunction.get_allowed_easings(value)

    def _is_on_track_line(self, x: int, y: int) -> bool:
        """Return ``True`` if *(x, y)* is near an existing track line."""
        track_index = self.y_to_track_index(y)
        if not (0 <= track_index < len(self.animation.tracks)):
            return False
        # do not grab if outside if before or after the last keyframe
        track_frames = self.animation.tracks[track_index].keyframes
        frame = self.x_to_frame(x)
        if (
            len(track_frames) < 2
            or frame < track_frames[0].t
            or frame > track_frames[-1].t
        ):
            return False
        cy = self.track_center_y(track_index)
        return abs(y - cy) <= self.line_thickness + 4

    def _show_easing_menu(self, x: int, y: int, global_pos: object) -> None:
        """Show easing options for the segment under the cursor.

        Only opens when the click lands on a keyframe diamond or within
        ``line_thickness + 4`` pixels of a track's centre line.
        """
        kf = self.pos_to_keyframe(x, y)
        if kf is None:
            if not self._is_on_track_line(x, y):
                return
            kf = self._segment_left_keyframe_at(x, y)
        if kf is None:
            return

        track_index = self.y_to_track_index(y)
        track = (
            self.animation.tracks[track_index]
            if 0 <= track_index < len(self.animation.tracks)
            else None
        )
        allowed = (
            self._get_allowed_easings_for_track(track)
            if track is not None
            else list(EasingFunction)
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
                self.animation.easing_changed(list(targets))

            action.triggered.connect(_set)

        menu.exec(global_pos)

    def _get_track_change_options(self, track: Track) -> list[tuple[str, bool]]:
        """Return ``(option_name, is_enabled)`` pairs for the track-change picker.

        Options already used by *other* tracks are disabled to enforce uniqueness.
        """
        used_by_others = {t.name for t in self.animation.tracks if t is not track}
        return [
            (opt, opt not in used_by_others) for opt in self.animation.track_options
        ]

    def _show_track_change_menu(self, y: int, global_pos: object) -> None:
        """Show a searchable combo-box for changing a track's binding.

        Options already used by other tracks are disabled to enforce uniqueness.
        """
        track_index = self.y_to_track_index(y)
        if not (0 <= track_index < len(self.animation.tracks)):
            return

        track = self.animation.tracks[track_index]
        options = self._get_track_change_options(track)

        container = QWidget(
            self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        container.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        combo = QSearchableComboBox(container)
        for option, enabled in options:
            combo.addItem(option)
            if not enabled:
                item = combo.model().item(combo.model().rowCount() - 1)
                if item is not None:
                    item.setEnabled(False)

        try:
            current_names = [opt for opt, _ in options]
            combo.setCurrentIndex(current_names.index(track.name))
        except ValueError:
            combo.setCurrentIndex(0)

        layout.addWidget(combo)
        container.adjustSize()
        if global_pos is not None:
            container.move(global_pos)
        container.show()

        def _apply(idx: int) -> None:
            model_item = combo.model().item(idx)
            if model_item is not None and not model_item.isEnabled():
                return
            new_name = combo.itemText(idx)
            if new_name != track.name:
                self.animation.remove_track(track.name)
                self.add_track(new_name)
            container.close()

        combo.activated.connect(_apply)

    def _show_add_track_popup(self, global_pos: object) -> None:
        """Show a searchable combo-box to pick which track to add.

        Only available (unused) track options are shown.  The user can either
        click an item or type a search term and press Enter to add the first
        matching (highlighted) item.
        """
        used = {t.name for t in self.animation.tracks}
        available = [name for name in self.animation.track_options if name not in used]
        if not available:
            return

        container = QWidget(
            self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        container.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        combo = QSearchableComboBox(container)
        for name in available:
            combo.addItem(name)

        layout.addWidget(combo)
        container.adjustSize()
        if global_pos is not None:
            container.move(global_pos)
        container.show()

        def _add(idx: int) -> None:
            name = combo.itemText(idx)
            if name:
                self.add_track(name)
            container.close()

        combo.activated.connect(_add)

    def _scroll_x_for_zoom(self, mouse_x: int, old_fw: float, new_fw: float) -> int:
        """Compute the ``scroll_x`` that keeps the frame under *mouse_x* fixed."""
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
            self.animation.remove_keyframes(removed)
            self.selected_keyframes.clear()
        elif event.key() == Qt.Key.Key_Space:
            self.toggle_playback()
        elif event.key() == Qt.Key.Key_Left:
            self._set_playhead(max(0, self.animation.current_frame - 1))
        elif event.key() == Qt.Key.Key_Right:
            self._set_playhead(self.animation.current_frame + 1)

    def toggle_playback(self) -> None:
        if not self._frame_iterator:
            interval = max(1, int(1000 / (self.animation.play_fps)))
            self._frame_iterator = self.animation.iter_frames(self._play_range)
            self._play_timer.start(interval)
        else:
            self._frame_iterator = None
            self._play_timer.stop()
        self.update()

    def is_playing(self) -> bool:
        return self._play_timer.isActive()

    def _on_timer_tick(self) -> None:
        if self._frame_iterator is None:
            self.toggle_playback()
        try:
            next(self._frame_iterator)
        except StopIteration:
            self._play_timer.stop()
            self._frame_iterator = None
            self.update()

    def _reset_view(self) -> None:
        """Fit the entire keyframe range in the viewport and scroll to the origin.

        The zoom level is chosen so that all keyframes from frame 0 to the last
        keyframe (plus a 10 % buffer, minimum 10 frames) fill the available
        timeline width.
        """
        max_frame = max(
            (kf.t for t in self.animation.tracks for kf in t.keyframes), default=0
        )
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
        """Move the playhead to *frame*."""
        self.animation.current_frame = frame

    def _can_add_track(self) -> bool:
        return len(self.animation.tracks) < len(self.animation.track_options)

    def add_track(self, name: str, color: tuple[int, int, int] | None = None) -> Track:
        """Add a new track with an auto-assigned colour and return it."""
        if color is None:
            qcolor = (
                self.track_color_cycle[
                    len(self.animation.tracks) % len(self.track_color_cycle)
                ]
                if self.track_color_cycle
                else None
            )
            color = (
                (qcolor.red(), qcolor.green(), qcolor.blue())
                if qcolor
                else (180, 180, 180)
            )
        return self.animation.add_track(name, color)
