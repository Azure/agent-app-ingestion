---
applyTo: "VERSION,CHANGELOG.md,README.md,docs/**"
---

# Release metadata and documentation

- Follow `.github/copilot-instructions.md` completely.
- On feature work, do not change `VERSION`.
- On `develop`, stage changes under exactly one `## [Unreleased]`.
- On `release/x.y.z`, set `VERSION` to `x.y.z` and convert `Unreleased` to
  `## [vX.Y.Z] - YYYY-MM-DD`.
- Never add `Unreleased` to a release branch or `main`.
- Changelog entries use a bold descriptive title and explain behavior and
  impact with relevant technical context.
- Keep component READMEs limited to concise descriptions and central links.
- Coordinate all application user, operator, and developer guides on `main` in
  [`Azure/AI-Landing-Zones`](https://github.com/Azure/AI-Landing-Zones/tree/main/docs/agent-landing-zone).
- Keep [Monitoring & audit](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/application-monitoring/)
  aligned with executable local contracts, telemetry, and tests.
- Preserve local internal engineering instructions, ADRs, schemas, contracts,
  governance, workflows, policies, and changelogs.
- Never publish private Azure environment or resource-group names.
- Load `service-release` for release work and
  `documentation-consistency` for user- or operator-visible changes.
