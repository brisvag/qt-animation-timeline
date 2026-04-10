import pytest

from qt_animation_timeline.easing import EasingFunction
from qt_animation_timeline.models import (
    Animation,
    Keyframe,
    Track,
)


def test_keyframe():
    kf = Keyframe(t=10)
    assert kf.t == 10
    assert kf.easing is EasingFunction.Linear
    kf = Keyframe(easing=EasingFunction.Step)
    assert kf.easing is EasingFunction.Step


def test_track():
    t = Track(name="X")
    kf = t.add_keyframe(10)
    assert kf.t == 10 and kf in t.keyframes
    with pytest.raises(KeyError):
        t.add_keyframe(10)
    t.add_keyframe(30)
    t.add_keyframe(5)
    assert [k.t for k in t.keyframes_sorted()] == [5, 10, 30]


def test_add_track():
    a = Animation()
    a.track_options = {"A": (None, "")}
    received = []
    a.track_added.connect(received.append)
    track = a.add_track("A")
    assert isinstance(track, Track)
    assert track.name == "A"
    assert track in a.tracks
    assert received == [track]
