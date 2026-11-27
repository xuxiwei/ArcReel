"""SaaS: generated video and audio follow images into object storage."""

from contextlib import nullcontext
from pathlib import Path

import pytest

from lib.material.formal_objects import stores_remotely
from lib.object_storage import client as client_module
from lib.object_storage.client import ObjectStorageClient, ObjectStorageConfig
from saas.storage import media_offload


@pytest.fixture
def saas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")


def test_self_hosted_keeps_images_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "self_hosted")
    assert stores_remotely("storyboards")
    assert not stores_remotely("videos")
    assert not stores_remotely("audio")
    assert not media_offload.keeps_local_work_file("videos/scene_1.mp4")
    assert isinstance(media_offload.media_commit_scope("video", "p"), nullcontext)


def test_saas_stores_video_and_audio_remotely(saas) -> None:
    for resource_type in ("storyboards", "characters", "videos", "reference_videos", "audio"):
        assert stores_remotely(resource_type), resource_type
    assert not stores_remotely("unknown")


def test_saas_keeps_media_work_files_local(saas) -> None:
    assert media_offload.keeps_local_work_file("videos/scene_1.mp4")
    assert media_offload.keeps_local_work_file("versions/audio/segment_1_v2_x.WAV")
    assert not media_offload.keeps_local_work_file("storyboards/scene_1.png")


def test_media_tasks_run_inside_formal_commit(saas, monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    seen: list[str] = []

    def fake_formal_commit(project_name: str):
        seen.append(project_name)
        return sentinel

    monkeypatch.setattr("lib.material.formal_objects.formal_commit", fake_formal_commit)
    for task_type in ("video", "reference_video", "tts", "voice_sample"):
        assert media_offload.media_commit_scope(task_type, "proj") is sentinel
    # Image tasks open their own formal commit; they are not wrapped twice.
    for task_type in ("storyboard", "grid", "character", None):
        assert isinstance(media_offload.media_commit_scope(task_type, "proj"), nullcontext)
    assert seen == ["proj"] * 4


def test_generation_dispatch_uses_media_scope() -> None:
    source = (Path(__file__).resolve().parents[3] / "server/services/tasks/generation_tasks.py").read_text(
        encoding="utf-8"
    )
    assert "async with media_commit_scope(task_type, project_name):" in source


def test_put_file_streams_from_disk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict] = []

    class FakeSdk:
        def put_object_from_file(self, **kwargs):
            calls.append(kwargs)
            return type("R", (), {"etag": "E"})()

    monkeypatch.setattr(client_module, "create_sdk_client", lambda config: FakeSdk())
    video = tmp_path / "a.mp4"
    video.write_bytes(b"x" * 10)
    client = ObjectStorageClient(ObjectStorageConfig("oss", "cn-hangzhou", "oss-cn-hangzhou.aliyuncs.com", "b", "a", "s"))
    assert client.put_file_sync("k.mp4", video, content_type="video/mp4") == "E"
    assert calls == [{"bucket": "b", "key": "k.mp4", "file_path": str(video), "content_type": "video/mp4"}]
    assert media_offload.media_content_type(".MP4") == "video/mp4"
