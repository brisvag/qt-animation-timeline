"""Interactive demo of AnimationTimelineWidget.

Run with::

    python examples/demo.py

Requires NumPy and pydantic (``pip install numpy pydantic``).
"""

from __future__ import annotations

import sys

from psygnal import EventedModel
from qtpy.QtWidgets import QApplication

from qt_animation_timeline.easing import EasingFunction
from qt_animation_timeline.qt_timeline import AnimationTimelineWidget


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


def main() -> None:
    """Run the demo application."""
    app = QApplication(sys.argv)

    camera = Camera()

    light = Light()

    timeline = AnimationTimelineWidget(
        track_options={
            "cam_x": (camera, "x"),
            "cam_y": (camera, "y"),
            "cam_zoom": (camera, "zoom"),
            # note that angles is a whole model itself!
            "light_angles": (light, "angles"),
        }
    )

    timeline.add_track("cam_x")
    timeline.add_track("cam_y")
    timeline.add_track("cam_zoom")
    timeline.add_track("light_angles")

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
    timeline.animation.tracks[3].add_keyframe(0, value=Angles(x=0.0, y=0.0, z=0.0))
    timeline.animation.tracks[3].add_keyframe(
        150,
        value=Angles(x=45.0, y=90.0, z=0.0),
        easing=EasingFunction.Step,
    )
    timeline.animation.tracks[3].add_keyframe(300, value=Angles(x=10.0, y=20.0, z=30.0))

    def _print_state() -> None:
        frame = timeline.animation.current_frame
        print(f"{frame=}\n{camera=}\n{light=}")

    timeline.animation.events.connect(_print_state)

    timeline.resize(1200, 200)
    timeline.setWindowTitle("AnimationTimelineWidget - demo (Camera + Light)")
    timeline.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
