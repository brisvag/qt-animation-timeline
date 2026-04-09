"""Interactive demo of AnimationTimelineWidget.

Run with::

    python examples/demo.py

Requires NumPy and pydantic (``pip install numpy pydantic``).
"""

from __future__ import annotations

import sys

from pydantic import BaseModel
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from qt_animation_timeline.easing import EasingFunction
from qt_animation_timeline.editor import AnimationTimelineWidget


class Camera:
    """Camera model: 2-D position and zoom level."""

    def __init__(self) -> None:
        self.x: float = 0.0
        self.y: float = 0.0
        self.zoom: float = 1.0


class Light(BaseModel):
    """Light model: intensity and Euler rotation angles."""

    intensity: float = 1.0
    angle_x: float = 0.0
    angle_y: float = 0.0
    angle_z: float = 0.0


def main() -> None:
    """Run the demo application."""
    app = QApplication(sys.argv)

    camera = Camera()

    # Light is a pydantic model; it is passed as a whole model binding.
    class _LightHolder:
        light = Light()

    holder = _LightHolder()

    timeline = AnimationTimelineWidget(
        track_options={
            "cam_x": (camera, "x"),
            "cam_y": (camera, "y"),
            "cam_zoom": (camera, "zoom"),
            "light": (holder, "light"),
        }
    )

    timeline.add_track("cam_x")
    timeline.add_track("cam_y")
    timeline.add_track("cam_zoom")
    timeline.add_track("light")

    # Camera.x - starts at frame 20 to demonstrate non-zero origins.
    timeline.animation.tracks[0].add_keyframe(20, value=50.0)
    timeline.animation.tracks[0].add_keyframe(100, value=200.0)
    timeline.animation.tracks[0].add_keyframe(200, value=50.0)

    # Camera.y
    timeline.animation.tracks[1].add_keyframe(0, value=0.0)
    timeline.animation.tracks[1].add_keyframe(
        150, value=100.0, easing=EasingFunction.Step
    )
    timeline.animation.tracks[1].add_keyframe(300, value=0.0)

    # Camera.zoom
    timeline.animation.tracks[2].add_keyframe(0, value=1.0)
    timeline.animation.tracks[2].add_keyframe(100, value=2.5)
    timeline.animation.tracks[2].add_keyframe(200, value=1.0)

    # Light — whole pydantic model; each field is interpolated independently.
    timeline.animation.tracks[3].add_keyframe(
        0, value=Light(intensity=1.0, angle_x=0.0, angle_y=0.0, angle_z=0.0)
    )
    timeline.animation.tracks[3].add_keyframe(
        150,
        value=Light(intensity=0.2, angle_x=45.0, angle_y=90.0, angle_z=0.0),
        easing=EasingFunction.Step,
    )
    timeline.animation.tracks[3].add_keyframe(
        300, value=Light(intensity=1.0, angle_x=10.0, angle_y=20.0, angle_z=30.0)
    )

    info_label = QLabel(
        "Move the playhead, reposition a keyframe, or change an easing to see values"
    )
    info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _print_state(reason: str) -> None:
        frame = timeline.animation.current_frame
        light = holder.light
        msg = (
            f"[{reason}] frame={frame:4d}  |  "
            f"Camera: x={camera.x:8.2f}  y={camera.y:8.2f}  zoom={camera.zoom:.2f}  |  "
            f"Light: intensity={light.intensity:.2f}  "
            f"angles=({light.angle_x:.1f}, {light.angle_y:.1f}, {light.angle_z:.1f})"
        )
        print(msg)
        info_label.setText(msg)

    timeline.playhead_moved.connect(lambda _: _print_state("playhead"))
    timeline.keyframes_moved.connect(lambda _: _print_state("keyframe moved"))
    timeline.easing_changed.connect(lambda _: _print_state("easing changed"))
    timeline.keyframe_added.connect(lambda t, kf: _print_state("keyframe added"))

    main_widget = QWidget()
    layout = QVBoxLayout(main_widget)
    layout.addWidget(timeline)
    layout.addWidget(info_label)
    main_widget.resize(1200, 500)
    main_widget.setWindowTitle("AnimationTimelineWidget - demo (Camera + Light)")
    main_widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
