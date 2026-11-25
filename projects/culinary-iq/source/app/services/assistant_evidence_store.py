from __future__ import annotations

import json
import sqlite3
import re
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.schemas.assistant import AssistantLocationEvidence
from app.schemas.restaurant import RestaurantLocationCreate
from app.services.restaurant_directory_store import normalize_text, restaurant_directory


DB_PATH = settings.data_root / settings.restaurant_directory_filename
MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "014_assistant_evidence_bundles.sql"
SOURCE_LABELS = {
    "user_supplied_chat_text": "From your message",
    "uploaded_screenshot": "From uploaded screenshot",
    "configured_maps_provider": "From Apple Maps",
    "stored_culinary_iq_data": "From stored restaurant data",
    "website_provider": "From a connected website",
    "assistant_inference": "Suggested by Culinary IQ — verify before saving",
}
ALLOWED_FIELDS = {
    "name", "address_line_1", "address_line_2", "city", "state", "postal_code", "country",
    "formatted_address", "phone", "website", "timezone", "hours",
}


class AssistantEvidenceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize() -> None:
    restaurant_directory.initialize()
    with closing(_connect()) as db:
        db.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        db.execute("INSERT OR IGNORE INTO schema_migrations VALUES (?, ?)", ("014_assistant_evidence_bundles", _now()))
        db.commit()


def _verification(source_origin: str) -> tuple[str, float, str]:
    if source_origin == "user_supplied_chat_text":
        return "user_supplied", .84, "The value was supplied directly by the user and still requires review."
    if source_origin == "stored_culinary_iq_data":
        return "stored_record", .95, "The value came from an authorized stored restaurant record."
    if source_origin in {"configured_maps_provider", "website_provider"}:
        return "verified_provider", .90, "The value came from a configured provider and still requires review."
    return "unverified_inference", .45, "The value is a model suggestion without independent verification."


def _address_key(values: dict[str, Any]) -> str:
    return normalize_text(
        values.get("formatted_address")
        or " ".join(str(values.get(key) or "") for key in ("address_line_1", "city", "state", "postal_code", "country"))
    )


def _normalize_location(values: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(values)
    website = str(normalized.get("website") or "").strip()
    if website and "://" not in website and re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(?:/.*)?$", website, re.I):
        normalized["website"] = f"https://{website}"
    return normalized


def _decode_bundle(row: sqlite3.Row, items: list[sqlite3.Row], restaurant: Any | None) -> dict[str, Any]:
    locations: dict[int, dict[str, Any]] = {}
    item_payloads: list[dict[str, Any]] = []
    for item in items:
        value = json.loads(item["structured_value_json"])
        locations.setdefault(item["entity_index"], {})[item["field_name"]] = value
        item_payloads.append({
            "id": item["id"], "entity_index": item["entity_index"], "field_name": item["field_name"],
            "value": value, "raw_supplied_text": item["raw_supplied_text"], "confidence": item["confidence"],
            "confidence_basis": item["confidence_basis"], "verification_status": item["verification_status"],
            "source_references": json.loads(item["source_references_json"] or "[]"),
            "provenance_chain": json.loads(item["provenance_chain_json"] or "[]"),
        })
    existing = {_address_key(location.model_dump()): location for location in (restaurant.locations if restaurant else []) if _address_key(location.model_dump())}
    duplicates = []
    conflicts = []
    seen: dict[str, int] = {}
    for index, location in locations.items():
        key = _address_key(location)
        if key and key in existing:
            duplicates.append({"location_index": index, "existing_location_id": existing[key].id, "message": "This address is already saved."})
        if key and key in seen:
            duplicates.append({"location_index": index, "duplicate_of_index": seen[key], "message": "This address appears more than once in the proposal."})
        elif key:
            seen[key] = index
        if not location.get("address_line_1") and not location.get("formatted_address"):
            conflicts.append({"location_index": index, "field_name": "address", "message": "Add an address before saving this location."})
    payload = dict(row)
    payload["source_label"] = SOURCE_LABELS.get(row["source_origin"], "Imported evidence")
    payload["locations"] = [locations[index] | {"_index": index} for index in sorted(locations)]
    payload["items"] = item_payloads
    payload["conflicts"] = conflicts
    payload["duplicate_warnings"] = duplicates
    payload.pop("workspace_id", None)
    payload.pop("raw_supplied_text", None)
    payload.pop("provider_metadata_json", None)
    payload.pop("idempotency_key", None)
    payload.pop("assistant_message_id", None)
    return payload


def get_bundle(bundle_id: str, workspace_id: str) -> dict[str, Any] | None:
    initialize()
    with closing(_connect()) as db:
        row = db.execute("SELECT * FROM assistant_evidence_bundles WHERE id=? AND workspace_id=?", (bundle_id, workspace_id)).fetchone()
        if not row:
            return None
        items = db.execute(
            "SELECT * FROM assistant_evidence_items WHERE bundle_id=? AND workspace_id=? ORDER BY entity_index,field_name",
            (bundle_id, workspace_id),
        ).fetchall()
    restaurant = restaurant_directory.get(row["restaurant_id"], workspace_id) if row["restaurant_id"] else None
    return _decode_bundle(row, items, restaurant)


def list_pending(workspace_id: str, restaurant_id: str | None = None) -> list[dict[str, Any]]:
    initialize()
    query = "SELECT id FROM assistant_evidence_bundles WHERE workspace_id=? AND status='pending'"
    args: list[Any] = [workspace_id]
    if restaurant_id:
        query += " AND restaurant_id=?"
        args.append(restaurant_id)
    query += " ORDER BY updated_at DESC LIMIT 20"
    with closing(_connect()) as db:
        rows = db.execute(query, args).fetchall()
    return [bundle for row in rows if (bundle := get_bundle(row["id"], workspace_id))]


def prepare_locations(
    *, workspace_id: str, restaurant_id: str, conversation_id: str, message_id: str | None,
    locations: list[dict[str, Any]], source_origin: str, raw_supplied_text: str | None,
    idempotency_key: str, model: str | None, provider_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    initialize()
    restaurant = restaurant_directory.get(restaurant_id, workspace_id)
    if not restaurant:
        raise AssistantEvidenceError("restaurant_not_found", "The selected restaurant is no longer available.", 404)
    with closing(_connect()) as db:
        existing = db.execute(
            "SELECT id FROM assistant_evidence_bundles WHERE workspace_id=? AND idempotency_key=?",
            (workspace_id, idempotency_key),
        ).fetchone()
    if existing:
        return get_bundle(existing["id"], workspace_id)  # type: ignore[return-value]
    if source_origin in {"configured_maps_provider", "website_provider"} and not provider_metadata:
        raise AssistantEvidenceError("provider_provenance_required", "Provider evidence requires provider provenance.", 422)
    verification, confidence, basis = _verification(source_origin)
    bundle_id, created = str(uuid4()), _now()
    with closing(_connect()) as db:
        db.execute(
            "INSERT INTO assistant_evidence_bundles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                bundle_id, workspace_id, restaurant_id, conversation_id, message_id, "restaurant_locations",
                "assistant_structured_evidence", source_origin, raw_supplied_text, "pending", idempotency_key,
                json.dumps(provider_metadata or {}), model, created, created,
            ),
        )
        for index, candidate in enumerate(locations):
            validated = _normalize_location(AssistantLocationEvidence.model_validate(candidate).model_dump(exclude_none=True))
            for field_name, value in validated.items():
                if field_name not in ALLOWED_FIELDS or value in ("", [], None) or field_name == "source_references":
                    continue
                db.execute(
                    "INSERT INTO assistant_evidence_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid4()), bundle_id, workspace_id, index, field_name, raw_supplied_text,
                        json.dumps(value), confidence, basis, verification,
                        json.dumps(validated.get("source_references", [])),
                        json.dumps([{"source_type": "assistant_structured_evidence", "source_origin": source_origin, "conversation_id": conversation_id, "message_id": message_id}]),
                        created,
                    ),
                )
        db.commit()
    return get_bundle(bundle_id, workspace_id)  # type: ignore[return-value]


def discard_bundle(bundle_id: str, workspace_id: str) -> bool:
    initialize()
    with closing(_connect()) as db:
        result = db.execute(
            "UPDATE assistant_evidence_bundles SET status='discarded',updated_at=? WHERE id=? AND workspace_id=? AND status='pending'",
            (_now(), bundle_id, workspace_id),
        )
        db.commit()
    return bool(result.rowcount)


def confirm_locations(bundle_id: str, workspace_id: str, locations: list[AssistantLocationEvidence]) -> dict[str, Any]:
    bundle = get_bundle(bundle_id, workspace_id)
    if not bundle:
        raise AssistantEvidenceError("evidence_bundle_not_found", "These pending changes are no longer available.", 404)
    if bundle["status"] != "pending":
        raise AssistantEvidenceError("evidence_bundle_not_pending", "These changes have already been reviewed.", 409)
    restaurant_id = bundle["restaurant_id"]
    restaurant = restaurant_directory.get(restaurant_id, workspace_id) if restaurant_id else None
    if not restaurant:
        raise AssistantEvidenceError("restaurant_not_found", "The selected restaurant is no longer available.", 404)
    existing_keys = {_address_key(item.model_dump()) for item in restaurant.locations}
    created_ids: list[str] = []
    skipped = 0
    for location in locations:
        values = location.model_dump(exclude_none=True, exclude={"source_references"})
        key = _address_key(values)
        if key and key in existing_keys:
            skipped += 1
            continue
        created = restaurant_directory.create_location(restaurant_id, RestaurantLocationCreate(**values), workspace_id)
        if created:
            created_ids.append(created.id)
            if key:
                existing_keys.add(key)
    with closing(_connect()) as db:
        db.execute(
            "UPDATE assistant_evidence_bundles SET status='confirmed',updated_at=? WHERE id=? AND workspace_id=?",
            (_now(), bundle_id, workspace_id),
        )
        db.commit()
    return {"restaurant_id": restaurant_id, "created_location_ids": created_ids, "created_count": len(created_ids), "duplicate_count": skipped, "status": "confirmed"}


initialize()
