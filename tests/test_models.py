import pytest
from pydantic import BaseModel

from qt_animation_timeline.easing import EasingFunction
from qt_animation_timeline.models import (
    AnimationTimeline,
    Keyframe,
    PlayMode,
    Track,
)


@pytest.fixture(scope="function")
def animation():
    animation = AnimationTimeline()

    class MyModel(BaseModel):
        x: int = 1

    animation.track_options = {"A": (MyModel(), "x")}
    return animation


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
    assert [k.t for k in t.keyframes] == [5, 10, 30]


def test_add_track(animation):
    animation.track_options = {"A": (None, "")}
    received = []
    animation.track_added.connect(received.append)
    track = animation.add_track("A")
    assert isinstance(track, Track)
    assert track.name == "A"
    assert animation.tracks.get("A") is track
    assert received == [track]


def test_play_normal_stops_at_last_keyframe(animation):
    animation.add_track("A")
    animation.tracks["A"].add_keyframe(0, value=0.0)
    animation.tracks["A"].add_keyframe(5, value=1.0)
    animation.play_mode = PlayMode.NORMAL
    iterator = animation.iter_frames()
    for i in range(5 + 1):
        assert next(iterator) == i
    with pytest.raises(StopIteration):
        next(iterator)


def test_play_loop_wraps(animation):
    animation.add_track("A")
    animation.tracks["A"].add_keyframe(0, value=0.0)
    animation.tracks["A"].add_keyframe(5, value=1.0)
    animation.play_mode = PlayMode.LOOP
    iterator = animation.iter_frames()
    for i in range(5 + 1):
        assert next(iterator) == i
    for i in range(5 + 1):
        assert next(iterator) == i


def test_play_pingpong_reverses(animation):
    animation.add_track("A")
    animation.tracks["A"].add_keyframe(0, value=0.0)
    animation.tracks["A"].add_keyframe(5, value=1.0)
    animation.play_mode = PlayMode.PINGPONG
    iterator = animation.iter_frames()
    for i in range(5 + 1):
        assert next(iterator) == i
    for i in range(1, 5):
        assert next(iterator) == 5 - i
