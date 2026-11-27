"""SharePoint drive selection must respect the requested site scope."""

import logging
from unittest.mock import Mock, call

from tests.test_worker_failure_boundaries import worker_module


def test_missing_subsite_does_not_query_parent_drive(worker_module):
    module = worker_module("sharepoint", "tools")
    worker = module.SharePointMetadataStreamer()
    worker._make_ms_graph_request = Mock(side_effect=[
        {"id": "parent-id"},
        {"value": [{"name": "another", "id": "other-id"}]},
    ])

    assert worker._get_site_and_drive_ids("example.org", "parent", "child", "Documents") == (None, None)
    assert worker._make_ms_graph_request.call_args_list == [
        call("https://graph.microsoft.com/v1.0/sites/example.org:/sites/parent:/"),
        call("https://graph.microsoft.com/v1.0/sites/parent-id/sites"),
    ]


def test_subsite_drive_and_returned_site_use_subsite_id(worker_module, caplog):
    module = worker_module("sharepoint", "tools")
    worker = module.SharePointMetadataStreamer()
    worker._make_ms_graph_request = Mock(side_effect=[
        {"id": "parent-id"},
        {"value": [{"name": "child", "id": "child-id"}]},
        {"value": [{"name": "Documents", "id": "child-drive"}]},
    ])

    with caplog.at_level(logging.INFO):
        result = worker._get_site_and_drive_ids("example.org", "parent", "child", "Documents")

    assert result == ("child-id", "child-drive")
    assert worker._make_ms_graph_request.call_args_list[-1] == call(
        "https://graph.microsoft.com/v1.0/sites/child-id/drives"
    )
    assert "Retrieved sub-site ID: child-id" in caplog.text


def test_without_subsite_drive_and_site_remain_parent(worker_module):
    module = worker_module("sharepoint", "tools")
    worker = module.SharePointMetadataStreamer()
    worker._make_ms_graph_request = Mock(side_effect=[
        {"id": "parent-id"},
        {"value": [{"name": "Documents", "id": "parent-drive"}]},
    ])

    assert worker._get_site_and_drive_ids("example.org", "parent", drive_name="Documents") == (
        "parent-id", "parent-drive"
    )
    assert worker._make_ms_graph_request.call_args_list[-1] == call(
        "https://graph.microsoft.com/v1.0/sites/parent-id/drives"
    )
