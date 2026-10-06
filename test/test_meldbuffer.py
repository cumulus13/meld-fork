import os

from gi.repository import Gio

from meld.meldbuffer import MeldBufferData, MeldBufferState


def _loaded(path):
    data = MeldBufferData()
    data.reset(Gio.File.new_for_path(str(path)), MeldBufferState.LOAD_FINISHED)
    return data


def test_changed_on_disk_follows_mtime(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("a")
    data = _loaded(path)
    assert not data.changed_on_disk()

    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    assert data.changed_on_disk()

    # Saving or reloading records the new on-disk mtime
    data.update_mtime()
    assert not data.changed_on_disk()


def test_changed_on_disk_without_file(tmp_path):
    assert not MeldBufferData().changed_on_disk()

    path = tmp_path / "gone.txt"
    path.write_text("x")
    data = _loaded(path)
    path.unlink()
    assert not data.changed_on_disk()
