from qtpy.QtCore import QRectF, Qt
from qtpy.QtGui import QColor, QFont, QKeyEvent, QPainter, QPen
from qtpy.QtWidgets import QApplication, QScrollBar, QVBoxLayout, QWidget

_TRACK_COLORS = [
    QColor(255, 100, 100),
    QColor(100, 200, 100),
    QColor(100, 150, 255),
    QColor(255, 200, 80),
    QColor(200, 100, 255),
    QColor(80, 220, 200),
]


class Keyframe:
    def __init__(self, t, value=0, easing="Linear"):
        self.t = max(0, int(t))
        self.value = value
        self.easing = easing


class Track:
    def __init__(self, name, color=None):
        self.name = name
        self.color = color or QColor(180, 180, 180)
        self.keyframes = []

    def add_keyframe(self, t, value=0, easing="Linear"):
        t = max(0, round(t))
        for kf in self.keyframes:
            if kf.t == t:
                raise KeyError
        kf = Keyframe(t, value, easing)
        self.keyframes.append(kf)
        self.keyframes.sort(key=lambda k: k.t)
        return kf


class AnimationTimelineWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.bg_color = QColor(30, 30, 30)
        self.track_bg_color = QColor(50, 50, 50)
        self.time_line_color = QColor(180, 180, 180, 120)
        self.time_label_color = QColor(200, 200, 200)
        self.current_frame_color = QColor(255, 0, 0)

        self.add_button_color = QColor(80, 150, 80)
        self.remove_button_color = QColor(180, 80, 80)

        self.keyframe_size = 10
        self.line_thickness = 2

        self.frame_width = 15
        self.track_height = 40

        self.left_margin = 120
        self.top_margin = 40

        self.min_frame_width = 2
        self.max_frame_width = 50

        self.tracks = []
        self.track_options = ["Location X", "Location Y", "Rotation", "Scale"]

        self.current_frame = 0

        self.scroll_x = 0
        self.scroll_y = 0

        self.selected_keyframes = []
        self.selected_keyframe = None
        self.drag_offset = 0

        self.scrubbing = False

        self.h_scroll = QScrollBar(Qt.Horizontal, self)
        self.v_scroll = QScrollBar(Qt.Vertical, self)

        self.h_scroll.valueChanged.connect(self.on_hscroll)
        self.v_scroll.valueChanged.connect(self.on_vscroll)

        self.label_font = QFont("Arial", 10)

        self.setFocusPolicy(Qt.StrongFocus)

    # ------------------------------------------------

    def frame_to_x(self, frame):
        return self.left_margin + frame * self.frame_width - self.scroll_x

    def x_to_frame(self, x):
        return round((x - self.left_margin + self.scroll_x) / self.frame_width)

    def y_to_track_index(self, y):
        return int((y - self.top_margin + self.scroll_y) / self.track_height)

    # ------------------------------------------------

    def resizeEvent(self, event):
        vsw = 20 if self.v_scroll.isVisible() else 0

        self.h_scroll.setGeometry(0, self.height() - 20, self.width() - vsw, 20)

        self.v_scroll.setGeometry(self.width() - 20, 0, 20, self.height() - 20)

        self.update_scrollbars()

    def update_scrollbars(self):
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

    def on_hscroll(self, v):
        self.scroll_x = v
        self.update()

    def on_vscroll(self, v):
        self.scroll_y = v
        self.update()

    # ------------------------------------------------

    def zoom_step(self):
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

    # ------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.bg_color)
        painter.setFont(self.label_font)

        metrics = painter.fontMetrics()

        # track backgrounds
        for i, _track in enumerate(self.tracks):
            y = self.top_margin + i * self.track_height - self.scroll_y

            painter.fillRect(
                self.left_margin,
                y,
                self.width() - self.left_margin,
                self.track_height,
                self.track_bg_color,
            )

        # frame grid
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
            painter.drawText(
                int(x) - metrics.horizontalAdvance(str(frame)) // 2,
                self.top_margin - 10,
                str(frame),
            )

        # tracks
        for i, track in enumerate(self.tracks):
            self.draw_track(painter, i, track)

        # labels
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
            by = y + (self.track_height - 14) // 2

            painter.setBrush(self.remove_button_color)
            painter.setPen(Qt.NoPen)
            painter.drawRect(bx, by, 14, 14)

            painter.setPen(Qt.black)
            painter.drawText(bx + 4, by + 11, "-")

        # add button
        size = 18

        y = (
            self.top_margin
            + len(self.tracks) * self.track_height
            - self.scroll_y
            + (self.track_height - size) // 2
        )

        x = 8

        painter.setBrush(self.add_button_color)
        painter.setPen(Qt.NoPen)
        painter.drawRect(x, y, size, size)

        painter.setPen(Qt.black)

        painter.drawLine(x + 4, y + size // 2, x + size - 4, y + size // 2)
        painter.drawLine(x + size // 2, y + 4, x + size // 2, y + size - 4)

        # playhead
        x = self.frame_to_x(self.current_frame)

        painter.setPen(QPen(self.current_frame_color, 2))
        painter.drawLine(int(x), self.top_margin, int(x), self.height())

    # ------------------------------------------------

    def draw_track(self, painter, index, track):
        y = self.top_margin + index * self.track_height - self.scroll_y

        if len(track.keyframes) >= 2:
            painter.setPen(QPen(track.color, self.line_thickness))

            for k1, k2 in zip(track.keyframes[:-1], track.keyframes[1:], strict=False):
                painter.drawLine(
                    int(self.frame_to_x(k1.t)),
                    y + self.track_height // 2,
                    int(self.frame_to_x(k2.t)),
                    y + self.track_height // 2,
                )

        for kf in track.keyframes:
            self.draw_keyframe(painter, index, track, kf)

    def draw_keyframe(self, painter, track_index, track, kf):
        x = self.frame_to_x(kf.t)

        y = (
            self.top_margin
            + track_index * self.track_height
            - self.scroll_y
            + self.track_height // 2
        )

        y -= self.keyframe_size // 2

        color = (
            track.color if kf not in self.selected_keyframes else QColor(255, 255, 0)
        )

        painter.setBrush(color)
        painter.setPen(Qt.NoPen)

        painter.drawEllipse(
            QRectF(
                x - self.keyframe_size // 2,
                y,
                self.keyframe_size,
                self.keyframe_size,
            )
        )

    # ------------------------------------------------
    # mouse
    # ------------------------------------------------

    def mousePressEvent(self, event):
        playhead_x = self.frame_to_x(self.current_frame)

        if abs(event.x() - playhead_x) < 6:
            self.scrubbing = True
            return

        x = event.x()
        y = event.y()

        # remove buttons
        for i in range(len(self.tracks)):
            ty = self.top_margin + i * self.track_height - self.scroll_y

            if 8 <= x <= 22 and ty + 13 <= y <= ty + 27:
                self.tracks.pop(i)
                self.update_scrollbars()
                self.update()
                return

        # add button
        ay = self.top_margin + len(self.tracks) * self.track_height - self.scroll_y
        add_btn_size = 18
        add_btn_y = ay + (self.track_height - add_btn_size) // 2

        if 8 <= x <= 8 + add_btn_size and add_btn_y <= y <= add_btn_y + add_btn_size:
            self.add_track()
            return

        clicked = self.pos_to_keyframe(x, y)

        if clicked:
            if event.modifiers() & Qt.ControlModifier:
                if clicked in self.selected_keyframes:
                    self.selected_keyframes.remove(clicked)
                else:
                    self.selected_keyframes.append(clicked)

            else:
                self.selected_keyframes = [clicked]

            self.selected_keyframe = clicked
            self.drag_offset = self.x_to_frame(x) - clicked.t

            self.update()
            return

        self.selected_keyframes.clear()
        self.current_frame = max(0, self.x_to_frame(x))

        self.update()

    def mouseMoveEvent(self, event):
        if self.scrubbing:
            self.current_frame = max(0, self.x_to_frame(event.x()))
            self.update()
            return

        if not (self.selected_keyframes and self.selected_keyframe):
            return

        frame = self.x_to_frame(event.x()) - self.drag_offset
        frame = max(0, frame)

        delta = frame - self.selected_keyframe.t

        for kf in self.selected_keyframes:
            kf.t = max(0, kf.t + delta)

        for track in self.tracks:
            track.keyframes.sort(key=lambda k: k.t)

        self.update_scrollbars()
        self.update()

    def mouseReleaseEvent(self, event):
        self.selected_keyframe = None
        self.scrubbing = False

    def mouseDoubleClickEvent(self, event):
        x = event.x()
        y = event.y()

        if x < self.left_margin:
            return

        track_index = self.y_to_track_index(y)

        if not (0 <= track_index < len(self.tracks)):
            return

        frame = max(0, self.x_to_frame(x))
        track = self.tracks[track_index]

        try:
            track.add_keyframe(frame)
        except KeyError:
            # A keyframe already exists at this frame; silently ignore the duplicate.
            pass

        self.update_scrollbars()
        self.update()

    # ------------------------------------------------

    def pos_to_keyframe(self, x, y):
        track_index = self.y_to_track_index(y)

        if not (0 <= track_index < len(self.tracks)):
            return None

        track = self.tracks[track_index]

        y_center = (
            self.top_margin
            + track_index * self.track_height
            - self.scroll_y
            + self.track_height // 2
        )

        for kf in track.keyframes:
            x_kf = self.frame_to_x(kf.t)

            if (
                abs(x_kf - x) <= self.keyframe_size
                and abs(y_center - y) <= self.keyframe_size
            ):
                return kf

        return None

    # ------------------------------------------------

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y() / 120
            self.frame_width += delta * 2

            self.frame_width = max(
                self.min_frame_width,
                min(self.frame_width, self.max_frame_width),
            )

            self.update_scrollbars()
            self.update()
            return

        self.scroll_x += event.angleDelta().y()

        self.scroll_x = max(0, min(self.scroll_x, self.h_scroll.maximum()))
        self.h_scroll.setValue(self.scroll_x)

        self.update()

    # ------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Delete:
            for track in self.tracks:
                track.keyframes = [
                    kf for kf in track.keyframes if kf not in self.selected_keyframes
                ]

            self.selected_keyframes.clear()

            self.update_scrollbars()
            self.update()

    # ------------------------------------------------

    def add_track(self, name=None):
        color = _TRACK_COLORS[len(self.tracks) % len(_TRACK_COLORS)]
        self.tracks.append(Track(name or self.track_options[0], color))
        self.update_scrollbars()
        self.update()


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
