"""The episodes resource, per the v1 API contract."""

from __future__ import annotations

from unleashed.manifest import Document, Field, FieldType, Filter, Listing, Resource

EPISODE_STATUSES = (
    "Idea",
    "Draft",
    "Record",
    "Edit",
    "Scheduled",
    "Published",
    "Promote",
    "Completed",
    "Cancelled",
)

TRANSCRIPT_STATUSES = ("none", "Pending", "Processing", "Completed", "Failed")

EPISODES = Resource(
    name="episodes",
    fields=(
        Field("uuid", read_only=True, help="Assigned by the API."),
        Field(
            "podcast_uuid",
            required_on_create=True,
            immutable=True,
            help="UUID of the owning podcast. Copy it from the web app until v0.3.",
        ),
        Field("podcast_name", read_only=True),
        Field("name", required_on_create=True, help="Episode title."),
        Field(
            "target_published_date",
            type=FieldType.DATE,
            required_on_create=True,
            help="YYYY-MM-DD.",
        ),
        Field("actual_published_date", type=FieldType.DATE, read_only=True),
        Field("status", enum=EPISODE_STATUSES, help="Defaults to Idea."),
        Field(
            "is_published",
            type=FieldType.BOOL,
            update_only=True,
            help="Publishes the episode and stamps the actual published date.",
        ),
        Field("description", nullable=True, help="Show notes. Markdown is rendered."),
        Field("canonical_url", nullable=True),
        Field("cover_art_file_id", read_only=True),
        Field("transcript_status", read_only=True),
    ),
    filters=(
        Filter("podcast_uuid"),
        Filter("status", enum=EPISODE_STATUSES),
        Filter("is_published", type=FieldType.BOOL),
        Filter(
            "transcript_status",
            enum=TRANSCRIPT_STATUSES,
            help="'none' selects episodes with no transcript at all.",
        ),
        Filter("has_cover_art", type=FieldType.BOOL),
        Filter("name", help="Partial, case-insensitive match."),
        Filter("target_published_since", type=FieldType.DATE, help="On or after."),
    ),
    sorts=("target_published_date", "actual_published_date", "created_at", "name", "status"),
    documents=(
        Document(
            "transcript",
            params=(
                Filter(
                    "format",
                    enum=("text", "none"),
                    help="'none' omits the text body, for polling the status. Defaults to text.",
                ),
            ),
            listings=(
                Listing(
                    "utterances",
                    filters=(
                        Filter(
                            "with_words",
                            type=FieldType.BOOL,
                            help="Include per-word timing on each utterance.",
                        ),
                    ),
                    help="Speaker-attributed segments, ordered by start time.",
                ),
            ),
            help=(
                "The episode's most recent transcript. An unfinished transcript reads with a "
                "null text; an episode with no transcript at all is not found."
            ),
        ),
    ),
)
