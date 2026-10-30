# Infrastructure ownership

This component's `main.bicep` declares a resource-group scope but creates no
resources. [Agent Landing Zone](https://github.com/Azure/agent-landing-zone)
owns the foundation, deployment topology, and optional ingestion selection.

The component's deployment assets assume an existing compatible environment,
not a standalone foundation. Follow the central guides from
[`Azure/AI-Landing-Zones` `main`](https://github.com/Azure/AI-Landing-Zones/tree/main/docs/agent-landing-zone):

- [Deploy the full stack](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/deploy-full-stack/)
- [Select ingestion deployment](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/configuration/#ingestion-application-selection)
- [Redeploy applications only](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/deploy-full-stack/#redeploy-applications-only)
