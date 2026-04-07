from qtpy.QtWidgets import QApplication, QWidget, QVBoxLayout, QScrollBar, QMenu
from qtpy.QtGui import QPainter, QColor, QPen, QFont, QKeyEvent
from qtpy.QtCore import Qt, QRectF

class Keyframe:
    def __init__(self, frame, value=0, easing='Linear'):
        self.frame = max(0,int(frame))
        self.value = value
        self.easing = easing

class Track:
    def __init__(self, name, color=QColor(200,200,50)):
        self.name = name
        self.color = color
        self.keyframes = []

    def add_keyframe(self, frame, value=0):
        frame = max(0,int(round(frame)))
        for kf in self.keyframes:
            if kf.frame == frame:
                return kf
        kf = Keyframe(frame,value)
        self.keyframes.append(kf)
        self.keyframes.sort(key=lambda k:k.frame)
        return kf

    def remove_keyframe(self, frame):
        frame = max(0,int(round(frame)))
        self.keyframes = [kf for kf in self.keyframes if kf.frame!=frame]

class TimelineWidget(QWidget):
    # --------- Customizable Colors ---------
    bg_color = QColor(30,30,30)
    track_bg_color = QColor(50,50,50)
    time_line_color = QColor(180,180,180,120)
    time_label_color = QColor(200,200,200)
    current_frame_color = QColor(255,0,0)
    add_button_color = QColor(80,150,80)
    remove_button_color = QColor(180,80,80)
    button_text_color = QColor(0,0,0)
    text_color = QColor(255,255,255)

    # --------- Customizable Sizes ---------
    keyframe_size = 10
    line_thickness = 2

    def __init__(self,parent=None):
        super().__init__(parent)
        self.tracks=[]
        self.allowed_track_names=["Location X","Location Y","Rotation Z","Scale"]
        self.current_frame=0
        self.frame_width=15
        self.track_height=40
        self.selected_keyframe=None
        self.drag_offset=0
        self.scroll_x=0
        self.left_margin=120
        self.top_margin=40

        self.selected_keyframes=[]
        self.scrollbar=QScrollBar(Qt.Horizontal,self)
        self.scrollbar.valueChanged.connect(self.on_scroll)
        self.label_font=QFont("Arial",10)

        self.min_frame_width=2
        self.max_frame_width=50

    # ---------- Scroll & Resize ----------
    def resizeEvent(self,event):
        self.scrollbar.setGeometry(0,self.height()-20,self.width(),20)
        self.update_scrollbar()

    def update_scrollbar(self):
        max_frame=max((kf.frame for t in self.tracks for kf in t.keyframes),default=0)
        content_width = (max_frame+20)*self.frame_width
        page_width=self.width()-self.left_margin
        self.scrollbar.setMaximum(max(0,int(content_width-page_width)))
        self.scrollbar.setPageStep(int(page_width))
        self.scroll_x=max(0,min(self.scroll_x,self.scrollbar.maximum()))

    def on_scroll(self,value):
        self.scroll_x=max(0,min(value,self.scrollbar.maximum()))
        self.update()

    # ---------- Painting ----------
    def paintEvent(self,event):
        painter=QPainter(self)
        painter.fillRect(self.rect(), self.bg_color)
        painter.setFont(self.label_font)
        metrics = painter.fontMetrics()

        # ---------- Top time-step labels ----------
        if self.frame_width<3: step=500
        elif self.frame_width<5: step=200
        elif self.frame_width<10: step=100
        elif self.frame_width<20: step=20
        elif self.frame_width<40: step=10
        else: step=1
        max_frame_to_draw=int((self.width()+self.scroll_x-self.left_margin)/self.frame_width)
        label_y = self.top_margin - 10
        for frame in range(0,max_frame_to_draw+1,step):
            x=self.left_margin + frame*self.frame_width - self.scroll_x
            if x>=self.left_margin-1:
                painter.setPen(self.time_label_color)
                painter.drawText(int(x)-metrics.width(str(frame))//2, label_y, str(frame))
                painter.setPen(self.time_line_color)
                painter.drawLine(int(x), self.top_margin, int(x), self.height())

        # ---------- Tracks and keyframes ----------
        for i,track in enumerate(self.tracks):
            y=self.top_margin+i*self.track_height
            painter.fillRect(0,y,self.width(),self.track_height,self.track_bg_color)

            # Track name
            name_y = y + self.track_height//2 + metrics.ascent()//2 - 2
            painter.setPen(track.color)
            painter.drawText(35, name_y, track.name)

            # - button
            button_size = self.track_height//2
            button_margin = 5
            painter.setBrush(self.remove_button_color)
            painter.setPen(Qt.NoPen)
            painter.drawRect(button_margin, y + (self.track_height-button_size)//2, button_size, button_size)
            painter.setPen(self.button_text_color)
            painter.drawText(button_margin + 7, y + self.track_height//2 + 5, "-")

            # Connect keyframes
            if len(track.keyframes)>=2:
                painter.setPen(QPen(track.color,self.line_thickness))
                for k1,k2 in zip(track.keyframes[:-1],track.keyframes[1:]):
                    x1=self.left_margin+k1.frame*self.frame_width-self.scroll_x
                    x2=self.left_margin+k2.frame*self.frame_width-self.scroll_x
                    y_line = y + self.track_height//2
                    painter.drawLine(int(x1), int(y_line), int(x2), int(y_line))

            # Draw keyframes
            for kf in track.keyframes:
                x=self.left_margin+kf.frame*self.frame_width-self.scroll_x
                y_dot = y + self.track_height//2 - self.keyframe_size//2
                painter.setBrush(track.color if kf not in self.selected_keyframes else QColor(255,255,0))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QRectF(int(x)-self.keyframe_size//2, int(y_dot), self.keyframe_size, self.keyframe_size))

        # Current frame line clamped
        clamped_frame = max(0,self.current_frame)
        x=self.left_margin + clamped_frame*self.frame_width - self.scroll_x
        painter.setPen(QPen(self.current_frame_color,2))
        painter.drawLine(int(x),self.top_margin,int(x),self.height())

        # + Add Track button
        text = "+ Add Track"
        text_width = metrics.width(text)
        text_height = metrics.height()
        padding_x = 10
        padding_y = 5
        rect_width = text_width + padding_x*2
        rect_height = text_height + padding_y*2
        y_add = self.top_margin + len(self.tracks)*self.track_height + 10
        painter.setBrush(self.add_button_color)
        painter.setPen(Qt.NoPen)
        painter.drawRect(5, y_add, rect_width, rect_height)
        painter.setPen(self.button_text_color)
        painter.drawText(5 + padding_x, y_add + padding_y + metrics.ascent(), text)

    # ---------- Mouse ----------
    def mousePressEvent(self,event):
        frame_clicked=int(round((event.x()-self.left_margin+self.scroll_x)/self.frame_width))
        track_index=int((event.y()-self.top_margin)/self.track_height)

        # + button
        metrics = self.fontMetrics()
        text = "+ Add Track"
        text_width = metrics.width(text)
        text_height = metrics.height()
        padding_x = 10
        padding_y = 5
        rect_width = text_width + padding_x*2
        rect_height = text_height + padding_y*2
        y_add = self.top_margin + len(self.tracks)*self.track_height + 10
        if y_add<=event.y()<=y_add+rect_height and 5<=event.x()<=5+rect_width:
            self.add_track()
            return

        # - buttons & track dropdown
        for i,track in enumerate(self.tracks):
            y=self.top_margin+i*self.track_height
            button_size = self.track_height//2
            button_margin = 5
            if y + (self.track_height-button_size)//2 <= event.y() <= y + (self.track_height+button_size)//2 and button_margin <= event.x() <= button_margin + button_size:
                self.tracks.pop(i)
                self.update_scrollbar()
                self.update()
                return
            if y<=event.y()<=y+self.track_height and 35<=event.x()<=self.left_margin-5:
                self.show_track_name_menu(track,event.globalPos())
                return

        # Keyframes
        if 0<=track_index<len(self.tracks):
            track=self.tracks[track_index]
            clicked_kf=None
            for kf in track.keyframes:
                kf_x=self.left_margin+kf.frame*self.frame_width-self.scroll_x
                y_dot=self.top_margin+track_index*self.track_height+self.track_height//2
                if abs(kf_x-event.x())<=self.keyframe_size//2 and abs(y_dot-event.y())<=self.keyframe_size//2:
                    clicked_kf=kf
                    break

            if event.button()==Qt.RightButton and clicked_kf:
                self.show_easing_menu(track,clicked_kf,event.globalPos())
                return
            elif event.button()==Qt.LeftButton:
                if event.modifiers() & Qt.ControlModifier and clicked_kf:
                    if clicked_kf not in self.selected_keyframes:
                        self.selected_keyframes.append(clicked_kf)
                    else:
                        self.selected_keyframes.remove(clicked_kf)
                    self.update()
                    return
                elif event.modifiers() & Qt.ShiftModifier and clicked_kf:
                    if self.selected_keyframes:
                        last = self.selected_keyframes[-1]
                        frames = [kf for kf in track.keyframes if min(last.frame,clicked_kf.frame)<=kf.frame<=max(last.frame,clicked_kf.frame)]
                        for kf in frames:
                            if kf not in self.selected_keyframes:
                                self.selected_keyframes.append(kf)
                    else:
                        self.selected_keyframes.append(clicked_kf)
                    self.update()
                    return
                elif clicked_kf:
                    if clicked_kf not in self.selected_keyframes:
                        self.selected_keyframes = [clicked_kf]
                    self.selected_keyframe = clicked_kf
                    self.drag_offset = frame_clicked - clicked_kf.frame
                    return
                else:
                    self.current_frame = frame_clicked
                    self.update()
                    return

            if event.modifiers() & Qt.ShiftModifier and clicked_kf is None:
                self.selected_keyframes.clear()
                self.update()

    def mouseMoveEvent(self,event):
        if self.selected_keyframes and self.selected_keyframe:
            frame=int(round((event.x()-self.left_margin+self.scroll_x)/self.frame_width - self.drag_offset))
            frame=max(0,frame)
            delta = frame - self.selected_keyframe.frame
            for kf in self.selected_keyframes:
                kf.frame = max(0,kf.frame+delta)
            self.update_scrollbar()
            self.update()

    def mouseReleaseEvent(self,event):
        self.selected_keyframe=None

    def keyPressEvent(self,event: QKeyEvent):
        if event.key()==Qt.Key_Delete:
            for track in self.tracks:
                track.keyframes = [kf for kf in track.keyframes if kf not in self.selected_keyframes]
            self.selected_keyframes.clear()
            self.update_scrollbar()
            self.update()

    def wheelEvent(self,event):
        if event.modifiers() & Qt.ControlModifier:
            old_width=self.frame_width
            delta=event.angleDelta().y()/120
            self.frame_width+=delta*2
            self.frame_width=max(self.min_frame_width,min(self.frame_width,self.max_frame_width))
            mouse_frame=int(round((event.x()-self.left_margin+self.scroll_x)/old_width))
            self.scroll_x=int(mouse_frame*self.frame_width-(event.x()-self.left_margin))
            self.scroll_x=max(0,min(self.scroll_x,self.scrollbar.maximum()))
            self.update_scrollbar()
            self.update()

    # ---------- Track Management ----------
    def add_track(self,name=None):
        name=name or self.allowed_track_names[0]
        self.tracks.append(Track(name))
        self.update_scrollbar()
        self.update()

    def show_track_name_menu(self,track,pos):
        menu=QMenu()
        for name in self.allowed_track_names:
            action=menu.addAction(name)
            action.triggered.connect(lambda checked,n=name,t=track: self.set_track_name(t,n))
        menu.exec(pos)

    def set_track_name(self,track,name):
        track.name=name
        self.update()

    # ---------- Easing Menu ----------
    def show_easing_menu(self,track,keyframe,pos):
        menu=QMenu()
        for easing in ['Linear','EaseIn','EaseOut','EaseInOut']:
            action=menu.addAction(easing)
            action.triggered.connect(lambda checked,k=keyframe,e=easing:self.set_easing(k,e))
        menu.exec(pos)

    def set_easing(self,keyframe,easing):
        keyframe.easing=easing
        self.update()


# ---------- Example ----------
if __name__=="__main__":
    import sys
    app=QApplication(sys.argv)
    timeline=TimelineWidget()
    timeline.allowed_track_names=["Location X","Location Y","Rotation Z","Scale"]

    timeline.add_track("Location X")
    timeline.add_track("Rotation Z")
    timeline.tracks[0].color=QColor(255,100,100)
    timeline.tracks[1].color=QColor(100,255,100)

    for f in [50,400,900,1500]:
        timeline.tracks[0].add_keyframe(f)
    for f in [100,1200,1700]:
        timeline.tracks[1].add_keyframe(f)

    main=QWidget()
    layout=QVBoxLayout(main)
    layout.addWidget(timeline)
    main.resize(1200,400)
    main.show()
    sys.exit(app.exec())
