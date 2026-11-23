"""Reindexing deletes every matching chunk without deleting other parents."""

import copy
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

from azure.core.exceptions import AzureError
from azure.search.documents.models import IndexingResult
import pytest

from tests.test_worker_failure_boundaries import worker_module


class Results:
    def __init__(self, documents):
        self.documents = documents

    def __aiter__(self):
        async def values():
            for document in self.documents:
                yield document

        return values()

    def by_page(self):
        async def pages():
            yield self

        return pages()


class Search:
    def __init__(self, documents, *, stale=False, stale_reads=0, reject=False):
        self.documents = {doc["id"]: copy.deepcopy(doc) for doc in documents}
        self.stale_documents = copy.deepcopy(self.documents)
        self.stale = stale
        self.stale_reads = stale_reads
        self.reject = reject
        self.requests = []
        self.batches = []

    async def search(self, **kwargs):
        self.requests.append(kwargs)
        parent = re.search(r"parent_id eq '((?:[^']|'')*)'", kwargs["filter"])[1].replace("''", "'")
        source = "blob" if "source eq 'blob'" in kwargs["filter"] else None
        use_stale = self.stale or (self.batches and self.stale_reads > 0)
        if use_stale and self.stale_reads:
            self.stale_reads -= 1
        documents = self.stale_documents if use_stale else self.documents
        selected = [
            {"id": doc["id"]}
            for doc in documents.values()
            if doc["parent_id"] == parent and (source is None or doc["source"] == source)
        ]
        skip = kwargs.get("skip", 0)
        return Results(selected[skip:skip + kwargs["top"]])

    async def delete_documents(self, *, documents):
        self.batches.append(copy.deepcopy(documents))
        results = []
        for index, document in enumerate(documents):
            succeeded = not self.reject or index != 0
            if succeeded:
                self.documents.pop(document["id"])
            results.append(IndexingResult.deserialize({
                "key": document["id"],
                "status": succeeded,
                "statusCode": 200 if succeeded else 503,
            }))
        return results


@pytest.fixture(params=[
    ("blob_storage_indexer", "BlobStorageDocumentIndexer"),
    ("sharepoint_indexer", "SharePointIndexer"),
])
def worker(request, worker_module):
    module_name, class_name = request.param
    module = worker_module(module_name)
    instance = object.__new__(getattr(module, class_name))
    instance.cfg = SimpleNamespace(indexer_name="test", batch_size=100)
    instance._ensure_clients = AsyncMock()
    return instance


@pytest.mark.asyncio
async def test_parent_deletion_removes_all_pages_without_touching_other_documents(worker):
    instance = worker
    parent = "/synthetic/'" + "x" * 129
    source = "blob" if instance.__class__.__name__ == "BlobStorageDocumentIndexer" else "sharepoint"
    documents = [
        {"id": f"legacy-{number:04d}", "parent_id": parent, "source": source, "acl": ["keep"]}
        for number in range(1001)
    ]
    documents.extend([
        {"id": "current-0000", "parent_id": parent, "source": source, "acl": ["keep"]},
        {"id": "other-parent", "parent_id": "/unrelated", "source": source, "acl": ["unchanged"]},
    ])
    instance._search_client = Search(documents)

    await instance._delete_parent_docs(parent)

    assert set(instance._search_client.documents) == {"other-parent"}
    assert instance._search_client.documents["other-parent"]["acl"] == ["unchanged"]
    assert all(len(batch) <= 1000 for batch in instance._search_client.batches)
    assert all(request["headers"]["x-ms-enable-elevated-read"] == "true"
               for request in instance._search_client.requests)


@pytest.mark.asyncio
async def test_partial_delete_failure_stops_and_surfaces_error(worker):
    instance = worker
    instance._search_client = Search([
        {"id": "a", "parent_id": "/parent", "source": "blob"},
        {"id": "b", "parent_id": "/parent", "source": "blob"},
    ], reject=True)

    with pytest.raises(AzureError, match="confirm"):
        await instance._delete_parent_docs("/parent")
    assert len(instance._search_client.batches) == 1


@pytest.mark.asyncio
async def test_delete_error_is_propagated(worker):
    instance = worker
    instance._search_client = Search([
        {"id": "a", "parent_id": "/parent", "source": "blob"},
    ])
    instance._search_client.delete_documents = AsyncMock(side_effect=AzureError("Search unavailable"))

    with pytest.raises(AzureError, match="Search unavailable"):
        await instance._delete_parent_docs("/parent")


@pytest.mark.asyncio
async def test_blob_replacement_does_not_upload_after_partial_deletion(worker_module):
    module = worker_module("blob_storage_indexer")
    instance = object.__new__(module.BlobStorageDocumentIndexer)
    instance.cfg = SimpleNamespace(indexer_name="test", batch_size=100)
    instance._ensure_clients = AsyncMock()
    instance._search_client = Search([
        {"id": "old", "parent_id": "/parent", "source": "blob"},
    ], reject=True)
    instance._upload_in_batches = AsyncMock()

    with pytest.raises(AzureError, match="confirm"):
        await instance._replace_parent_docs("/parent", [{"id": "new"}])
    instance._upload_in_batches.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_search_results_cannot_loop_forever_or_report_success(worker, monkeypatch, caplog):
    from tools import aisearch

    instance = worker
    instance._search_client = Search([
        {"id": "a", "parent_id": "/parent", "source": "blob"},
    ], stale=True)
    monkeypatch.setattr(aisearch.asyncio, "sleep", AsyncMock())

    with pytest.raises(TimeoutError, match="progress"):
        await instance._delete_parent_docs("/parent")
    assert len(instance._search_client.batches) == 1
    assert "Search deletion stalled on visible deleted keys" in caplog.text


@pytest.mark.asyncio
async def test_stale_search_results_can_settle_without_redeleting(worker, monkeypatch):
    from tools import aisearch

    instance = worker
    instance._search_client = Search([
        {"id": "a", "parent_id": "/parent", "source": "blob"},
    ], stale_reads=2)
    sleep = AsyncMock()
    monkeypatch.setattr(aisearch.asyncio, "sleep", sleep)

    await instance._delete_parent_docs("/parent")
    assert len(instance._search_client.batches) == 1
    assert sleep.await_count == 2
