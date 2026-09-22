"""The short-form-videos resource, per the v1 API contract.

A short stands alone, sits under a podcast, or sits under an episode — an episode brings
its own podcast, so podcast_uuid is only needed without one. The video itself is
attached afterwards through the video-file sub-resource.
"""

from __future__ import annotations

from unleashed.manifest import Attachment, Field, FieldType, Filter, Resource

ORIGINS = ("manual", "generated")

SHORT_FORM_VIDEOS = Resource(
    name="short-form-videos",
    fields=(
        Field("uuid", read_only=True, help="Assigned by the API."),
        Field("title", required_on_create=True, help="At most 255 characters."),
        Field("script", nullable=True, help="The words spoken on camera."),
        Field("body", nullable=True, help="The post caption."),
        Field(
            "micro_body",
            nullable=True,
            help="Caption for platforms with tight limits. At most 280 characters.",
        ),
        Field(
            "podcast_uuid",
            nullable=True,
            help="Owning podcast. Not needed with an episode. Changing it drops the episode.",
        ),
        Field("podcast_episode_uuid", nullable=True, help="Owning episode."),
        Field("target_date", type=FieldType.DATE, nullable=True, help="YYYY-MM-DD."),
        Field("published_date", type=FieldType.DATE, nullable=True, help="YYYY-MM-DD."),
        Field("video_file_uuid", read_only=True),
        Field("origin", read_only=True, enum=ORIGINS),
        Field("created_at", read_only=True),
        Field("updated_at", read_only=True),
    ),
    filters=(
        Filter("podcast_uuid"),
        Filter("podcast_episode_uuid"),
        Filter("origin", enum=ORIGINS),
        Filter("title", help="Partial, case-insensitive match."),
        Filter("standalone", type=FieldType.BOOL, help="Only shorts with no podcast."),
    ),
    sorts=("created_at", "updated_at", "title", "target_date", "published_date"),
    attachments=(
        Attachment(
            "video-file",
            id_field="file_uuid",
            help="UUID of an uploaded video file you own. Upload it in the web app.",
        ),
    ),
)
