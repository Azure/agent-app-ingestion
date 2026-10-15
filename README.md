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
an operator dashboard, and a separately gated hosted retrieval API. It does
not execute conversational agents or store their full chat history.

## Documentation and release scope

- [Product documentation](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/)
  owns deployment topology and shared setup.
- [Canonical documentation source](https://github.com/Azure/AI-Landing-Zones/tree/main/docs/agent-landing-zone)
  is on `Azure/AI-Landing-Zones` `main`, not a legacy documentation branch.
- [Runtime, API, security, scheduling, and audit guide](docs/runtime.md)
  covers this service.
- [Contributor quality commands](docs/python-quality.md) and
  [operator dashboard development](frontend/README.md) cover local engineering.

Agent Landing Zone `4.3.0` pins
[`v3.1.1`](https://github.com/Azure/agent-app-ingestion/tree/v3.1.1)
at `72efd8d7d51e10d38bf8b89f03b7eb42e1ed8ff2`. Repository `main` also
contains later naming and App Configuration label changes. The runtime guide
marks the label difference explicitly. `main` or `develop` is not evidence
that a change is in the platform's shipped image.

## Run this service locally

Obtain compatible infrastructure and a development App Configuration store
through Agent Landing Zone first. This repository's Bicep file does not
provision a standalone environment. The selected sources, models, storage,
Search index, identities, and network access must already be configured.

**Starting the service can write and delete data.** Startup jobs default to
enabled, and cron scheduling remains active even when immediate startup jobs
are disabled. Review the [scheduling defaults](docs/runtime.md#jobs-and-startup)
before connecting to any environment.

From this repository's root, with Python 3.12 and Azure CLI installed, run:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
az login
$env:APP_CONFIG_ENDPOINT = "https://<app-configuration-name>.azconfig.io"
.\.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8080
```

These are service startup commands, not infrastructure deployment commands.
See [configuration and identity](docs/runtime.md#configuration-and-identity)
for RBAC, runtime values, and environment opt-in. `GET /healthz` and
`GET /readyz` are process probes, not proof that a source was indexed.

## Optional deployment

The ingestion Container App is optional, independently of Container Apps or
Foundry hosted orchestration. Fresh supported native Foundry IQ deployments
default its platform deployment control to `false`. Existing and custom
selections are preserved. Native Blob ingestion does not replace conversation
attachments or all source types.

Enabling deployment does not change retrieval backends or sources, enable
`POST /retrieve`, or remove API-key requirements from ingestion APIs.
See [deployment and retrieval boundaries](docs/runtime.md#deployment-and-retrieval-boundaries).

## Contributing

Follow the [engineering contract](AGENTS.md) and
[contribution guidelines](https://github.com/Azure/agent-landing-zone/blob/main/CONTRIBUTING.md).
Audit schemas and their integrity pins are in [`contracts/`](contracts/).

## Trademarks

Microsoft trademarks and logos are subject to
[Microsoft's guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Modified versions must not imply sponsorship. Third-party trademarks follow
their owners' policies.
