import qt_animation_editor


def test_imports_with_version():
    assert isinstance(qt_animation_editor.__version__, str)
