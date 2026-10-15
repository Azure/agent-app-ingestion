"""Offline regressions for the v2.4.13 blob indexer hotfix.

Execute the actual module, following test_blob_metadata's import-stub pattern.
Only configuration, heavy chunking imports and Azure client boundaries are
replaced; initializer, identity resolution and query control flow remain real.
"""

import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest


def _load_module(monkeypatch, name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def indexer_module(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    credentials = _load_module(
        monkeypatch, "hotfix_credentials", root / "tools" / "credentials.py"
    )
    stubs = {
        "dependencies": {"get_config": Mock()},
        "tools.credentials": {
            "get_azure_client_id": credentials.get_azure_client_id,
        },
        "chunking": {"DocumentChunker": object},
        "chunking.chunker_factory": {"ChunkerFactory": object},
        "utils.file_utils": {"_safe_delete": Mock()},
    }
    for name, attrs in stubs.items():
        stub = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(stub, key, value)
        monkeypatch.setitem(sys.modules, name, stub)

    module = _load_module(
        monkeypatch, "blob_hotfix_under_test", root / "jobs" / "blob_storage_indexer.py"
    )

    class Config:
        def get(self, key, default=None, allow_none=True):
            return default

    module.get_config.return_value = Config()
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    for name in (
        "AzureCliCredential", "ManagedIdentityCredential", "ChainedTokenCredential",
        "BlobServiceClient", "AsyncSearchClient",
    ):
        monkeypatch.setattr(module, name, Mock())
    return module


def _config(module):
    return module.BlobIndexerConfig(
        storage_account_name="teststorage",
        source_container="documents",
        search_endpoint="https://search.example.invalid",
        search_index_name="test-index",
    )


@pytest.mark.parametrize("explicit_config", [False, True], ids=["default", "explicit"])
@pytest.mark.parametrize("client_id", [None, "test-user-identity"], ids=["system", "user"])
def test_cleaner_initializes_config_before_resolving_identity(
    indexer_module, explicit_config, client_id
):
    module = indexer_module
    app = module.get_config.return_value
    original_get = app.get
    app.get = Mock(side_effect=lambda key, default=None, **kw: (
        client_id if key == "AZURE_CLIENT_ID" else original_get(key, default, **kw)
    ))
    cfg = _config(module) if explicit_config else None
    cleaner = module.BlobStorageDeletedItemsCleaner(cfg)

    # On v2.4.13 this raises AttributeError: cleaner has no _app.
    asyncio.run(cleaner._ensure_clients())

    assert cleaner._app is app
    if explicit_config:
        assert cleaner.cfg is cfg
    else:
        assert cleaner.cfg.source_container == "documents"
    assert module.get_config.call_count == (1 if explicit_config else 2)
    app.get.assert_any_call("AZURE_CLIENT_ID", None, allow_none=True)
    module.ManagedIdentityCredential.assert_called_once_with(client_id=client_id)
    module.ChainedTokenCredential.assert_called_once_with(
        module.AzureCliCredential.return_value,
        module.ManagedIdentityCredential.return_value,
    )
    module.BlobServiceClient.assert_called_once_with(
        f"https://{cleaner.cfg.storage_account_name}.blob.core.windows.net",
        credential=cleaner._credential,
    )
    module.AsyncSearchClient.assert_called_once_with(
        endpoint=cleaner.cfg.search_endpoint,
        index_name=cleaner.cfg.search_index_name,
        credential=cleaner._credential,
        api_version="2025-11-01-preview",
    )
    asyncio.run(cleaner._ensure_clients())
    assert module.ManagedIdentityCredential.call_count == 1
    assert module.AsyncSearchClient.call_count == 1


async def _rows(items):
    for item in items:
        yield item


def _search_client(pages):
    return Mock(
        search=AsyncMock(side_effect=[_rows(page) for page in pages]),
        delete_documents=AsyncMock(),
        close=AsyncMock(),
    )


def _assert_no_elevated_headers(search, expected_calls):
    assert search.await_count == expected_calls
    for call in search.await_args_list:
        headers = call.kwargs.get("headers", {})
        assert "x-ms-enable-elevated-read" not in {
            key.lower() for key in headers
        }
        assert call.kwargs["search_text"] == "*"


def test_index_state_queries_omit_elevated_header(indexer_module):
    module = indexer_module
    indexer = module.BlobStorageDocumentIndexer(_config(module))
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    search = _search_client([
        [{"parent_id": "/documents/kept.txt",
          "metadata_storage_last_modified": timestamp.isoformat()}],
        [],
    ])
    module.AsyncSearchClient.return_value = search

    state = asyncio.run(indexer._load_latest_index_state())

    assert state == {"/documents/kept.txt": timestamp}
    assert [call.kwargs["skip"] for call in search.search.await_args_list] == [0, 1000]
    _assert_no_elevated_headers(search.search, 2)


def test_replacement_delete_queries_omit_elevated_header(indexer_module):
    module = indexer_module
    indexer = module.BlobStorageDocumentIndexer(_config(module))
    search = _search_client([[{"id": "old-chunk"}], []])
    module.AsyncSearchClient.return_value = search

    asyncio.run(indexer._delete_parent_docs("/documents/old.txt"))

    search.delete_documents.assert_awaited_once_with(documents=[{"id": "old-chunk"}])
    _assert_no_elevated_headers(search.search, 2)


def test_purge_scan_delete_and_consistency_queries_omit_elevated_header(
    indexer_module, monkeypatch
):
    module = indexer_module
    cleaner = module.BlobStorageDeletedItemsCleaner(_config(module))
    # Isolate query behavior from the independently tested initializer regression.
    cleaner._credential = Mock(close=AsyncMock())
    cleaner._blob_service = Mock(close=AsyncMock())
    cleaner._blob_service.get_container_client.return_value.list_blobs.return_value = _rows([])
    search = _search_client([
        [{"parent_id": "/documents/deleted.txt"}], [],  # index inventory
        [{"id": "deleted-chunk"}], [],                # per-parent deletion
        [],                                          # consistency scan
    ])
    cleaner._search_client = search
    for method in ("_ensure_container", "_write_file_log", "_write_run_summary"):
        monkeypatch.setattr(cleaner, method, AsyncMock())

    asyncio.run(cleaner.run())

    search.delete_documents.assert_awaited_once_with(
        documents=[{"id": "deleted-chunk"}]
    )
    queries = [call.kwargs for call in search.search.await_args_list]
    assert [query["select"] for query in queries] == [
        ["parent_id"], ["parent_id"], ["id"], ["id"], ["parent_id"],
    ]
    assert queries[2]["filter"] == (
        "parent_id eq '/documents/deleted.txt' and source eq 'blob'"
    )
    summary = cleaner._write_run_summary.await_args.args[1]
    assert summary["indexParentsPurged"] == 1
    assert summary["indexChunkDocumentsDeleted"] == 1
    assert summary["indexParentsCountAfter"] == 0
    search.close.assert_awaited_once()
    _assert_no_elevated_headers(search.search, 5)
