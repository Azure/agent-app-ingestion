<!--
page_type: sample
languages:
- azdeveloper
- powershell
- bicep
products:
- azure
- azure-ai-foundry
- azure-openai
- azure-ai-search
urlFragment: agent-app-ingestion
name: Agent Landing Zone Data Ingestion
description: Python document ingestion service that prepares grounding content for Azure AI Search.
-->
# Agent Landing Zone Data Ingestion

The Python 3.12 ingestion service for
[Agent Landing Zone](https://github.com/Azure/agent-landing-zone). It chunks
documents, generates embeddings, writes Azure AI Search content, and runs
Blob, SharePoint, NL2SQL, and maintenance jobs. It also exposes ingestion APIs,
an operator dashboard, and a separately gated hosted retrieval API.
It processes documents, not conversational agents.

## Documentation

All application user, operator, and developer guides live in the
[central documentation source](https://github.com/Azure/AI-Landing-Zones/tree/main/docs/agent-landing-zone)
on `Azure/AI-Landing-Zones` `main` and are published at:

- [Document ingestion](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/ingestion/)
- [Ingestion jobs and recovery](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/ingestion-jobs/)
- [Application operations](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/operations/)
- [Run ingestion locally](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/local-development/#ingestion)
- [Application API reference](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/application-api/)
- [Ingestion tests and quality checks](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/application-testing/#ingestion)

## Contributing

Follow the [engineering contract](AGENTS.md) and
[contribution guidelines](https://github.com/Azure/agent-landing-zone/blob/main/CONTRIBUTING.md).
Internal engineering rules, policies, and executable contracts remain local.
See [security reporting](SECURITY.md) and the [license](LICENSE.md).

## Trademarks

Microsoft trademarks and logos are subject to
[Microsoft's guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Modified versions must not imply sponsorship. Third-party trademarks follow
their owners' policies.
