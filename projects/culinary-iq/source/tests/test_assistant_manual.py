import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import assistant_manual


client = TestClient(app)


def document(document_id="doc-one", title="Document One", status="current", version="1.0.0", capability="core.restaurant_directory", body="# Overview\n\nUseful restaurant workflow guidance."):
    return f'''---
document_id: {document_id}
title: {title}
version: {version}
status: {status}
applicable_routes: ["/photo-iq"]
feature: photo-iq
audience: ["operators"]
last_updated: 2026-07-30
capability_requirements: ["{capability}"]
---
{body}
'''


@pytest.fixture()
def manual_paths(tmp_path, monkeypatch):
    root = tmp_path / "manual"
    root.mkdir()
    index = tmp_path / "index.json"
    history = tmp_path / "history"
    pin = tmp_path / "pin.json"
    monkeypatch.setattr(assistant_manual, "MANUAL_ROOT", root)
    monkeypatch.setattr(assistant_manual, "INDEX_PATH", index)
    monkeypatch.setattr(assistant_manual, "INDEX_HISTORY_ROOT", history)
    monkeypatch.setattr(assistant_manual, "INDEX_PIN_PATH", pin)
    monkeypatch.setattr(settings, "assistant_manual_auto_refresh", False)
    return root, index, history


def test_recursive_markdown_index_and_non_authoritative_status_filter(manual_paths):
    root, index, _ = manual_paths
    nested = root / "features" / "setup"
    nested.mkdir(parents=True)
    (nested / "current.md").write_text(document(), encoding="utf-8")
    (root / "draft.md").write_text(document("draft-doc", "Draft", "draft", body="# Draft\n\nRestaurant workflow guidance in review."), encoding="utf-8")
    (root / "future.md").write_text(document("future-doc", "Future", "future", body="# Future\n\nRestaurant workflow guidance planned later."), encoding="utf-8")
    payload = assistant_manual.rebuild_manual_index(root, index)
    assert payload["document_count"] == 3 and index.exists()
    results, diagnostics = assistant_manual.search_manual("restaurant workflow guidance")
    assert {item["document_id"] for item in results} == {"doc-one"}
    assert diagnostics["excluded_non_authoritative_chunks"] == {"draft": 1, "future": 1}


def test_validation_reports_duplicate_missing_title_status_links_and_capabilities(manual_paths):
    root, _, _ = manual_paths
    (root / "one.md").write_text(document("duplicate"), encoding="utf-8")
    (root / "two.md").write_text(document("duplicate", title="", status="invented", capability="future.telepathy", body="# Other\n\nSee [missing](missing.md#nowhere)."), encoding="utf-8")
    preview = assistant_manual.preview_manual_source(root)
    codes = {issue["code"] for issue in preview["issues"]}
    assert preview["valid"] is False
    assert {"duplicate_document_id", "missing_required_metadata", "missing_title", "invalid_status", "incompatible_capability_requirement", "broken_internal_link"} <= codes


def test_failed_rebuild_keeps_previous_index_byte_for_byte(manual_paths):
    root, index, _ = manual_paths
    path = root / "current.md"
    path.write_text(document(), encoding="utf-8")
    assistant_manual.rebuild_manual_index(root, index)
    original = index.read_bytes()
    path.write_text(document(status="invalid"), encoding="utf-8")
    with pytest.raises(assistant_manual.ManualValidationError):
        assistant_manual.rebuild_manual_index(root, index)
    assert index.read_bytes() == original


def test_development_auto_refresh_rebuilds_changed_markdown(manual_paths):
    root, index, _ = manual_paths
    path = root / "current.md"
    path.write_text(document(version="1.0.0"), encoding="utf-8")
    first = assistant_manual.rebuild_manual_index(root, index)
    path.write_text(document(version="1.1.0", body="# Overview\n\nFrequently edited wording."), encoding="utf-8")
    settings.environment = "development"
    settings.assistant_manual_auto_refresh = True
    refreshed = assistant_manual.load_manual_index()
    assert refreshed["version"] != first["version"]
    assert refreshed["source_fingerprint"] == assistant_manual.preview_manual_source(root)["source_fingerprint"]


def test_index_history_and_atomic_rollback(manual_paths):
    root, index, history = manual_paths
    path = root / "current.md"
    path.write_text(document(version="1.0.0"), encoding="utf-8")
    first = assistant_manual.rebuild_manual_index(root, index)
    path.write_text(document(version="2.0.0", body="# Overview\n\nUpdated workflow wording."), encoding="utf-8")
    second = assistant_manual.rebuild_manual_index(root, index)
    assert first["version"] != second["version"] and len(list(history.glob("*.json"))) == 2
    restored = assistant_manual.rollback_manual_index(first["version"], index)
    assert restored["version"] == first["version"]
    assert json.loads(index.read_text(encoding="utf-8"))["version"] == first["version"]
    settings.assistant_manual_auto_refresh = True
    settings.environment = "development"
    assert assistant_manual.load_manual_index()["version"] == first["version"]


def test_development_preview_endpoints_and_production_guard(manual_paths, monkeypatch):
    root, index, _ = manual_paths
    (root / "current.md").write_text(document(), encoding="utf-8")
    assistant_manual.rebuild_manual_index(root, index)
    monkeypatch.setattr(settings, "environment", "development")
    assert client.get("/api/assistant/manual/preview").status_code == 200
    assert client.post("/api/assistant/manual/validate").json()["valid"] is True
    assert client.post("/api/assistant/manual/rebuild").status_code == 200
    monkeypatch.setattr(settings, "environment", "production")
    assert client.get("/api/assistant/manual/preview").status_code == 404
