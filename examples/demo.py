"""Interactive demo of AnimationTimelineWidget with two models and debug output.

Run with::

    python examples/demo.py

The demo creates a ``Camera`` model and a ``Light`` model, each bound to a set
of tracks.  Moving the playhead, changing an easing function, or repositioning
a keyframe all print the current field values for both models to stdout so it
is immediately clear what caused each update.
Requires NumPy (``pip install numpy``).
"""

from __future__ import annotations

import sys

import numpy as np
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


class Light:
    """Light model: intensity and Euler rotation angles."""

    def __init__(self) -> None:
        self.intensity: float = 1.0
        self.angles: np.ndarray = np.array([0.0, 0.0, 0.0])


def build_demo() -> tuple[QWidget, AnimationTimelineWidget, Camera, Light]:
    """Build and return the demo widget without starting the event loop."""
    camera = Camera()
    light = Light()

    timeline = AnimationTimelineWidget(
        track_options={
            "cam_x": (camera, "x"),
            "cam_y": (camera, "y"),
            "cam_zoom": (camera, "zoom"),
            "light_intensity": (light, "intensity"),
            "light_angles": (light, "angles"),
        }
    )

    timeline.add_track("cam_x")
    timeline.add_track("cam_y")
    timeline.add_track("cam_zoom")
    timeline.add_track("light_intensity")
    timeline.add_track("light_angles")

    # Camera.x - starts at frame 20 to demonstrate non-zero origins.
    timeline.tracks[0].add_keyframe(20, value=50.0)
    timeline.tracks[0].add_keyframe(100, value=200.0)
    timeline.tracks[0].add_keyframe(200, value=50.0)

    # Camera.y
    timeline.tracks[1].add_keyframe(0, value=0.0)
    timeline.tracks[1].add_keyframe(150, value=100.0, easing=EasingFunction.Step)
    timeline.tracks[1].add_keyframe(300, value=0.0)

    # Camera.zoom
    timeline.tracks[2].add_keyframe(0, value=1.0)
    timeline.tracks[2].add_keyframe(100, value=2.5)
    timeline.tracks[2].add_keyframe(200, value=1.0)

    # Light.intensity
    timeline.tracks[3].add_keyframe(0, value=1.0)
    timeline.tracks[3].add_keyframe(150, value=0.2, easing=EasingFunction.Step)
    timeline.tracks[3].add_keyframe(300, value=1.0)

    # Light.angles - numpy array; Linear easing works element-wise.
    timeline.tracks[4].add_keyframe(50, value=np.array([0.0, 0.0, 0.0]))
    timeline.tracks[4].add_keyframe(150, value=np.array([45.0, 90.0, 180.0]))
    timeline.tracks[4].add_keyframe(280, value=np.array([10.0, 20.0, 30.0]))

    info_label = QLabel("Move the playhead, reposition a keyframe, or change an easing to see values")
    info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _print_state(reason: str) -> None:
        frame = timeline.current_frame
        angles_str = "[" + ", ".join(f"{a:.1f}" for a in light.angles) + "]"
        msg = (
            f"[{reason}] frame={frame:4d}  |  "
            f"Camera: x={camera.x:8.2f}  y={camera.y:8.2f}  zoom={camera.zoom:.2f}  |  "
            f"Light: intensity={light.intensity:.2f}  angles={angles_str}"
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

    return main_widget, timeline, camera, light


def main() -> None:
    """Run the demo application."""
    app = QApplication(sys.argv)
    _widget, _timeline, _camera, _light = build_demo()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
