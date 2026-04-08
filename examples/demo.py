"""Interactive demo of AnimationTimelineWidget with debug output.

Run with::

    python examples/demo.py

The demo creates a simple ``Scene`` model whose fields are bound to three
tracks.  Moving the playhead prints the current field values to stdout.
"""

from __future__ import annotations

import sys

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from qt_animation_editor.editor import AnimationTimelineWidget, EasingFunction


class Scene:
    """Toy model whose fields are animated by the timeline."""

    def __init__(self) -> None:
        self.x: float = 0.0
        self.y: float = 0.0
        self.visible: bool = True


def main() -> None:
    """Run the demo application."""
    app = QApplication(sys.argv)

    scene = Scene()

    timeline = AnimationTimelineWidget()
    timeline.track_options = {
        "x": (scene, "x"),
        "y": (scene, "y"),
        "visible": (scene, "visible"),
    }

    # Add tracks pre-bound to the model fields.
    timeline.add_track("x")
    timeline.add_track("y")
    timeline.add_track("visible")

    # Keyframe values are set explicitly here; in real usage double-clicking
    # captures the live field value from the model.
    timeline.tracks[0].add_keyframe(0, value=0.0)
    timeline.tracks[0].add_keyframe(100, value=200.0)
    timeline.tracks[0].add_keyframe(200, value=50.0)

    timeline.tracks[1].add_keyframe(0, value=0.0)
    timeline.tracks[1].add_keyframe(150, value=100.0, easing=EasingFunction.Bool)
    timeline.tracks[1].add_keyframe(300, value=0.0)

    timeline.tracks[2].add_keyframe(0, value=1.0, easing=EasingFunction.Bool)
    timeline.tracks[2].add_keyframe(120, value=0.0)
    timeline.tracks[2].add_keyframe(240, value=1.0)

    info_label = QLabel("Move the playhead to see values")
    info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _on_playhead(frame: int) -> None:
        msg = (
            f"frame={frame:4d}  "
            f"x={scene.x:8.2f}  "
            f"y={scene.y:8.2f}  "
            f"visible={scene.visible}"
        )
        print(msg)
        info_label.setText(msg)

    timeline.playhead_moved.connect(_on_playhead)

    main_widget = QWidget()
    layout = QVBoxLayout(main_widget)
    layout.addWidget(timeline)
    layout.addWidget(info_label)
    main_widget.resize(1200, 450)
    main_widget.setWindowTitle("AnimationTimelineWidget - demo")
    main_widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
