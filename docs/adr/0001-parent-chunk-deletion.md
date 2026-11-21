# ADR-0001: Bounded parent chunk deletion

- Status: Proposed
- Date: 2026-11-21
- Owners: Ingestion maintainers
- Related pull request: #391

## Context

Reindexing Blob and SharePoint documents must remove all Search chunks for the
selected parent without changing other documents or their ACLs. Deleting while
advancing an offset skips remaining matches, and a SharePoint query limited to
1,000 matches leaves larger parents incomplete.

The v3.1.3 to v3.1.5 change from SHA-1 to SHA-256 changes chunk IDs when the
sanitized parent exceeds 128 characters. An incomplete replacement can leave
old IDs alongside new IDs. The reverse transition has the same risk. Search
queries are not snapshots and deletion visibility can lag.

## Prioritized characteristics

| Characteristic | Priority | Measure |
| --- | --- | --- |
| Data and ACL safety | 1 | Delete only keys returned by the existing parent and source filters |
| Failure visibility | 2 | Abort replacement on incomplete or unconfirmed deletion |
| Bounded operation | 3 | Limit batches, elapsed time, retries and tracked keys |
| Compatibility | 4 | Do not require a new index field or change chunk IDs |

## Options considered

1. Keep the existing offset and fixed top limit. This retains the demonstrated
   incomplete-deletion risk during reindexing and rollback.
2. Use a sorted keyset cursor. It avoids offset drift but requires every
   existing index to make its key sortable and filterable. Those attributes
   cannot be added to an existing field without rebuilding the index.
3. Requery the first bounded page after confirmed deletion. Wait for previously
   deleted keys to disappear, stop explicitly on stalled visibility or limits,
   and preserve the existing filter and elevated-read boundaries. This adds
   Search requests and keeps a bounded set of deleted IDs in memory.

## Decision

Use the third option for parent replacement. Only confirmed deletes advance
the operation. A timeout, partial failure, missing key or failure to observe
progress aborts the operation before replacement uploads.

Blob purge is outside this decision and retains its pagination defect. Its
cleaner also fails during client initialization because `_app` is unset.
Fixing initialization would activate scheduled deletion, and its source scan
applies `BLOB_PREFIX` while its index scan covers all Blob parents. This may
select unrelated parents for deletion when a prefix is configured. Address
those risks together before enabling the cleaner. SharePoint purge is unchanged.

## Compatibility and rollout

No index schema, authorization metadata, parent ID or chunk ID changes are
introduced. The existing v3.1.3-to-v3.1.5 ID transition remains relevant for
long parents. SharePoint freshness lookup can trigger reindexing on upgrade or
rollback because it looks up the current chunk-zero key. Blob freshness uses
parent IDs and can retain old keys until a source change causes replacement.

Before upgrading or rolling back, identify affected long parents and review
the current index for duplicate or orphaned chunks. Use a controlled,
parent-scoped repair or reindex procedure with a verified backup and access
controls. Do not assume a version rollback repairs data already written by a
later version. Coordinate operator guidance in the central documentation.

## Validation

Regression tests cover more than 1,000 chunks, both old and new IDs, unrelated
parents, partial failures and stalled or delayed visibility.
Controlled Azure AI Search validation must verify pagination, deletion
visibility, ACL preservation and replacement before production adoption.
Offline fakes do not establish service consistency or concurrent-write behavior.

## Recovery

On failure, retain the source and retry the affected parent only after
investigating Search availability and the logged failure. A partially deleted
parent can require a controlled reindex from its source. Preserve existing
release tags and use a forward corrective release rather than retagging.

## Review trigger

Revisit when Search consistency, index key attributes, deletion scale or
concurrent writers change, or if controlled validation exposes missed chunks.
