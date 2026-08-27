"""Resource manifests. One file per API resource, no generator changes required."""

from unleashed.manifest import Resource
from unleashed.resources.episodes import EPISODES

#: Resources whose commands ship today. Leads has a manifest but no commands in v0.1.
SHIPPED: tuple[Resource, ...] = (EPISODES,)
