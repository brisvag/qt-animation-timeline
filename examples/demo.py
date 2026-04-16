"""Interactive demo of AnimationTimelineWidget.

Run with::

    python examples/demo.py

Requires NumPy and pydantic (``pip install numpy pydantic``).
"""

from __future__ import annotations

import sys

from psygnal import EventedModel
from qtpy.QtWidgets import QApplication

from qt_animation_timeline import AnimationTimeline, AnimationTimelineWidget
from qt_animation_timeline.easing import EasingFunction


class Camera:
    """Camera: 2-D position and zoom level."""

    def __init__(self) -> None:
        self.x: float = 0.0
        self.y: float = 0.0
        self.zoom: float = 1.0

    def __str__(self) -> str:
        """Print out camera info."""
        return f"Camera(x={self.x}, y={self.y}, zoom={self.zoom})"


class Angles(EventedModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class Light(EventedModel):
    """Light model: intensity and Euler rotation angles."""

    intensity: float = 1.0
    angles: Angles = Angles()


camera = Camera()

light = Light()

animation = AnimationTimeline(
    track_options={
        "cam_x": (camera, "x"),
        "cam_y": (camera, "y"),
        "cam_zoom": (camera, "zoom"),
        # note that light is a whole model itself!
        "light": (light, ""),
    }
)

cam_x = animation.add_track("cam_x")
cam_y = animation.add_track("cam_y")
cam_zoom = animation.add_track("cam_zoom")
light = animation.add_track("light")

cam_x.add_keyframe(20, value=50.0)
cam_x.add_keyframe(100, value=200.0)
cam_x.add_keyframe(200, value=50.0)

cam_y.add_keyframe(0, value=0.0)
cam_y.add_keyframe(150, value=100.0, easing=EasingFunction.Step)
cam_y.add_keyframe(300, value=0.0)

# Camera.zoom
cam_zoom.add_keyframe(0, value=1.0)
cam_zoom.add_keyframe(100, value=2.5)
cam_zoom.add_keyframe(200, value=1.0)

# Light — whole pydantic model; each field is interpolated independently.
light.add_keyframe(0, value=Light(intensity=0.5, angles=Angles(x=0.0, y=0.0, z=0.0)))
light.add_keyframe(
    150,
    value=Light(intensity=0.2, angles=Angles(x=45.0, y=90.0, z=0.0)),
    easing=EasingFunction.Step,
)
light.add_keyframe(
    300, value=Light(intensity=0.8, angles=Angles(x=10.0, y=20.0, z=30.0))
)


def _print_state() -> None:
    frame = animation.current_frame
    print(f"{frame=}\n{camera=}\n{light=}")


animation.events.connect(_print_state)
animation.track_removed.connect(_print_state)
animation.keyframes_added.connect(_print_state)
animation.keyframes_removed.connect(_print_state)
animation.keyframes_moved.connect(_print_state)
animation.easing_changed.connect(_print_state)


def spawn_widget():
    """Spawn the timeline widget."""
    app = QApplication(sys.argv)
    # set up the widget
    timeline = AnimationTimelineWidget(animation=animation)

    timeline.resize(1200, 200)
    timeline.setWindowTitle("AnimationTimelineWidget - demo (Camera + Light)")
    timeline.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    spawn_widget()
