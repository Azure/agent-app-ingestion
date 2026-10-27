# Python quality checks

This guide covers the repository's contributor tooling, not deployment
readiness or a certification that GitHub merge rules are active.
Read the [engineering contract](../AGENTS.md) first.
The [runtime guide](runtime.md) owns service behavior and configuration.
Cross-component contributor guidance belongs in the
[central main-branch documentation](https://github.com/Azure/AI-Landing-Zones/tree/main/docs/agent-landing-zone).

## Contributor commands

Use Python 3.12 in an isolated environment. Runtime requirements and
development-only quality tools are separate manifests:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-quality.txt
python -m pip install pytest pytest-asyncio
git fetch origin develop
$Base = git merge-base HEAD origin/develop
python -m pytest -q tests/test_quality_policy.py tests/test_jobs_runtime.py
python -m pytest tests -q --junitxml=.artifacts/pytest.xml -o junit_family=legacy
python -I .github/scripts/quality-evidence.py --junit .artifacts/pytest.xml --base-ref $Base --report .artifacts/test-evidence.json
python -I .github/scripts/check-quality.py --check all --base-ref $Base --test-evidence .artifacts/test-evidence.json --report .artifacts/quality.json
```

Use the actual fetched target SHA for release-target or explicitly authorized
non-`develop` work. Do not substitute a convenient base to suppress findings.
If local PowerShell policy prevents activation, use the virtual environment's
Python executable directly rather than changing execution policy.

`--check` accepts `all`, `lint`, `typing`, `architecture`, `exceptions`, or
`policy`. `--repository` selects a separate candidate checkout for the
protected-base evaluator. Ordinary contributors can omit it.
`--test-evidence` binds exception and dynamic-import evidence to executed tests.
Exit `0` means passed, `1` means violations, and `2` means incomplete or
invalid execution. Missing reports and nonzero results are not success.
The checker creates report directories but does not rewrite source or policy.

Use `python -I` for checker, evidence, and aggregate entrypoints. The tooling
isolates startup and static analysis from candidate imports, plugins, and
startup hooks. This is not an operating-system sandbox or protection against
an untrusted interpreter or installed tool.

## Ownership and policy

`main.py` composes the application and scheduler lifecycle.
[`jobs/runtime.py`](../jobs/runtime.py) owns the shared scheduler reference,
registry, cron map, running-job state, lock, and tracking wrapper.
Administrative routes use that interface rather than importing `main`.
Compatibility re-exports do not create a second owner of mutable state.

The quality policy inventories flat-root and package modules, public/private
surfaces, import directions, typing coverage, dynamic imports, and broad
exception handlers. Blocking typing starts with
`telemetry/audit_contract.py`, `telemetry/audit_sanitizer.py`, and
`jobs/runtime.py`. New runtime modules enter scope automatically.
Out-of-scope imported diagnostics remain visible.

An exact exception record is not a blanket category approval. Source and
handler fingerprints, approved protected-base metadata, and passing same-run
behavior evidence must match. Changed or stale records fail. Logging and
rethrowing do not automatically waive the independent handler check.
Do not add suppressions, rewrite baselines, approve records, or weaken policy
to make a candidate green. Policy changes require their protected review path.

The initial ingestion adoption recorded 67 active exception records under
[explicit administrative authorization](https://github.com/Azure/agent-landing-zone/issues/681#issuecomment-5601804634).
That historical authorization is not independent latest-head GitHub review or
permission for future changes. See
[adoption tracking](https://github.com/Azure/agent-landing-zone/issues/681) and
the [coordination PR](https://github.com/Azure/agent-landing-zone/pull/689)
for historical evidence. Old bootstrap component pins and task milestones are
not the current shipped compatibility matrix. The [README](../README.md)
identifies the platform pin.

## Operator dashboard

Use Node 22 as configured in CI. From `frontend`, run:

```text
npm ci
npm test
npm run lint
npm run build
```

Do not bypass peer validation. The maintained `frontend-checks` job runs these
commands. See the [dashboard development guide](../frontend/README.md).
The Dockerfile still names a Node 20 devcontainer build stage. The maintained
local/CI Node 22 choice is not a claim that a specific Docker base-image patch
was validated by this documentation review.

## CI evidence and activation

The [test workflow](../.github/workflows/tests.yml) has Python behavior and
frontend jobs plus the five quality checks. Its `quality-gate` aggregate
requires successful same-workflow behavior jobs and fresh, matching quality
reports. Missing, skipped, cancelled, stale, or failed results are not a pass.
For normal runs, CI selects the protected target's evaluator, configuration,
and tool pins. Candidate policy or checker changes cannot self-authorize.
If a target lacks an evaluator, the bootstrap path deliberately blocks a
normal green policy claim.

The quality workflow uses unprivileged `pull_request` execution. The separate
main-branch guard uses `pull_request_target` to enforce branch naming.
Do not confuse the two workflows or infer repository settings from YAML.

Administrators separately own required-check activation, code-owner
protection, latest-head review, stale-approval dismissal, and bypass
restrictions. Validate those through normal administrative review.
This document neither changes nor verifies live GitHub settings.

## Compatibility and recovery

Tests and static checks do not certify a live Azure topology, cross-component
deployment, image build, or artifact recovery. Record the exact candidate,
base, command outcomes, and unperformed checks in the component handoff.
Use the platform's compatible manifest pins rather than historical bootstrap
versions.

Recover code or tooling through a reviewed revert or roll-forward. Do not
disable protected checks as a substitute for policy repair. Reverting an
image does not restore deleted Search documents, undo Blob control changes,
or reverse persisted App Configuration writes. Source restoration,
reingestion, and configuration recovery need separate authorization.
