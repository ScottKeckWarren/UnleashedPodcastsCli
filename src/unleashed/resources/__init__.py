"""Resource manifests. One file per API resource, no generator changes required."""

from unleashed.manifest import Resource
from unleashed.resources.episodes import EPISODES
from unleashed.resources.people import PEOPLE
from unleashed.resources.short_form_videos import SHORT_FORM_VIDEOS

#: Resources whose commands ship today. Leads has a manifest but no commands yet.
SHIPPED: tuple[Resource, ...] = (EPISODES, SHORT_FORM_VIDEOS, PEOPLE)
