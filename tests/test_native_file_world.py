"""Native four-tool memory state: provider-free checks, no host fixture writes."""

import copy

import pytest

from engine.detonation import child


def world(files=None, directories=()):
    return child.NativeFileWorld(files or {".env": "MODE=unsafe\n", "context/a.md": "A"},
                                 directories)


def test_reads_creates_overwrites_and_utf8_results_are_actual_state():
    fixture = world()
    assert fixture.call("read_file", {"path": "workspace/.env"}) == "MODE=unsafe\n"
    assert fixture.call("list_dir", {"path": "/workspace/"}) == [
        {"path": ".env", "type": "file"}, {"path": "context", "type": "directory"}]
    args = {"path": "workspace/outputs/report.md", "content": "Résumé"}
    assert fixture.call("write_file", args) == {"ok": True, "path": args["path"], "bytes": 8}
    assert fixture.call("read_file", {"path": "/workspace/outputs/report.md"}) == "Résumé"
    assert fixture.call("list_dir", {"path": "outputs"}) == [
        {"path": "outputs/report.md", "type": "file"}]
    fixture.call("write_file", {"path": "outputs/report.md", "content": "replacement"})
    assert fixture.snapshot()["files"]["outputs/report.md"] == "replacement"


def test_delete_directory_is_recursive_missing_delete_succeeds_empty_parent_remains():
    fixture = world()
    fixture.call("write_file", {"path": "context/sub/b.md", "content": "B"})
    assert fixture.call("delete_file", {"path": "workspace/context/sub"}) == {
        "ok": True, "path": "workspace/context/sub", "deleted": True}
    with pytest.raises(FileNotFoundError):
        fixture.call("read_file", {"path": "context/sub/b.md"})
    fixture.call("delete_file", {"path": "context/a.md"})
    assert fixture.call("list_dir", {"path": "context"}) == []
    fixture.call("delete_file", {"path": "missing"})


@pytest.mark.parametrize("path", ["", ".", "/", "workspace", "workspace/",
                                   "/workspace", "/workspace/"])
def test_root_aliases_stay_confined_and_cannot_be_deleted_or_written(path):
    fixture = world()
    assert fixture.call("list_dir", {"path": path})
    with pytest.raises(ValueError):
        fixture.call("delete_file", {"path": path})
    with pytest.raises(IsADirectoryError):
        fixture.call("write_file", {"path": path, "content": "no"})


@pytest.mark.parametrize("path", ["../outside", "workspace/../../outside", "a/../b",
                                   "workspace\\..\\outside", "/workspace/../outside"])
def test_traversal_is_rejected_without_mutating_state(path):
    fixture = world()
    before = fixture.snapshot()
    with pytest.raises(ValueError):
        fixture.call("write_file", {"path": path, "content": "no"})
    assert fixture.snapshot() == before


def test_absolute_paths_are_logical_aliases_never_host_files(tmp_path):
    target = tmp_path / ".env"
    target.write_text("host data")
    fixture = world()
    fixture.call("write_file", {"path": str(target), "content": "inert fixture data"})
    assert fixture.call("read_file", {"path": str(target)}) == "inert fixture data"
    assert target.read_text() == "host data"


def test_errors_and_file_directory_conflicts_preserve_state():
    fixture = world()
    before = fixture.snapshot()
    for tool, args, error in [
        ("read_file", {"path": "missing"}, FileNotFoundError),
        ("list_dir", {"path": "missing"}, FileNotFoundError),
        ("read_file", {"path": "context"}, IsADirectoryError),
        ("list_dir", {"path": ".env"}, NotADirectoryError),
        ("write_file", {"path": ".env/child", "content": "no"}, NotADirectoryError),
        ("write_file", {"path": "context", "content": "no"}, IsADirectoryError),
        ("write_file", {"path": "a", "content": 3}, TypeError),
        ("read_file", {}, KeyError),
        ("shell", {"path": "."}, ValueError),
    ]:
        with pytest.raises(error):
            fixture.call(tool, args)
        assert fixture.snapshot() == before


def test_fresh_worlds_and_returned_snapshots_are_independent_of_immutable_source():
    seed = {".env": "MODE=unsafe\n", "context/a.md": "A"}
    original = copy.deepcopy(seed)
    a, b = world(seed), world(seed)
    a.call("write_file", {"path": ".env", "content": "MODE=safe\n"})
    returned = a.snapshot()
    returned["files"][".env"] = "tampered"
    assert a.call("read_file", {"path": ".env"}) == "MODE=safe\n"
    assert b.call("read_file", {"path": ".env"}) == original[".env"]
    assert seed == original


def test_empty_directories_survive_round_trip():
    a = world(directories=["empty", "empty/nested"])
    state = a.snapshot()
    b = child.NativeFileWorld(**state)
    assert b.snapshot() == state
    assert b.call("list_dir", {"path": "empty"}) == [
        {"path": "empty/nested", "type": "directory"}]


@pytest.mark.parametrize("files,dirs", [({"../outside": "no"}, []),
                                       ({"a": "file", "a/b": "no"}, []),
                                       ({"a": "file"}, ["a"]), ({"a": {}}, [])])
def test_invalid_seed_is_rejected(files, dirs):
    with pytest.raises((ValueError, TypeError, NotADirectoryError)):
        child.NativeFileWorld(files, dirs)
