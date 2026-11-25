from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.services import assistant_store
from app.services.usage_policy import UsagePolicyError


DB_PATH = settings.data_root / settings.restaurant_directory_filename
MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "015_evidence_intake_and_usage_policy.sql"
UPLOAD_ROOT = settings.data_root / "uploads" / "assistant-evidence"

SUPPORTED: dict[str, set[str]] = {
    ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
    ".webp": {"image/webp"}, ".heic": {"image/heic", "image/heif"}, ".heif": {"image/heif", "image/heic"},
    ".pdf": {"application/pdf"}, ".doc": {"application/msword", "application/x-ole-storage"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".txt": {"text/plain"}, ".md": {"text/markdown", "text/plain"}, ".rtf": {"application/rtf", "text/rtf"},
    ".odt": {"application/vnd.oasis.opendocument.text"}, ".csv": {"text/csv", "text/plain"},
    ".xls": {"application/vnd.ms-excel", "application/x-ole-storage"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".ods": {"application/vnd.oasis.opendocument.spreadsheet"}, ".ppt": {"application/vnd.ms-powerpoint", "application/x-ole-storage"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".odp": {"application/vnd.oasis.opendocument.presentation"}, ".json": {"application/json", "text/json"},
    ".xml": {"application/xml", "text/xml"}, ".html": {"text/html"}, ".htm": {"text/html"},
}
UNSAFE_EXTENSIONS = {".exe", ".dll", ".com", ".bat", ".cmd", ".ps1", ".sh", ".js", ".mjs", ".jar", ".msi", ".scr", ".zip", ".rar", ".7z", ".tar", ".gz"}
ZIP_MIMES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text", ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
}


class EvidenceIntakeError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400): super().__init__(message); self.code = code; self.status = status


def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH, timeout=30); db.row_factory = sqlite3.Row; db.execute("PRAGMA foreign_keys=ON"); return db


def initialize() -> None:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    with closing(_connect()) as db:
        db.executescript(MIGRATION_PATH.read_text(encoding="utf-8")); db.commit()


def _zip_mime(data: bytes, extension: str) -> str | None:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
            if extension == ".docx" and "word/document.xml" in names: return ZIP_MIMES[extension]
            if extension == ".xlsx" and "xl/workbook.xml" in names: return ZIP_MIMES[extension]
            if extension == ".pptx" and "ppt/presentation.xml" in names: return ZIP_MIMES[extension]
            if extension in {".odt", ".ods", ".odp"} and "mimetype" in names:
                value = archive.read("mimetype").decode("ascii", "ignore").strip()
                return value if value == ZIP_MIMES[extension] else None
    except (zipfile.BadZipFile, KeyError, OSError): pass
    return None


def detect_mime(data: bytes, extension: str) -> str:
    head = data[:512]
    if head.startswith(b"\xff\xd8\xff"): return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP": return "image/webp"
    if len(head) >= 12 and head[4:8] == b"ftyp" and head[8:12] in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}: return "image/heic" if extension == ".heic" else "image/heif"
    if head.startswith(b"%PDF-"): return "application/pdf"
    if head.startswith(b"{\\rtf"): return "application/rtf"
    if head.startswith(bytes.fromhex("D0CF11E0A1B11AE1")): return "application/x-ole-storage"
    if head.startswith(b"PK\x03\x04"): return _zip_mime(data, extension) or "application/zip"
    sample = data[:8192]
    if b"\x00" in sample: return "application/octet-stream"
    try: text = sample.decode("utf-8")
    except UnicodeDecodeError: return "application/octet-stream"
    stripped = text.lstrip()
    if extension == ".json":
        try: json.loads(text); return "application/json"
        except json.JSONDecodeError: return "text/plain"
    if extension in {".xml"} and stripped.startswith("<?xml"): return "application/xml"
    if extension in {".html", ".htm"} and re.search(r"(?i)<(?:!doctype\s+html|html|head|body)\b", stripped): return "text/html"
    if extension == ".csv" and ("," in text or "\t" in text): return "text/csv"
    if extension == ".md": return "text/markdown"
    return "text/plain"


def _safe_text(data: bytes, extension: str, *, preserve_lines: bool = False) -> str | None:
    if extension in {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".rtf"}:
        value = data.decode("utf-8", "replace")
    elif extension in ZIP_MIMES:
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                candidates = [name for name in archive.namelist() if name.endswith(".xml") and name.startswith(("word/", "xl/", "ppt/slides/", "content.xml"))]
                value = "\n".join(archive.read(name).decode("utf-8", "replace") for name in candidates[:100])
        except (zipfile.BadZipFile, OSError): return None
    else: return None
    value = re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>", " ", value)
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    if preserve_lines:
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\s*\n\s*", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()[: settings.evidence_max_document_characters]
    return re.sub(r"\s+", " ", value).strip()[: settings.evidence_max_document_characters]


def _validate_decodable(data: bytes, detected: str, extension: str) -> None:
    if detected.startswith("image/"):
        try:
            with Image.open(BytesIO(data)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            message = "HEIC images are not supported by this server yet." if extension in {".heic", ".heif"} else "This image is damaged or could not be opened."
            raise EvidenceIntakeError("decode_failed", message, 422) from exc
    if detected == "application/pdf" and (len(data) < 12 or b"%%EOF" not in data[-2048:]):
        raise EvidenceIntakeError("decode_failed", "This PDF is damaged or incomplete.", 422)


def inspect_file(*, filename: str, declared_mime: str | None, data: bytes, preserve_lines: bool = False) -> dict[str, Any]:
    """Apply the universal evidence security policy without persisting the upload."""
    extension = Path(filename).suffix.lower()
    if extension in UNSAFE_EXTENSIONS:
        raise EvidenceIntakeError("unsafe_file", "This file type cannot be uploaded.", 415)
    if extension not in SUPPORTED:
        raise EvidenceIntakeError("unsupported_file", "This file type is not supported.", 415)
    if len(data) > settings.evidence_max_file_mb * 1024 * 1024:
        raise EvidenceIntakeError("file_too_large", f"Each file must be {settings.evidence_max_file_mb} MB or smaller.", 413)
    detected = detect_mime(data, extension)
    if detected not in SUPPORTED[extension]:
        raise EvidenceIntakeError("file_type_mismatch", "The file contents do not match the filename.", 415)
    _validate_decodable(data, detected, extension)
    return {
        "extension": extension,
        "declared_mime_type": declared_mime,
        "detected_mime_type": detected,
        "sha256": hashlib.sha256(data).hexdigest(),
        "file_size": len(data),
        "extracted_text": _safe_text(data, extension, preserve_lines=preserve_lines),
    }


def _public(row: sqlite3.Row, duplicate: bool = False) -> dict[str, Any]:
    return {"id": row["id"], "filename": row["original_filename"], "mime_type": row["detected_mime_type"],
            "size": row["file_size"], "status": row["status"], "message": row["status_detail"],
            "uploaded_at": row["uploaded_at"], "duplicate": duplicate,
            "review_route": f"/photo-iq?view=restaurants&evidenceUpload={row['id']}" if row["status"] == "ready_for_review" else None}


def accept(*, workspace_id: str, user_id: str, conversation_id: str, restaurant_id: str | None,
           filename: str, declared_mime: str | None, data: bytes) -> dict[str, Any]:
    initialize()
    if not assistant_store.get_conversation(conversation_id, workspace_id, 1): raise EvidenceIntakeError("conversation_not_found", "This conversation is no longer available.", 404)
    extension = Path(filename).suffix.lower()
    if extension in UNSAFE_EXTENSIONS: raise EvidenceIntakeError("unsafe_file", "This file type cannot be uploaded.", 415)
    if extension not in SUPPORTED: raise EvidenceIntakeError("unsupported_file", "This file type is not supported.", 415)
    if len(data) > settings.evidence_max_file_mb * 1024 * 1024: raise EvidenceIntakeError("file_too_large", f"Each file must be {settings.evidence_max_file_mb} MB or smaller.", 413)
    detected = detect_mime(data, extension)
    if detected not in SUPPORTED[extension]: raise EvidenceIntakeError("file_type_mismatch", "The file contents do not match the filename.", 415)
    _validate_decodable(data, detected, extension)
    digest = hashlib.sha256(data).hexdigest()
    with closing(_connect()) as db:
        existing = db.execute("SELECT * FROM assistant_evidence_uploads WHERE workspace_id=? AND sha256=?", (workspace_id, digest)).fetchone()
        if existing: return _public(existing, True)
    upload_id, now = str(uuid4()), _now(); safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)[:180] or f"evidence{extension}"
    directory = UPLOAD_ROOT / workspace_id / upload_id; directory.mkdir(parents=True, exist_ok=False); path = directory / safe_name; path.write_bytes(data)
    extracted = _safe_text(data, extension)
    detail = "Ready for you to review." if extracted or detected.startswith("image/") or detected == "application/pdf" else "Uploaded and ready for review."
    provenance = {"original_filename": filename, "declared_mime_type": declared_mime, "detected_mime_type": detected, "sha256": digest,
                  "workspace_id": workspace_id, "user_id": user_id, "uploaded_at": now, "untrusted_evidence": True}
    with closing(_connect()) as db:
        db.execute("INSERT INTO assistant_evidence_uploads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            upload_id, workspace_id, user_id, conversation_id, restaurant_id, filename, declared_mime, detected, extension,
            len(data), digest, str(path), "ready_for_review", detail, extracted, None, json.dumps(provenance), now, now,
        )); db.commit(); row = db.execute("SELECT * FROM assistant_evidence_uploads WHERE id=?", (upload_id,)).fetchone()
    return _public(row)


def list_for_conversation(conversation_id: str, workspace_id: str) -> list[dict[str, Any]]:
    initialize()
    with closing(_connect()) as db:
        rows = db.execute("SELECT * FROM assistant_evidence_uploads WHERE conversation_id=? AND workspace_id=? ORDER BY uploaded_at DESC", (conversation_id, workspace_id)).fetchall()
    return [_public(row) for row in rows]


def get_upload(upload_id: str, workspace_id: str) -> dict[str, Any] | None:
    initialize()
    with closing(_connect()) as db:
        row = db.execute("SELECT * FROM assistant_evidence_uploads WHERE id=? AND workspace_id=?", (upload_id, workspace_id)).fetchone()
    if not row: return None
    return _public(row) | {
        "restaurant_id": row["restaurant_id"],
        "declared_mime_type": row["declared_mime_type"], "detected_mime_type": row["detected_mime_type"],
        "extension": row["file_extension"], "sha256": row["sha256"], "updated_at": row["updated_at"],
        "text_preview": (row["extracted_text"] or "")[:8000] or None,
        "content_url": f"/backend-api/api/assistant/evidence-uploads/{row['id']}/content",
    }


def upload_path(upload_id: str, workspace_id: str) -> tuple[Path, str, str] | None:
    initialize()
    with closing(_connect()) as db:
        row = db.execute("SELECT storage_path,detected_mime_type,original_filename FROM assistant_evidence_uploads WHERE id=? AND workspace_id=?", (upload_id, workspace_id)).fetchone()
    if not row: return None
    path = Path(row["storage_path"]).resolve()
    expected_root = UPLOAD_ROOT.resolve()
    if not path.is_file() or expected_root not in path.parents: return None
    return path, row["detected_mime_type"], row["original_filename"]


initialize()
