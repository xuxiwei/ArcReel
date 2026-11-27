"""SaaS: generated video and audio are saved to object storage too, not only images.

Upstream stores only image content versions remotely (``stores_remotely`` → ``.png``) and only
image commits run inside :func:`lib.material.formal_objects.formal_commit`. In SaaS:

- :func:`stores_media_remotely` extends ``stores_remotely`` to video (``.mp4``) and audio (``.wav``);
- :func:`media_commit_scope` wraps video / reference-video / TTS / voice-sample task execution in
  ``formal_commit`` so their version commits go through the same object registration, reference
  counting, settlement and recovery as images;
- :func:`keeps_local_work_file` keeps the local copy of video/audio work files: several consumers
  (final cut, timeline render, Jianying export, thumbnails) read them straight from disk without
  fetching from object storage, so the idle-cache cleanup must not evict them. Object storage holds
  the durable copy and serves downloads.

Everything follows the existing global setting: with "new content target" = local nothing changes.
Self-hosted mode is unchanged.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext
from pathlib import PurePath
from typing import Any

from saas.adapter.mode import is_saas

MEDIA_CONTENT_TYPES = {".mp4": "video/mp4", ".wav": "audio/wav", ".mp3": "audio/mpeg"}
MEDIA_TASK_TYPES = frozenset({"video", "reference_video", "tts", "voice_sample"})


def stores_media_remotely(extension: str) -> bool:
    return is_saas() and extension.lower() in MEDIA_CONTENT_TYPES


def is_media_suffix(suffix: str) -> bool:
    return suffix.lower() in MEDIA_CONTENT_TYPES


def media_content_type(suffix: str) -> str | None:
    return MEDIA_CONTENT_TYPES.get(suffix.lower())


def keeps_local_work_file(relative_path: str) -> bool:
    return is_saas() and is_media_suffix(PurePath(relative_path).suffix)


def media_commit_scope(task_type: str | None, project_name: str) -> AbstractAsyncContextManager[Any]:
    if not is_saas() or task_type not in MEDIA_TASK_TYPES:
        return nullcontext()
    from lib.material.formal_objects import formal_commit

    return formal_commit(project_name)
