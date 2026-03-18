from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from ..activity_repository import ActivityRepository
from ..domain import ActivityRecord, UserRecord


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class ActivityQuery:
    user_id: str | None
    action_type: str | None
    target_type: str | None
    query: str | None
    date_from: datetime | None
    date_to: datetime | None


class ActivityService:
    def __init__(self, *, repository: ActivityRepository) -> None:
        self._repository = repository

    def log(
        self,
        *,
        user: UserRecord,
        action_type: str,
        target_type: str,
        target_id: str | None,
        description: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self._repository.create(
            ActivityRecord(
                id=str(uuid.uuid4()),
                user_id=user.id,
                username=user.username,
                user_role=user.role,
                action_type=action_type,
                target_type=target_type,
                target_id=target_id,
                description=description,
                metadata=metadata or {},
                created_at=_utc_now(),
            )
        )

    def list_entries(self, query: ActivityQuery) -> list[ActivityRecord]:
        return self._repository.list_entries(
            user_id=query.user_id,
            action_type=query.action_type,
            target_type=query.target_type,
            query=query.query,
            date_from=query.date_from,
            date_to=query.date_to,
        )

    def list_action_types(self) -> list[str]:
        return self._repository.list_distinct_action_types()

    def list_target_types(self) -> list[str]:
        return self._repository.list_distinct_target_types()
