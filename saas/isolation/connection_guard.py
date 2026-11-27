"""SaaS: don't move or delete the object-storage connection while generation tasks are queued or running.

A task that started with the old connection fails its formal commit when the connection changes
(``RemoteSaveFailedError("connection_changed")``) and the paid result is lost. Updating only the
access keys stays allowed. Self-hosted: unchanged.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from saas.adapter.mode import is_saas


async def ensure_no_active_tasks(session: AsyncSession) -> None:
    if not is_saas():
        return
    from lib.db.models.task import Task
    from lib.infra.api_errors import ConflictError

    count = int(
        (await session.execute(select(func.count()).select_from(Task).where(Task.status.in_(("queued", "running")))))
        .scalar_one()
    )
    if count:
        raise ConflictError("object_storage_tasks_running", count=count)
