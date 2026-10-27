# Infrastructure ownership

This component's `main.bicep` declares a resource-group scope but creates no
resources. [Agent Landing Zone](https://github.com/Azure/agent-landing-zone)
owns deployment topology, optional ingestion selection, resources, identities,
configuration, and runtime version pins.

Follow the [central deployment documentation](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/)
from its [main-branch source](https://github.com/Azure/AI-Landing-Zones/tree/main/docs/agent-landing-zone).
The component's `azure.yaml` and deployment scripts assume an existing compatible
environment. Running them is not a standalone setup or a way to switch retrieval
backends. For local startup only, return to the [ingestion README](../README.md).
