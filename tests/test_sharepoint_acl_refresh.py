"""Permission-only synchronization exercises the real collection and Graph paths."""

import asyncio
import copy
from datetime import datetime, timezone
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
from azure.core.exceptions import AzureError
from azure.search.documents.models import IndexingResult
import pytest

from tests.test_worker_failure_boundaries import worker_module


USER = "11111111-1111-4111-8111-111111111111"
OLD_USER = "22222222-2222-4222-8222-222222222222"
GROUP = "33333333-3333-4333-8333-333333333333"
OLD_GROUP = "44444444-4444-4444-8444-444444444444"
STAMP = "2026-01-01T00:00:00Z"
ACL_FIELDS = ("metadata_security_user_ids", "metadata_security_group_ids")


def permissions(users=(USER,), groups=(GROUP,), *, inherited=False):
    grants = [
        {"grantedToV2": {kind: {"id": principal}}}
        for kind, principals in (("user", users), ("group", groups))
        for principal in principals
    ]
    if inherited:
        for grant in grants:
            grant["inheritedFrom"] = {"driveId": "drive", "id": "parent"}
    return {"value": grants}


class Search:
    def __init__(self, documents):
        self.documents = {doc["id"]: copy.deepcopy(doc) for doc in documents}
        self.queries = []
        self.batches = []
        self.reject = set()

    async def get_document(self, *, key, **kwargs):
        return copy.deepcopy(self.documents[key])

    async def search(self, **kwargs):
        self.queries.append(kwargs)
        parent = re.search(r"parent_id eq '((?:[^']|'')*)'", kwargs["filter"])[1].replace("''", "'")
        bounds = re.search(r"parent_id ge '((?:[^']|'')*)' and parent_id lt '((?:[^']|'')*)'", kwargs["filter"])
        lower, upper = (value.replace("''", "'") for value in bounds.groups()) if bounds else ("", "")

        async def values():
            for doc in sorted(self.documents.values(), key=lambda value: value["id"]):
                if doc["parent_id"] == parent or (bounds and lower <= doc["parent_id"] < upper):
                    yield {field: copy.deepcopy(doc.get(field)) for field in kwargs["select"]}

        return values()

    async def merge_documents(self, *, documents):
        self.batches.append(copy.deepcopy(documents))
        results = []
        for doc in documents:
            succeeded = doc["id"] not in self.reject
            if succeeded:
                self.documents[doc["id"]].update(copy.deepcopy(doc))
            results.append(IndexingResult.deserialize({
                "key": doc["id"], "status": succeeded, "statusCode": 200 if succeeded else 503,
            }))
        return results


@pytest.fixture
def connector(worker_module):
    module = worker_module("sharepoint_indexer")
    worker = object.__new__(module.SharePointIndexer)
    worker.cfg = SimpleNamespace(
        indexer_name="sharepoint-indexer", batch_size=2, max_file_processing_attempts=3,
        max_concurrency=1,
    )
    worker._item_timeout_s = 5
    worker._collection_gather_timeout_s = 5
    worker._http_total_timeout_s = 5
    worker._allowed_exts = {"pdf"}
    worker._get_list_navigation_base_url = AsyncMock(return_value="")
    worker._get_lookup_columns_map = AsyncMock(return_value={})
    worker._resolve_lookup_fields_for_item = AsyncMock(return_value={})
    worker._read_file_log = AsyncMock(return_value=None)
    worker._write_file_log = AsyncMock()
    worker._embed = AsyncMock(side_effect=AssertionError("Unchanged content must not be embedded"))
    worker._delete_parent_docs = AsyncMock(side_effect=AssertionError("ACL refresh must not delete content"))
    worker._upload_docs = AsyncMock(side_effect=AssertionError("ACL refresh must not upload content"))
    graph = object.__new__(module.SharePointGraphClient)
    graph._graph_base = "https://graph.microsoft.com/v1.0"
    graph._graph_beta_base = "https://graph.microsoft.com/beta"
    graph._gget = AsyncMock(return_value=permissions())
    graph.get_site_id = AsyncMock(return_value="site")
    graph.get_drive_item = AsyncMock(return_value={
        "id": "file", "name": "document.pdf", "file": {"mimeType": "application/pdf"},
        "parentReference": {"driveId": "drive"},
        "fileSystemInfo": {"lastModifiedDateTime": STAMP},
        "lastModifiedDateTime": "2026-01-02T00:00:00Z",
    })
    graph.download_drive_item = AsyncMock(side_effect=AssertionError("Unchanged content must not be downloaded"))

    async def items(**kwargs):
        yield {"id": "item", "lastModifiedDateTime": STAMP, "fields": {"Title": "Synthetic item"}}

    graph.iter_items = items
    worker._graph_client = graph
    body = module._make_parent_key("example.org", "site", "list", "item")
    file_parent = module._make_parent_key("example.org", "site", "list", "item", "document.pdf")

    def document(parent, number):
        return {
            "id": module._make_chunk_key(parent, number), "parent_id": parent, "source": "sharepoint",
            "metadata_storage_last_modified": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "content": "Existing synthetic content", "contentVector": [0.1],
            ACL_FIELDS[0]: [OLD_USER], ACL_FIELDS[1]: [OLD_GROUP],
        }

    worker._search_client = Search([
        document(body, 0), *[document(file_parent, n) for n in range(3)],
        document("unrelated", 0),
    ])
    spec = {"siteDomain": "example.org", "siteName": "site", "listId": "list"}
    return module, worker, graph, spec, document, body, file_parent


async def run_collection(connector, *, library=False):
    module, worker, _, spec, *_ = connector
    stats = module.RunStats()
    result = await worker._process_collection(
        object(), {**spec, "listType": "documentLibrary" if library else "genericList"},
        "run", asyncio.Semaphore(1), stats, asyncio.Lock(),
    )
    return result, stats


@pytest.mark.asyncio
@pytest.mark.parametrize("library", [False, True])
@pytest.mark.parametrize("change", ["grant", "revoke", "empty", "inherited", "break-inheritance", "restore-inheritance"])
async def test_unchanged_content_refreshes_every_affected_acl(connector, library, change):
    _, worker, graph, _, _, body, file_parent = connector
    users = [OLD_USER, USER] if change == "grant" else ([] if change == "empty" else [USER])
    groups = [] if change == "empty" else [GROUP]
    graph._gget.return_value = permissions(
        users, groups, inherited=change in {"inherited", "restore-inheritance"},
    )
    before = copy.deepcopy(worker._search_client.documents)
    result, stats = await run_collection(connector, library=library)
    parents = {body, file_parent} if library else {body}
    for key, doc in worker._search_client.documents.items():
        if doc["parent_id"] in parents:
            assert set(doc[ACL_FIELDS[0]]) == set(users)
            assert doc[ACL_FIELDS[1]] == groups
            assert {k: v for k, v in doc.items() if k not in ACL_FIELDS} == {
                k: v for k, v in before[key].items() if k not in ACL_FIELDS
            }
        else:
            assert doc == before[key]
    assert result["failed"] == 0 and result["success"] == 1 and result["chunks"] == 0
    assert stats.items_indexed == 0 and stats.items_skipped_nochange == 0
    assert worker._write_file_log.await_args.args[1]["status"] == "acl-updated"
    assert all(set(doc) == {"id", *ACL_FIELDS} for batch in worker._search_client.batches for doc in batch)
    assert all(len(batch) <= worker.cfg.batch_size for batch in worker._search_client.batches)
    worker._embed.assert_not_awaited()
    worker._upload_docs.assert_not_awaited()
    worker._delete_parent_docs.assert_not_awaited()
    graph.download_drive_item.assert_not_awaited()
    if library:
        assert "/drives/drive/items/file/permissions" in graph._gget.await_args.args[1]


@pytest.mark.asyncio
async def test_equal_acl_order_or_duplicates_do_not_write_or_reprocess(connector):
    _, worker, graph, *_ = connector
    for doc in worker._search_client.documents.values():
        doc[ACL_FIELDS[0]] = [USER, OLD_USER]
        doc[ACL_FIELDS[1]] = [GROUP]
    graph._gget.return_value = permissions([OLD_USER, USER, USER], [GROUP])
    result, stats = await run_collection(connector, library=True)
    assert result["success"] == 0 and result["failed"] == 0
    assert stats.items_skipped_nochange == 1
    assert worker._search_client.batches == []
    worker._embed.assert_not_awaited()
    graph.download_drive_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_chunks_are_scanned_without_a_top_limit(connector):
    _, worker, _, _, make_document, _, file_parent = connector
    worker.cfg.batch_size = 1500
    for n in range(1005):
        doc = make_document(file_parent, n)
        worker._search_client.documents[doc["id"]] = doc
    result, _ = await run_collection(connector, library=True)
    assert result["failed"] == 0
    assert sum(len(batch) for batch in worker._search_client.batches) == 1006
    assert all("top" not in query and "skip" not in query for query in worker._search_client.queries)
    assert all(query["headers"] == {"x-ms-enable-elevated-read": "true"} for query in worker._search_client.queries)
    assert all(query["order_by"] == ["id asc"] for query in worker._search_client.queries)
    assert max(map(len, worker._search_client.batches)) <= 1000


@pytest.mark.asyncio
async def test_item_range_updates_old_file_names_but_not_sibling_items(connector):
    _, worker, _, _, make_document, body, _ = connector
    before = {}
    for parent in [body + "0", body + "2/document.pdf", body + "-sibling", body + "/previous-name.pdf"]:
        doc = make_document(parent, 0)
        worker._search_client.documents[doc["id"]] = doc
        before[doc["id"]] = copy.deepcopy(doc)
    result, _ = await run_collection(connector, library=True)
    assert result["failed"] == 0
    for key, old in before.items():
        doc = worker._search_client.documents[key]
        if old["parent_id"] == body + "/previous-name.pdf":
            assert doc[ACL_FIELDS[0]] == [USER] and doc[ACL_FIELDS[1]] == [GROUP]
        else:
            assert doc == old


@pytest.mark.asyncio
async def test_inheritance_changes_replace_previous_effective_grants_without_parent_union(connector):
    _, worker, graph, _, _, body, file_parent = connector
    for users, groups, inherited in [
        ([OLD_USER], [OLD_GROUP], True),
        ([USER], [GROUP], True),
        ([USER], [], False),
        ([OLD_USER], [GROUP], True),
    ]:
        graph._gget.return_value = permissions(users, groups, inherited=inherited)
        result, _ = await run_collection(connector, library=True)
        assert result["failed"] == 0
        for doc in worker._search_client.documents.values():
            if doc["parent_id"] in {body, file_parent}:
                assert doc[ACL_FIELDS[0]] == users and doc[ACL_FIELDS[1]] == groups
    assert graph._gget.await_count == 4
    assert all("/drives/drive/items/file/permissions?" in call.args[1] for call in graph._gget.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 501])
async def test_failed_permission_lookup_does_not_clear_acl_or_claim_success(connector, status, caplog):
    _, worker, graph, *_ = connector
    graph._gget.side_effect = aiohttp.ClientResponseError(
        SimpleNamespace(real_url="https://graph.microsoft.com"), (), status=status,
        message="private-permission-canary",
    )
    before = copy.deepcopy(worker._search_client.documents)
    result, stats = await run_collection(connector, library=True)
    assert result["failed"] == stats.items_failed == 1 and result["success"] == 0
    assert worker._search_client.documents == before and not worker._search_client.batches
    assert worker._write_file_log.await_args.args[1]["status"] == "error"
    assert "private-permission-canary" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"value": None}, {"value": [None]}, {"value": [{"grantedToV2": []}]}])
async def test_invalid_permission_response_is_not_a_successful_empty_acl(connector, payload):
    _, worker, graph, *_ = connector
    graph._gget.return_value = payload
    result, _ = await run_collection(connector)
    assert result["failed"] == 1 and result["success"] == 0
    assert worker._search_client.batches == []


@pytest.mark.asyncio
async def test_permission_pages_are_complete_before_any_acl_write(connector):
    _, worker, graph, *_ = connector
    next_url = graph._graph_beta_base + "/sites/site/lists/list/items/item/permissions?$skiptoken=next"
    graph._gget.side_effect = [
        {**permissions([USER], []), "@odata.nextLink": next_url}, permissions([], [GROUP]),
    ]
    result, _ = await run_collection(connector)
    assert result["failed"] == 0
    doc = worker._search_client.batches[0][0]
    assert doc[ACL_FIELDS[0]] == [USER] and doc[ACL_FIELDS[1]] == [GROUP]
    assert graph._gget.await_count == 2


@pytest.mark.asyncio
async def test_late_permission_page_failure_never_commits_partial_acl(connector):
    _, worker, graph, *_ = connector
    next_url = graph._graph_beta_base + "/sites/site/lists/list/items/item/permissions?$skiptoken=next"
    graph._gget.side_effect = [
        {**permissions([USER], []), "@odata.nextLink": next_url}, AzureError("private-late-page"),
    ]
    result, _ = await run_collection(connector)
    assert result["failed"] == 1 and worker._search_client.batches == []


@pytest.mark.asyncio
@pytest.mark.parametrize("next_link", [
    "https://untrusted.example/permissions", "http://graph.microsoft.com/beta/sites/site/lists/list/items/item/permissions",
    "https://graph.microsoft.com/beta/sites/other/lists/list/items/item/permissions", "", 7,
])
async def test_invalid_permission_pagination_never_forwards_credentials_or_commits_acl(connector, next_link):
    _, worker, graph, *_ = connector
    graph._gget.return_value = {**permissions(), "@odata.nextLink": next_link}
    result, _ = await run_collection(connector)
    assert result["failed"] == 1 and worker._search_client.batches == []
    assert graph._gget.await_count == 1


@pytest.mark.asyncio
async def test_permission_pagination_cycle_fails_instead_of_accepting_partial_acl(connector):
    _, worker, graph, *_ = connector
    next_url = graph._graph_beta_base + "/sites/site/lists/list/items/item/permissions?$skiptoken=cycle"
    graph._gget.return_value = {**permissions(), "@odata.nextLink": next_url}
    result, _ = await run_collection(connector)
    assert result["failed"] == 1 and graph._gget.await_count == 2
    assert worker._search_client.batches == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["missing", "failed", "duplicate", "unrelated"])
async def test_acl_merges_require_confirmation_for_every_requested_key(connector, case):
    _, worker, *_ = connector

    def result(key, success=True):
        return IndexingResult.deserialize({"key": key, "status": success, "statusCode": 200})

    async def merge_documents(**kwargs):
        return {
            "missing": [], "failed": [result("key", False)],
            "duplicate": [result("key"), result("key")], "unrelated": [result("other")],
        }[case]

    with pytest.raises(AzureError, match="confirm"):
        await worker._with_backoff(merge_documents, documents=[{"id": "key"}])


@pytest.mark.asyncio
async def test_absent_permission_client_is_not_a_successful_empty_acl(connector):
    _, worker, *_ = connector
    worker._graph_client = None
    with pytest.raises(RuntimeError, match="unavailable"):
        await worker._get_security_principals_for_item(
            session=object(), site_id="site", collection_id="list", item_id="item",
        )


@pytest.mark.asyncio
async def test_changed_content_retains_full_indexing_with_current_acl(connector):
    _, worker, _, _, _, body, _ = connector
    worker._search_client.documents[next(
        key for key, doc in worker._search_client.documents.items() if doc["parent_id"] == body
    )]["metadata_storage_last_modified"] = datetime(2025, 1, 1, tzinfo=timezone.utc)
    worker._embed.side_effect = None
    worker._embed.return_value = [0.2]
    worker._delete_parent_docs.side_effect = None
    worker._upload_docs.side_effect = None
    result, stats = await run_collection(connector)
    assert result["failed"] == 0 and result["success"] == 1 and stats.items_indexed == 1
    worker._embed.assert_awaited_once()
    worker._delete_parent_docs.assert_awaited_once_with(body)
    doc = worker._upload_docs.await_args.args[0][0]
    assert doc[ACL_FIELDS[0]] == [USER] and doc[ACL_FIELDS[1]] == [GROUP]
    assert doc["contentVector"] == [0.2]


@pytest.mark.asyncio
async def test_partial_search_merge_is_visible_and_retry_updates_only_stale_chunks(connector):
    _, worker, _, _, _, _, file_parent = connector
    failed_id = next(
        key for key, doc in worker._search_client.documents.items() if doc["parent_id"] == file_parent
    )
    worker._search_client.reject = {failed_id}
    result, stats = await run_collection(connector, library=True)
    assert result["failed"] == stats.items_failed == 1 and result["success"] == 0
    assert worker._write_file_log.await_args.args[1]["status"] == "error"
    assert worker._search_client.documents[failed_id][ACL_FIELDS[0]] == [OLD_USER]
    worker._search_client.reject.clear()
    worker._search_client.batches.clear()
    result, _ = await run_collection(connector, library=True)
    assert result["failed"] == 0 and result["success"] == 1
    updated = [doc["id"] for batch in worker._search_client.batches for doc in batch]
    assert failed_id in updated
    assert len(updated) < 4
    assert all(doc[ACL_FIELDS[0]] == [USER] for doc in worker._search_client.documents.values()
               if doc["parent_id"] != "unrelated")


@pytest.mark.asyncio
async def test_content_retry_block_does_not_block_permission_revocations(connector):
    _, worker, *_ = connector
    worker._read_file_log.return_value = {
        "blocked": True, "processingAttempts": 3, "blockedReason": "max_attempts_exceeded",
    }
    result, stats = await run_collection(connector, library=True)
    assert result["failed"] == 0 and result["success"] == 1
    assert stats.items_skipped_blocked == 1
    log = worker._write_file_log.await_args.args[1]
    assert log["blocked"] is True and log["processingAttempts"] == 3
    worker._embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_with_partial_item_failure_is_not_reported_finished(connector):
    _, worker, _, spec, *_ = connector
    worker._ensure_clients = AsyncMock()
    worker._close_clients = AsyncMock()
    worker._hydrate_site_configs_from_cosmos = AsyncMock()
    worker._parse_collections = lambda: [spec]
    worker._process_collection = AsyncMock(return_value={"items": 1, "success": 0, "failed": 1, "chunks": 0})
    summaries = []

    async def write(run, summary):
        summaries.append(copy.deepcopy(summary))

    worker._write_run_summary_safely = write
    with pytest.raises(RuntimeError, match="failed"):
        await worker.run()
    assert summaries[-1]["status"] == "failed"
    worker._close_clients.assert_awaited_once()


@pytest.mark.asyncio
async def test_unexpected_item_defect_propagates_and_never_finishes_the_job(connector, caplog):
    _, worker, graph, spec, *_ = connector
    defect = TypeError("private-defect-canary")
    graph._gget.side_effect = defect
    worker._ensure_clients = AsyncMock()
    worker._close_clients = AsyncMock()
    worker._hydrate_site_configs_from_cosmos = AsyncMock()
    worker._parse_collections = lambda: [spec]
    summaries = []

    async def write(run, summary):
        summaries.append(copy.deepcopy(summary))

    worker._write_run_summary_safely = write
    with pytest.raises(TypeError) as raised:
        await worker.run()
    assert raised.value is defect
    assert summaries[-1]["status"] == "failed"
    assert not worker._search_client.batches
    worker._close_clients.assert_awaited_once()
    assert "private-defect-canary" not in caplog.text + str(summaries)
