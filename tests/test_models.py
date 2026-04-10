import pytest
from pydantic import BaseModel

from qt_animation_timeline.easing import EasingFunction
from qt_animation_timeline.models import (
    Animation,
    Keyframe,
    PlayMode,
    Track,
)


@pytest.fixture(scope="function")
def animation():
    animation = Animation()

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
    assert [k.t for k in t.keyframes_sorted()] == [5, 10, 30]


def test_add_track(animation):
    animation.track_options = {"A": (None, "")}
    received = []
    animation.track_added.connect(received.append)
    track = animation.add_track("A")
    assert isinstance(track, Track)
    assert track.name == "A"
    assert track in animation.tracks
    assert received == [track]


def test_play_normal_stops_at_last_keyframe(animation):
    animation.add_track("A")
    animation.tracks[0].add_keyframe(0, value=0.0)
    animation.tracks[0].add_keyframe(5, value=1.0)
    animation.play_mode = PlayMode.NORMAL
    animation.playing = True
    animation.current_frame = 5
    animation.advance_playhead()
    assert not animation.playing and animation.current_frame == 5


def test_play_loop_wraps(animation):
    animation.add_track("A")
    animation.tracks[0].add_keyframe(0, value=0.0)
    animation.tracks[0].add_keyframe(5, value=1.0)
    animation.play_mode = PlayMode.LOOP
    animation.current_frame = 5
    animation.advance_playhead()
    assert animation.current_frame == 0


def test_play_pingpong_reverses(animation):
    animation.add_track("A")
    animation.tracks[0].add_keyframe(0, value=0.0)
    animation.tracks[0].add_keyframe(5, value=1.0)
    animation.play_mode = PlayMode.PINGPONG
    animation.play_direction = 1
    animation.current_frame = 5
    animation.advance_playhead()
    assert animation.play_direction == -1
    animation.current_frame = 0
    animation.advance_playhead()
    assert animation.play_direction == 1


def test_play_no_keyframes(animation):
    animation.play_mode = PlayMode.NORMAL
    animation.playing = True
    animation.advance_playhead()
    assert not animation.playing
