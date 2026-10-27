# Ingestion runtime guide

Return to the [service README](../README.md). Shared deployment and topology
belong in the [central documentation](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/)
and its [main-branch source](https://github.com/Azure/AI-Landing-Zones/tree/main/docs/agent-landing-zone).
Unless marked as historical behavior, these notes describe `v3.1.2`.
Use the platform release manifest for the compatible component combination.

## Configuration and identity

`APP_CONFIG_ENDPOINT` is required in the process environment.
The [configuration client](../tools/appconfig.py) tries managed identity and
then Azure CLI credentials. `AZURE_CLIENT_ID` can select a user-assigned
identity. Azure access requires data-plane RBAC and connectivity, not merely
a successful CLI login.

Use the shared `agent-lz` label and exact runtime key names. There is no
automatic prefix alias. Selector order differs between revisions:

| Revision | Selectors, earliest to latest |
| --- | --- |
| `v3.1.1` | `gpt-rag-ingestion`, `agent-lz`, all labels (`label_filter=None`) |
| `v3.1.2` | `gpt-rag-ingestion`, `agent-app-ingestion`, `agent-lz`, all labels (`label_filter=None`) |

Both revisions require `azure-appconfiguration-provider==2.5.0` and
`azure-appconfiguration==1.8.1`. The provider's default when the label argument
is omitted is `"\0"`, which selects only unlabelled settings. This service
instead passes explicit `None`. The
[provider preserves that value](https://github.com/Azure/azure-sdk-for-python/blob/970708307ddf52b8f1b4a4207da0ab6e2ee83eca/sdk/appconfiguration/azure-appconfiguration-provider/azure/appconfiguration/provider/_models.py#L71-L103),
and the [SDK omits the REST label filter](https://github.com/Azure/azure-sdk-for-python/blob/f6ae3b6d2baddece07ddea989ef3b3fb57630662/sdk/appconfiguration/azure-appconfiguration/azure/appconfiguration/_generated/_operations/_operations.py#L121-L149).
That is an unfiltered all-labels query, including unlabelled settings, not a
null-label-only query or an absent-only fallback.

The provider deduplicates by key, retaining the last setting in the combined
result sequence. The final all-labels query can therefore overwrite earlier
service-label or `agent-lz` values with a same-key result from any label.
There is no guaranteed unlabelled-over-`agent-lz` priority. Do not treat service
result ordering across labels as an explicit operator override policy.

Operator configuration writes default to `agent-lz`, configurable through
the process variable `APP_CONFIG_LABEL`. Confirm the effective read value
after a write and avoid conflicting same-key values across labels.
The legacy `v3.1.1` image does not read the `agent-app-ingestion` service label.
Narrowing the final selector would require a separately reviewed runtime
change, not a documentation edit.

Direct runtime environment reads are normally disabled. The implementation
uses non-empty-string truthiness for `allow_environment_variables`, so even
the string `false` enables them. To keep them disabled, leave the variable
unset or empty. To opt in deliberately, use `true`. Environment values then
precede provider values. This differs from the orchestrator's boolean parsing.

Endpoint-load failure first tries `AZURE_APPCONFIG_CONNECTION_STRING` if
configured. Without one, it uses the environment-only adapter only when
environment reads are enabled. Otherwise it propagates. A failed chosen
connection-string load also propagates. Prefer managed identity over this
legacy secret-based fallback. Resolve runtime secrets through Key Vault
references.

Configure resources for the selected pipeline, including
`SEARCH_SERVICE_NAME`, `SEARCH_RAG_INDEX_NAME`, storage containers,
model deployments, and the applicable document analysis endpoint.
Dependencies are conditional on source and chunker selection. The
[chunker factory](../chunking/chunker_factory.py) supports transcripts,
spreadsheets, JSON, PDFs/images, Office documents, and text fallbacks.
`USE_DOCUMENT_INTELLIGENCE=false` selects Content Understanding by default.
`MULTIMODAL=false` by default. Office support depends on the selected analysis
service and version.

Azure SDK credential-based access does not make the HTTP API wholly keyless.
Ingestion and retrieval have different inbound authentication contracts.
No `APP_CONFIG_TLS_COMPATIBILITY` implementation exists in this service,
including pinned `v3.1.1`. Setting the orchestrator's opt-in here has no
effect. Standard SDK transport and certificate behavior still applies.
Do not disable certificate verification to work around connectivity issues.

## Jobs and startup

The FastAPI lifespan initializes configuration, validates mode-specific
resources, mounts administrative routes, configures telemetry, and starts
APScheduler. [`jobs/runtime.py`](../jobs/runtime.py) owns the shared scheduler
reference, registry, and running-job tracking.

| Setting | Runtime default |
| --- | --- |
| `RUN_JOBS_ON_STARTUP` | `true`, runs scheduled ingestion/purge jobs sequentially in a background task |
| `CRON_RUN_BLOB_INDEX` | `0 * * * *` |
| `CRON_RUN_BLOB_PURGE` | `10 * * * *` |
| `CRON_RUN_LOG_CLEANUP` | `0 * * * *`, plus immediate startup cleanup |
| `CRON_RUN_SHAREPOINT_INDEX`, `CRON_RUN_SHAREPOINT_PURGE` | No schedule when unset |
| `CRON_RUN_NL2SQL_INDEX`, `CRON_RUN_NL2SQL_PURGE` | No schedule when unset |
| `CRON_RUN_IMAGES_PURGE` | No schedule when unset |

`RUN_JOBS_ON_STARTUP=false` prevents immediate ingestion/purge runs, not cron
runs or startup log cleanup. Unset or blank Blob schedule values receive the
startup defaults rather than disabling those jobs. Use an isolated development
environment and review configured schedules before starting locally.
The probes `/healthz` and `/readyz` do not validate successful indexing.
Invalid cron configuration fails schedule setup.

## Ingestion and operator APIs

| Route | Purpose and boundary |
| --- | --- |
| `POST /document-chunking` | Chunk source documents using the indexer-style request envelope. Requires `X-API-KEY`. |
| `POST /text-embedding` | Generate text embeddings using its request envelope. Requires `X-API-KEY`. |
| `POST /ingest-documents` | Process direct document records and upload chunks. Requires `X-API-KEY`. |
| `GET /api/jobs`, `GET /api/jobs/queue`, `GET /api/files` | Administrative job and file information when the admin surface is mounted. |
| `POST /api/jobs/{job_type}/run` | Queue a manual job. Uses the Admin gate when Entra is configured and rejects a conflicting run with `409`. |
| `GET /api/config`, `PUT /api/config` | Read effective settings or write allowlisted settings. Mutations use the Admin gate when Entra is configured. |
| `POST /api/config/reload`, `POST /api/config/apply` | Reload configuration or apply configured schedules. Uses the same administrative mutation gate. |

See the schemas and handlers in [`main.py`](../main.py) and
[`api/admin.py`](../api/admin.py) rather than sending an arbitrary file upload
or assuming every endpoint accepts the same JSON.
The API-key validator accepts `DATA_INGEST_APP_APIKEY` and the legacy
`INGESTION_APP_APIKEY` alias. Store them as secrets. HTTP success for a
per-record ingestion envelope does not mean every record was indexed.
Inspect record errors and confirmed `indexedChunks`.

In classic mode, the dashboard and administrative read routes do not all have
an unconditional Entra gate. The Admin dependency allows development access
when the tenant is absent. Do not expose an unconfigured development service
as a production operator endpoint. Hosted/panel authorization is stricter.

Configuration writes can partially succeed. A confirmed write remains
`200/applied` if only best-effort local refresh fails.
`POST /api/config/apply` reports `500` for genuine schedule-application
failures. Neither response implies rollback of earlier writes.

## Deployment and retrieval boundaries

The platform decides whether to deploy this Container App. Fresh supported
native Foundry IQ deployments default that deployment choice to `false`,
independently of Container Apps or Foundry hosted orchestration. Existing and
custom choices remain preserved. This platform control is not a runtime API
flag and is not consumed by this service to choose retrieval or sources.

Native Foundry IQ Blob indexing handles its configured corpus. It does not
replace this service's conversation-attachment ingestion, SharePoint workers,
NL2SQL metadata jobs, or all format-specific processing. `searchIndex`
knowledge sources can use indexes populated by this service.
Deploying it does not change the orchestrator's `RETRIEVAL_BACKEND`, register
sources automatically, enable hosted retrieval, or change authentication.
Select only the pipelines required by the platform topology.

Two existing runtime flags control administrative mounting, not whether this
Container App exists. They are resolved at startup, so changing the mounted
surface requires a restart:

| Flags | Administrative surface |
| --- | --- |
| `DEPLOY_HOSTED_AGENT_ORCHESTRATION=false` (default) | Classic dashboard and `/api/*` admin routes mount. Static dashboard content still requires a built bundle. |
| Hosted flag `true`, `DEPLOY_ADMINISTRATIVE_PANEL=false` (default) | No classic admin dashboard or `/api/panel/*` routes. Jobs and the ingestion APIs are not disabled by this mode. |
| Both flags `true` | Admin surface and `/api/panel/*` mount. Startup requires Cosmos account/database and Entra tenant/client configuration. |

Hosted/panel `/api/panel/*` requires a validated bearer with the exact `Admin`
role and has no development bypass. It provides status, Cosmos-backed feedback,
and an overview of ingestion data. Conversation history at
`GET /api/panel/conversations/{conversation_id}/history` returns `501`.
It does not proxy chat or retrieve Foundry-managed message bodies.

The separate `/panel/overview/metrics` and `/panel/corpus-curation/*` routes
are registered independently and fail with `503` unless
`DEPLOY_ADMINISTRATIVE_PANEL`, `PANEL_OPERATOR_SURFACES_ENABLED`, an explicit
`PANEL_OPERATOR_APP_ROLE` or `PANEL_OPERATOR_GROUP_ID`, and the
`DATA_INGEST_APP_APIKEY` cursor-signing secret are configured.
They require a validated delegated user with that role or group.
App-only tokens are rejected. Overview reads use aggregate Cosmos counts and
suppress buckets below `PANEL_OVERVIEW_MIN_CARDINALITY` (default `5`) as null.
Curation operates on blocked-file logs in Blob Storage, not chat messages.
Its cursor is HMAC-signed, caller-bound, and expires after
`PANEL_CURSOR_TTL_SECONDS` (default `600`).
The [panel contract](../contracts/conversations-panel-v1.schema.json) defines
the wire shapes. These operator routes are not conversation persistence APIs.

### Hosted Toolbox retrieval

`POST /retrieve` is a preview OpenAPI tool, separately gated from the
administrative mounting mode. Both `HOSTED_RETRIEVAL_ENABLED` and
`HOSTED_RETRIEVAL_INV_002_VALIDATED` default to `false`. The route returns
`503` until both are enabled. The second is an operator attestation of the
required isolated native-authorization validation, not a test this service
performs automatically. Do not set it merely because deployment succeeded.

Configure Toolbox `UserEntraToken` passthrough and
`HOSTED_RETRIEVAL_TOKEN_AUDIENCE` for the exact validated Search query-token
audience. Configure index native permission filters and the required user and
service RBAC through the platform. Validate restricted users and negative
cross-user/group cases before attesting. There is no manual group fallback.

The route validates a delegated user bearer and forwards it unchanged through
Search's `x-ms-query-source-authorization` header while using the service
credential for Search access. A static API key or managed identity alone
cannot replace the delegated caller token.
The body accepts only `query` (1 to 1,000 characters) and optional `top`
(1 to 10, default `5`). Identity, groups, and index selection are not inputs.
Results omit ACL/vector fields and bound content to 8,000 characters.
Missing/invalid bearer returns `401`, non-user or non-delegated identity
returns `403`, invalid schema returns `422`, missing server configuration
returns `500`, and Search query failures return sanitized `502`.
Cleanup failure after an otherwise successful query can still fail a request.

## Audit, provenance, and recovery

Ingestion emits the seven reserved `ingestion.*` event types through its
existing OpenTelemetry pipeline. Unlike orchestrator audit emission, it has
no `AUDIT_EVENTS_ENABLED` opt-in. Export still depends on telemetry
configuration. Emission is best-effort, not guaranteed delivery.
The event types are:

- `ingestion.run.started`
- `ingestion.run.completed`
- `ingestion.run.failed`
- `ingestion.run.cancelled`
- `ingestion.document.indexed`
- `ingestion.document.rejected`
- `ingestion.document.deleted`

Run wrappers attempt one start and one terminal event. Document events use the
run correlation and parent event. A completed event means the run wrapper did
not observe a failure, not proof that every possible source was processed.
Document success events depend on confirmed Search write/delete results.

`INGESTION_PROVENANCE_ENABLED=false` by default. Enabling it attaches optional
provenance to indexed/deleted events. `INGESTION_REQUIRE_GOVERNANCE_METADATA`
also defaults to `false`. Setting it to `true` without provenance fails startup.
Strict mode reports classification and right-to-use only when both are
explicitly supplied. It does not reject indexing simply because they are
missing. In non-strict mode, `INGESTION_DEFAULT_CLASSIFICATION` defaults to
`unclassified` and `INGESTION_DEFAULT_RIGHT_TO_USE` defaults to `not_asserted`.
`source_uri_id` and `source_version_id` are unkeyed SHA-256 digests.
They and content checksums can leak existence or equality information.
`delete_after` is metadata, not an automatic purge schedule.

The [logical audit schema](../contracts/audit-event-v2.schema.json),
[wire schema](../contracts/audit-event-v2.application-insights.schema.json),
and [digests](../contracts/audit-event-v2.sha256) define compatibility.
Custom-event names use `agentlz.audit.ingestion`. Decode the root
`parent_event_id` sentinel `evt_00000000000000000000000000000000` to null.
Audit evidence is not an immutable ledger or a legal compliance claim.

Reverting code or an image does not restore deleted Search documents, reverse
Blob control changes, or undo App Configuration writes. Use compatible platform
release pins and separately authorized source restoration, reingestion, and
configuration recovery.

## Component image build selection

The `v3.1.2` [PowerShell](../scripts/deploy.ps1) and
[Bash](../scripts/deploy.sh) hooks accept only `BUILD_MODE=local` or
`BUILD_MODE=acr-task`, normalized for case and surrounding whitespace.
Selection when unset is conditional, not always remote:

1. An explicit non-empty `BUILD_MODE` takes precedence.
2. Otherwise legacy `USE_DOCKER=true`, `1`, or `yes` selects `local`.
   `false`, `0`, or `no` selects `acr-task`.
3. If still unset, `NETWORK_ISOLATION=true` or a non-empty
   `ACR_TASK_AGENT_POOL` selects `acr-task`.
4. Otherwise a usable Docker command and successful `docker info` select
   `local`. If Docker is unavailable, select `acr-task`.

PowerShell additionally rejects Docker Desktop's manually paused diagnostic
and trims legacy/boolean selectors. Bash lowercases those selectors without
trimming them. Use exact values without whitespace for portability.
Unknown `USE_DOCKER` values fall through to automatic detection, but unknown
explicit `BUILD_MODE` values fail. Explicit `local` without Docker also fails,
with no automatic remote fallback.

Local builds target `linux/amd64` and push to ACR. `acr-task` invokes
`az acr build`. With network isolation enabled, remote mode requires an
`ACR_TASK_AGENT_POOL` or fails. These hooks assume platform-provisioned
resources. They do not infer that a parent predeploy log message set a
build-mode variable.

Deployment destinations use `AZURE_APP_RESOURCE_GROUP` from App Configuration
under `agent-lz`. Only a successful missing or empty read falls back to
`AZURE_RESOURCE_GROUP` for older environments. Configuration access failures
or multiple destination values stop deployment rather than select another group.
