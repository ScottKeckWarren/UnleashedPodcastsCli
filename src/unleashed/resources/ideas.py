"""The ideas resource, per the v1 API contract.

An idea is a backlog entry for a future episode. The podcast is optional — an idea
without one sits in the general backlog. Status and the converted episode are only
accepted on update, and the API accepts a converted episode only alongside the
status "converted".
"""

from __future__ import annotations

from unleashed.manifest import Field, FieldType, Filter, Resource

IDEA_STATUSES = ("open", "converted", "rejected")

IDEAS = Resource(
    name="ideas",
    fields=(
        Field("uuid", read_only=True, help="Assigned by the API."),
        Field("title", required_on_create=True, help="At most 255 characters."),
        Field("description", nullable=True),
        Field("podcast_uuid", nullable=True, help="Owning podcast. Omit for the general backlog."),
        Field("position", type=FieldType.INT, help="Order within the backlog."),
        Field("status", enum=IDEA_STATUSES, update_only=True, help="Starts as open."),
        Field(
            "converted_episode_uuid",
            nullable=True,
            update_only=True,
            help="The episode the idea became. Only accepted with --status converted.",
        ),
        Field("created_at", read_only=True),
        Field("updated_at", read_only=True),
    ),
    filters=(
        Filter("status", enum=IDEA_STATUSES),
        Filter("podcast_uuid"),
        Filter("title", help="Partial match."),
        Filter("unassigned", type=FieldType.BOOL, help="Only ideas with no podcast."),
    ),
    sorts=("position", "created_at", "updated_at", "title"),
)
