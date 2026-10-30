---
name: documentation-consistency
description: Keeps ingestion repository and published Agent Landing Zone documentation aligned with shipped formats, configuration, indexing, deployment, audit, and operator behavior.
---

# Ingestion documentation consistency

1. Identify the user, operator, developer, or cross-component behavior that changed.
2. Search this repository for the format, configuration key, index field,
   endpoint, job type, contract, and previous terminology.
3. Keep component READMEs limited to concise descriptions and central pointers.
   Keep internal engineering instructions, ADRs, schemas, contracts, governance,
   workflows, policies, and changelogs local.
4. Search `main` of
   [`Azure/AI-Landing-Zones`](https://github.com/Azure/AI-Landing-Zones/tree/main/docs/agent-landing-zone)
   for all affected application user, operator, and developer guides. Update
   every affected page in the coordinated change. Audit guidance belongs in
   [Monitoring & audit](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/application-monitoring/),
   backed by executable local contracts, telemetry, and tests.
5. Register new published pages in that repository's `mkdocs.yml`.
6. Ensure examples match current defaults, App Configuration labels,
   supported deployment modes, and released component behavior.

Publish application guides at
https://azure.github.io/AI-Landing-Zones/agent-landing-zone/ rather than
duplicating them locally. Report the central source commit or pull request and
publication status in the implementation handoff.
