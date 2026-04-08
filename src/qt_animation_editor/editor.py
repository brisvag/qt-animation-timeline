"""Animation timeline editor widget."""

from __future__ import annotations

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
from qtpy.QtWidgets import QApplication, QMenu, QScrollBar, QVBoxLayout, QWidget

EASING_OPTIONS: list[str] = ["Linear", "Ease In", "Ease Out", "Ease In Out", "Constant"]

_TRACK_COLORS = [
    QColor(255, 100, 100),
    QColor(100, 200, 100),
    QColor(100, 150, 255),
    QColor(255, 200, 80),
    QColor(200, 100, 255),
    QColor(80, 220, 200),
]


class Keyframe:
    """A keyframe with a time position, value, and separate in/out easing curves."""

    def __init__(
        self,
        t: int,
        value: float = 0,
        easing_in: str = "Linear",
        easing_out: str = "Linear",
    ) -> None:
        self.t = max(0, int(t))
        self.value = value
        self.easing_in = easing_in
        self.easing_out = easing_out


class Track:
    """A named animation track holding an ordered list of keyframes."""

    def __init__(self, name: str, color: QColor | None = None) -> None:
        self.name = name
        self.color = color or QColor(180, 180, 180)
        self.keyframes: list[Keyframe] = []

    def add_keyframe(
        self,
        t: int,
        value: float = 0,
        easing_in: str = "Linear",
        easing_out: str = "Linear",
    ) -> Keyframe:
        """Add a keyframe at frame *t*, raising `KeyError` if one already exists."""
        t = max(0, int(t))
        for kf in self.keyframes:
            if kf.t == t:
                raise KeyError(f"keyframe at frame {t} already exists")
        kf = Keyframe(t, value, easing_in, easing_out)
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
    # Emitted when a track is renamed via the context menu.
    track_renamed = Signal(object)
    # Emitted when a keyframe is created by the user.
    keyframe_added = Signal(object, object)
    # Emitted after one or more keyframes are deleted.
    keyframes_removed = Signal(list)
    # Emitted at the end of a keyframe drag operation.
    keyframes_moved = Signal(list)
    # Emitted when easing is changed via the context menu.
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

        self.tracks: list[Track] = []
        self.track_options: list[str] = [
            "Location X",
            "Location Y",
            "Rotation",
            "Scale",
        ]

        self.current_frame: int = 0

        self.scroll_x: int = 0
        self.scroll_y: int = 0

        self.selected_keyframes: list[Keyframe] = []
        # Anchor keyframe used to compute deltas during a multi-keyframe drag.
        self._drag_pivot: Keyframe | None = None
        self._drag_offset: int = 0
        self._dragging_keyframes: bool = False

        self._scrubbing: bool = False

        # Rubber-band box-selection state.
        self._box_start: QPoint | None = None
        self._box_rect: QRect | None = None

        self.h_scroll = QScrollBar(Qt.Orientation.Horizontal, self)
        self.v_scroll = QScrollBar(Qt.Orientation.Vertical, self)
        self.h_scroll.valueChanged.connect(self._on_hscroll)
        self.v_scroll.valueChanged.connect(self._on_vscroll)

        self.label_font = QFont("Arial", 10)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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

            bx, by = 8, y + (self.track_height - 14) // 2
            painter.setBrush(self.remove_button_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(bx, by, 14, 14)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(bx + 4, by + 11, "-")

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
            for k1, k2 in zip(track.keyframes[:-1], track.keyframes[1:], strict=False):
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

        # Empty content area: begin rubber-band selection.
        self.selected_keyframes.clear()
        self._box_start = QPoint(x, y)
        self._box_rect = None
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

        try:
            kf = track.add_keyframe(frame)
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

    def contextMenuEvent(self, event) -> None:
        x, y = event.pos().x(), event.pos().y()
        if x >= self.left_margin:
            self._show_easing_menu(x, y, event.globalPos())
        else:
            self._show_track_rename_menu(y, event.globalPos())

    def _show_easing_menu(self, x: int, y: int, global_pos: object) -> None:
        """Show a context menu with separate Easing In / Easing Out sub-menus."""
        kf = self.pos_to_keyframe(x, y)
        if kf is None:
            return

        targets = self.selected_keyframes if kf in self.selected_keyframes else [kf]
        menu = QMenu(self)

        def _add_submenu(title: str, attr: str) -> None:
            submenu = menu.addMenu(title)
            for easing in EASING_OPTIONS:
                action = submenu.addAction(easing)
                action.setCheckable(True)
                action.setChecked(all(getattr(k, attr) == easing for k in targets))

                def _set(checked: bool, _e: str = easing, _a: str = attr) -> None:
                    for k in targets:
                        setattr(k, _a, _e)
                    self.update()
                    self.easing_changed.emit(list(targets))

                action.triggered.connect(_set)

        _add_submenu("Easing In", "easing_in")
        _add_submenu("Easing Out", "easing_out")
        menu.exec(global_pos)

    def _show_track_rename_menu(self, y: int, global_pos: object) -> None:
        """Show a context menu for renaming a track to one of the allowed options."""
        track_index = self.y_to_track_index(y)
        if not (0 <= track_index < len(self.tracks)):
            return

        track = self.tracks[track_index]
        menu = QMenu(self)
        for option in self.track_options:
            action = menu.addAction(option)
            action.setCheckable(True)
            action.setChecked(track.name == option)

            def _rename(checked: bool, _t: Track = track, _n: str = option) -> None:
                _t.name = _n
                self.update()
                self.track_renamed.emit(_t)

            action.triggered.connect(_rename)
        menu.exec(global_pos)

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

    def _set_playhead(self, frame: int) -> None:
        """Move the playhead to *frame* and emit ``playhead_moved`` if it changed."""
        if frame != self.current_frame:
            self.current_frame = frame
            self.playhead_moved.emit(frame)
        self.update()

    def add_track(self, name: str | None = None) -> Track:
        """Add a new track with an auto-assigned colour and return it."""
        color = _TRACK_COLORS[len(self.tracks) % len(_TRACK_COLORS)]
        track = Track(name or self.track_options[0], color)
        self.tracks.append(track)
        self.update_scrollbars()
        self.update()
        self.track_added.emit(track)
        return track


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    timeline = AnimationTimelineWidget()

    timeline.add_track("Location X")
    timeline.add_track("Rotation Z")

    for f in [50, 400, 900, 1500]:
        timeline.tracks[0].add_keyframe(f)

    for f in [100, 1200, 1700]:
        timeline.tracks[1].add_keyframe(f)

    main = QWidget()

    layout = QVBoxLayout(main)
    layout.addWidget(timeline)

    main.resize(1200, 400)
    main.show()

    app.exec()
