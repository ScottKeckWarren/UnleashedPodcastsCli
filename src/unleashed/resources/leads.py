"""The leads resource.

Declared in v0.1 as a second manifest so the generator is exercised against more than
one shape. No leads commands ship until v1.1.
"""

from __future__ import annotations

from unleashed.manifest import Field, FieldType, Filter, Resource

LEAD_STATUSES = (
    "Identified",
    "Contacted",
    "Responded",
    "Onboarding",
    "Converted",
    "Declined",
)

LEADS = Resource(
    name="leads",
    fields=(
        Field("uuid", read_only=True),
        Field("show_name", required_on_create=True),
        Field("name", nullable=True, help="Host name."),
        Field("email", nullable=True, help="Required on create unless a handle is given."),
        Field("contact_handle", nullable=True),
        Field("feed_url", nullable=True, help="Required on create unless a show URL is given."),
        Field("show_url", nullable=True),
        Field("episode_count", type=FieldType.INT, nullable=True),
        Field("last_episode_at", type=FieldType.DATE, nullable=True),
        Field("cadence_note", nullable=True),
        Field("has_guests", type=FieldType.BOOL),
        Field("guest_evidence", nullable=True),
        Field("niche", nullable=True),
        Field("llm_estimate", type=FieldType.INT, nullable=True, help="0-100, stored verbatim."),
        Field("found_at", type=FieldType.DATE, nullable=True),
        Field("source", nullable=True),
        Field("status", enum=LEAD_STATUSES),
        Field("contacted_at", read_only=True),
        Field("notes", nullable=True),
    ),
    filters=(
        Filter("status", enum=LEAD_STATUSES),
        Filter("feed_url"),
        Filter("show_url"),
        Filter("show_name"),
        Filter("niche"),
        Filter("has_guests", type=FieldType.BOOL),
        Filter("last_episode_since", type=FieldType.DATE, help="On or after."),
        Filter("min_llm_estimate", type=FieldType.INT, help="Excludes leads with no estimate."),
    ),
    sorts=("found_at", "last_episode_at", "created_at", "llm_estimate"),
)
