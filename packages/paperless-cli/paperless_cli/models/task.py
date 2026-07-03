"""Task models for Paperless-ngx API."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


@dataclass
class Task:
    """Represents a background task in Paperless-ngx."""

    task_id: str
    task_file_name: str | None
    date_created: datetime
    date_done: datetime | None
    type: str
    status: Literal["PENDING", "STARTED", "SUCCESS", "FAILURE", "RETRY", "REVOKED"]
    result: Any | None = None
    acknowledged: bool = False
    related_document: int | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Task":
        """Create a Task instance from API response data."""
        return cls(
            task_id=data["task_id"],
            task_file_name=data.get("task_file_name"),
            date_created=datetime.fromisoformat(data["date_created"].replace("Z", "+00:00")),
            date_done=datetime.fromisoformat(data["date_done"].replace("Z", "+00:00"))
            if data.get("date_done")
            else None,
            type=data["type"],
            status=data["status"],
            result=data.get("result"),
            acknowledged=data.get("acknowledged", False),
            related_document=data.get("related_document"),
        )
