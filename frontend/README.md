# Ingestion operator dashboard development

This React/TypeScript dashboard belongs to the ingestion service, not a
separately deployed chat UI. Use Node 22, as in this repository's CI.

From this directory:

```text
npm ci
npm run dev
```

The Vite development server proxies `/api` to `http://localhost:8080`.
Start the backend separately using the [service README](../README.md) and
review its scheduling and authorization warnings first. The proxy does not
start a backend, provision resources, or bypass its authorization.

The maintained offline validation commands are:

```text
npm test
npm run lint
npm run build
```

The build writes to `../static`, which FastAPI can serve at `/dashboard`
when the administrative surface is mounted. Runtime mode gates and API
contracts are described in the [runtime guide](../docs/runtime.md).
Product deployment remains in the
[central documentation](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/).
