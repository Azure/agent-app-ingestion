"""Chunk identifiers use SHA-256 while preserving short-key compatibility."""

import hashlib

import pytest

from tests.test_worker_failure_boundaries import worker_module


@pytest.fixture(params=["blob", "sharepoint"])
def keys(request, worker_module):
    if request.param == "blob":
        module = worker_module("blob_storage_indexer")
        worker = object.__new__(module.BlobStorageDocumentIndexer)
        return worker._make_chunk_key, worker._make_chunk_key_prefix
    module = worker_module("sharepoint_ingestion_config")
    return module._make_chunk_key, module._make_chunk_key_prefix


def test_short_chunk_identifiers_remain_unchanged(keys):
    make_key, make_prefix = keys
    assert make_key("/folder/document.pdf", 7) == "folder-document-pdf-c00007"
    assert make_prefix("/folder/document.pdf") == "folder-document-pdf-c*"


def test_long_chunk_identifiers_use_the_same_sha256_suffix(keys):
    make_key, make_prefix = keys
    parent = "/" + "document" * 24 + ".pdf"
    digest = hashlib.sha256(parent.encode("utf-8")).hexdigest()[:10]
    key = make_key(parent, 7)
    assert key == f"{parent[1:101]}-{digest}-c00007"
    assert make_prefix(parent) == f"{key[:-5]}*"
    assert make_key(parent, 7) == key
    assert make_key(parent + "other", 7) != key
