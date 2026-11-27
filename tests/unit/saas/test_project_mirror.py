"""SaaS: project files are mirrored to object storage by path-derived keys."""

import json
import os
import time
from pathlib import Path

import pytest

from lib.object_storage.client import ObjectInfo, ObjectStorageError
from saas.storage import project_mirror as pm


class FakeClient:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.fail = False

    def put_file_sync(self, key, path, *, content_type=None):
        if self.fail:
            raise ObjectStorageError("network")
        self.objects[key] = Path(path).read_bytes()
        return "E"

    def head_sync(self, key):
        return ObjectInfo(size=len(self.objects[key]), etag="E", content_type=None)

    def delete_sync(self, key):
        self.deleted.append(key)
        self.objects.pop(key, None)


def _project(root: Path, org="orga", name="demo") -> Path:
    path = root / "projects" / "org" / org / name
    (path / "source").mkdir(parents=True)
    (path / "project.json").write_text("{}", encoding="utf-8")
    return path


def _age(path: Path, seconds: float = 120) -> None:
    old = time.time() - seconds
    os.utime(path, (old, old))


@pytest.fixture
def setup(tmp_path: Path):
    project = _project(tmp_path)
    novel = project / "source" / "小说.txt"
    novel.write_text("第一章", encoding="utf-8")
    (project / ".claude").mkdir()
    (project / ".claude" / "secret.json").write_text("{}", encoding="utf-8")
    (project / "output").mkdir()
    (project / "output" / "final.mp4.part").write_bytes(b"x")
    for p in (novel, project / "project.json"):
        _age(p)
    client = FakeClient()
    return tmp_path, project, novel, client, pm.MirrorTarget(7, "media", client)


def _sync(root, project, target, now=None):
    return pm.sync_project(root, "orga", project, project.name, target, pm._Budget(), now=now)


def test_uploads_new_files_once_and_skips_hidden_and_partial(setup) -> None:
    root, project, novel, client, target = setup
    assert _sync(root, project, target)["uploaded"] == 2
    assert set(client.objects) == {
        "arcreel-files/org/orga/demo/source/小说.txt",
        "arcreel-files/org/orga/demo/project.json",
    }
    assert _sync(root, project, target)["uploaded"] == 0
    entry = pm.mirrored_object(root, "orga", project, "source/小说.txt")
    assert entry and entry["key"].endswith("source/小说.txt")


def test_fresh_files_wait_until_stable_and_changes_reupload(setup) -> None:
    root, project, novel, client, target = setup
    _sync(root, project, target)
    novel.write_bytes("第一章\n第二章".encode())  # just written: not stable yet (bytes: no CRLF on Windows)
    assert pm.mirrored_object(root, "orga", project, "source/小说.txt") is None
    assert _sync(root, project, target)["uploaded"] == 0
    _age(novel)
    assert _sync(root, project, target)["uploaded"] == 1
    assert client.objects["arcreel-files/org/orga/demo/source/小说.txt"] == "第一章\n第二章".encode()


def test_missing_files_are_deleted_after_grace(setup) -> None:
    root, project, novel, client, target = setup
    _sync(root, project, target)
    novel.unlink()
    now = time.time()
    assert _sync(root, project, target, now=now)["deleted"] == 0
    assert _sync(root, project, target, now=now + pm.MISSING_GRACE_SECONDS + 1)["deleted"] == 1
    assert client.deleted == ["arcreel-files/org/orga/demo/source/小说.txt"]


def test_failed_upload_is_retried(setup) -> None:
    root, project, novel, client, target = setup
    client.fail = True
    assert _sync(root, project, target)["failed"] == 2
    client.fail = False
    assert _sync(root, project, target)["uploaded"] == 2


def test_keys_cannot_escape_the_project() -> None:
    with pytest.raises(ValueError):
        pm.mirror_key("orga", "demo", "../other/x")


def test_new_bucket_reuploads(setup) -> None:
    root, project, novel, client, target = setup
    _sync(root, project, target)
    other = pm.MirrorTarget(8, "media2", FakeClient())
    assert _sync(root, project, other)["uploaded"] == 2


def test_iter_projects_lists_org_projects(setup) -> None:
    root, project, *_ = setup
    assert pm.iter_projects(root) == [("orga", project)]
