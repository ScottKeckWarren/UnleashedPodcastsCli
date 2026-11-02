"""The tasks resource, per the v1 API contract.

A task is owned by and assigned to the caller. It may hang off an episode. The routes
need the tasks:read and tasks:write abilities, or answer 403.
"""

from __future__ import annotations

from unleashed.manifest import Field, FieldType, Filter, Resource

TASK_STATUSES = ("todo", "in_progress", "completed", "cancelled")

TASKS = Resource(
    name="tasks",
    fields=(
        Field("uuid", read_only=True, help="Assigned by the API."),
        Field("title", required_on_create=True, help="At most 255 characters."),
        Field("description", nullable=True),
        Field("status", enum=TASK_STATUSES, help="Defaults to todo."),
        Field("due_date", type=FieldType.DATE, nullable=True, help="YYYY-MM-DD."),
        Field("episode_uuid", nullable=True, help="The episode this task belongs to."),
        Field("created_at", read_only=True),
        Field("updated_at", read_only=True),
    ),
    filters=(
        Filter("status", enum=TASK_STATUSES),
        Filter("episode_uuid"),
        Filter("title", help="Partial match."),
    ),
    sorts=("due_date", "created_at", "updated_at", "title"),
)
