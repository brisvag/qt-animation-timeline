"""Interactive demo of AnimationTimelineWidget with debug output.

Run with::

    python examples/demo.py

Or from IPython (non-blocking, allows modifying settings interactively)::

    %run examples/demo.py

The demo creates a ``Scene`` model whose fields are bound to four tracks.
Moving the playhead prints the current field values to stdout.
Requires NumPy (``pip install numpy``).
"""

from __future__ import annotations

import sys

import numpy as np
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from qt_animation_editor.easing import EasingFunction
from qt_animation_editor.editor import AnimationTimelineWidget


class Scene:
    """Toy model whose fields are animated by the timeline."""

    def __init__(self) -> None:
        self.x: float = 0.0
        self.y: float = 0.0
        self.visible: bool = True
        self.angles: np.ndarray = np.array([0.0, 0.0, 0.0])


def build_demo() -> tuple[QWidget, AnimationTimelineWidget, Scene]:
    """Build and return the demo widget without starting the event loop."""
    scene = Scene()

    timeline = AnimationTimelineWidget(
        track_options={
            "x": (scene, "x"),
            "y": (scene, "y"),
            "visible": (scene, "visible"),
            "angles": (scene, "angles"),
        }
    )

    # Add tracks pre-bound to the model fields.
    timeline.add_track("x")
    timeline.add_track("y")
    timeline.add_track("visible")
    timeline.add_track("angles")

    # "x" starts at frame 20 (not 0) to demonstrate non-zero origins.
    timeline.tracks[0].add_keyframe(20, value=50.0)
    timeline.tracks[0].add_keyframe(100, value=200.0)
    timeline.tracks[0].add_keyframe(200, value=50.0)

    timeline.tracks[1].add_keyframe(0, value=0.0)
    timeline.tracks[1].add_keyframe(150, value=100.0, easing=EasingFunction.Step)
    timeline.tracks[1].add_keyframe(300, value=0.0)

    # "visible" uses actual bool values so Step easing works type-safely.
    timeline.tracks[2].add_keyframe(0, value=True, easing=EasingFunction.Step)
    timeline.tracks[2].add_keyframe(120, value=False)
    timeline.tracks[2].add_keyframe(240, value=True)

    # "angles" is a numpy array — Linear easing works element-wise.
    timeline.tracks[3].add_keyframe(50, value=np.array([0.0, 0.0, 0.0]))
    timeline.tracks[3].add_keyframe(150, value=np.array([45.0, 90.0, 180.0]))
    timeline.tracks[3].add_keyframe(280, value=np.array([10.0, 20.0, 30.0]))

    info_label = QLabel("Move the playhead to see values")
    info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _on_playhead(frame: int) -> None:
        angles_str = "[" + ", ".join(f"{a:.1f}" for a in scene.angles) + "]"
        msg = (
            f"frame={frame:4d}  "
            f"x={scene.x:8.2f}  "
            f"y={scene.y:8.2f}  "
            f"visible={scene.visible!s:<5}  "
            f"angles={angles_str}"
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

    return main_widget, timeline, scene


def main() -> None:
    """Run the demo application."""
    app = QApplication.instance() or QApplication(sys.argv)

    main_widget, timeline, scene = build_demo()

    # When running from IPython with %gui qt the event loop is already
    # running, so app.exec() would block.  Detect this by checking whether
    # IPython has an active GUI event loop registered.
    in_ipython_loop = False
    try:
        from IPython import get_ipython

        ip = get_ipython()
        in_ipython_loop = ip is not None and getattr(ip, "active_eventloop", None) is not None
    except ImportError:
        pass

    if not in_ipython_loop:
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
