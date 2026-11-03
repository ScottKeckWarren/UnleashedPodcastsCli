"""Resource manifests. One file per API resource, no generator changes required."""

from unleashed.manifest import Resource
from unleashed.resources.episodes import EPISODES
from unleashed.resources.ideas import IDEAS
from unleashed.resources.leads import LEADS
from unleashed.resources.people import PEOPLE
from unleashed.resources.short_form_videos import SHORT_FORM_VIDEOS
from unleashed.resources.tasks import TASKS

#: Resources whose commands ship today.
SHIPPED: tuple[Resource, ...] = (EPISODES, SHORT_FORM_VIDEOS, PEOPLE, IDEAS, TASKS, LEADS)
