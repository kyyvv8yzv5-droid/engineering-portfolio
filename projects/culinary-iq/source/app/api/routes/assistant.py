from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.workspace import get_workspace_id
from app.schemas.assistant import (
    AssistantCapabilities, AssistantContextEnvelope, AssistantContextUpdate, AssistantConversation, AssistantConversationCreate,
    AssistantEvidenceBundle, AssistantEvidenceConfirm, AssistantEvidenceUploadResult, AssistantMessageSend, AssistantSendResult,
)
from app.services import assistant_store
from app.services import assistant_evidence_store
from app.services import evidence_intake
from app.services.assistant_manual import (
    INDEX_PIN_PATH, ManualValidationError, list_manual_index_versions, load_manual_index, preview_manual_source,
    rebuild_manual_index, rollback_manual_index, search_manual,
)
from app.services.assistant_service import AssistantError, send_message
from app.services.assistant_tools import TOOL_DEFINITIONS, feature_capabilities
from app.services.restaurant_directory_store import restaurant_directory


router = APIRouter()


def _development_only() -> None:
    if settings.environment.lower() != "development":
        raise HTTPException(404, detail={"code": "not_available", "message": "Manual development tools are not available."})


def _error(error: AssistantError) -> HTTPException:
    return HTTPException(status_code=error.status, detail={"code": error.code, "message": str(error)})


@router.get("/capabilities", response_model=AssistantCapabilities)
def capabilities() -> AssistantCapabilities:
    configured = feature_capabilities(); index = load_manual_index()
    return AssistantCapabilities(openai_configured=configured["openai_configured"], apple_maps_configured=configured["apple_maps_configured"], model=settings.assistant_model, manual_index_version=index.get("version"), tools=[item["function"]["name"] for item in TOOL_DEFINITIONS], evidence_max_file_mb=settings.evidence_max_file_mb, evidence_max_upload_mb=settings.evidence_max_upload_mb, evidence_max_files=settings.evidence_max_files_per_upload)


@router.post("/conversations", response_model=AssistantConversation, status_code=status.HTTP_201_CREATED)
def create_conversation(payload: AssistantConversationCreate, workspace_id: str = Depends(get_workspace_id)) -> dict:
    return assistant_store.create_conversation(workspace_id, payload.title, payload.context.model_dump(mode="json"))


@router.get("/conversations", response_model=list[AssistantConversation])
def list_conversations(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0), workspace_id: str = Depends(get_workspace_id)) -> list[dict]:
    return assistant_store.list_conversations(workspace_id, limit, offset)


@router.get("/conversations/{conversation_id}", response_model=AssistantConversation)
def get_conversation(conversation_id: str, workspace_id: str = Depends(get_workspace_id)) -> dict:
    conversation = assistant_store.get_conversation(conversation_id, workspace_id, settings.assistant_history_limit * 2)
    if not conversation: raise HTTPException(404, detail={"code": "conversation_not_found", "message": "This conversation was not found."})
    return conversation


@router.post("/conversations/{conversation_id}/messages", response_model=AssistantSendResult)
async def create_message(conversation_id: str, payload: AssistantMessageSend, workspace_id: str = Depends(get_workspace_id)) -> AssistantSendResult:
    try: message, diagnostics = await send_message(conversation_id, workspace_id, payload.content, payload.context)
    except AssistantError as exc: raise _error(exc) from exc
    conversation = assistant_store.get_conversation(conversation_id, workspace_id, settings.assistant_history_limit * 2)
    return AssistantSendResult(conversation=conversation, message=message, retrieval_diagnostics=diagnostics if settings.environment.lower() == "development" else None)


@router.post("/conversations/{conversation_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_conversation(conversation_id: str, workspace_id: str = Depends(get_workspace_id)) -> Response:
    if not assistant_store.archive_conversation(conversation_id, workspace_id): raise HTTPException(404, detail={"code": "conversation_not_found", "message": "This conversation was not found."})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/conversations/{conversation_id}/context", status_code=status.HTTP_204_NO_CONTENT)
def update_conversation_context(conversation_id: str, payload: AssistantContextUpdate, workspace_id: str = Depends(get_workspace_id)) -> Response:
    context = payload.context.model_dump(mode="json")
    restaurant_id = context.get("selected_restaurant_id")
    if restaurant_id and not restaurant_directory.get(restaurant_id, workspace_id):
        raise HTTPException(404, detail={"code": "restaurant_not_found", "message": "The selected restaurant is no longer available."})
    if not assistant_store.update_conversation_context(conversation_id, workspace_id, context):
        raise HTTPException(404, detail={"code": "conversation_not_found", "message": "This conversation was not found."})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/conversations/{conversation_id}/evidence", response_model=AssistantEvidenceUploadResult)
async def upload_evidence(
    conversation_id: str, files: list[UploadFile] = File(...), restaurant_id: str | None = None,
    x_rmh_user: str = Header(default="local-user"), workspace_id: str = Depends(get_workspace_id),
) -> dict:
    if not files or len(files) > settings.evidence_max_files_per_upload:
        raise HTTPException(413, detail={"code": "too_many_files", "message": f"Choose up to {settings.evidence_max_files_per_upload} files at a time."})
    results: list[dict] = []; total = 0
    for upload in files:
        data = await upload.read(settings.evidence_max_file_mb * 1024 * 1024 + 1)
        total += len(data)
        if total > settings.evidence_max_upload_mb * 1024 * 1024:
            results.append({"filename": upload.filename or "file", "mime_type": upload.content_type, "size": len(data), "status": "failed", "message": f"The total upload must be {settings.evidence_max_upload_mb} MB or smaller."})
            continue
        try:
            results.append(evidence_intake.accept(workspace_id=workspace_id, user_id=x_rmh_user[:100], conversation_id=conversation_id,
                restaurant_id=restaurant_id, filename=upload.filename or "file", declared_mime=upload.content_type, data=data))
        except evidence_intake.EvidenceIntakeError as exc:
            results.append({"filename": upload.filename or "file", "mime_type": upload.content_type, "size": len(data),
                            "status": "unsupported" if exc.status == 415 else "failed", "message": str(exc)})
        finally:
            await upload.close()
    accepted = sum(item["status"] == "ready_for_review" for item in results)
    return {"files": results, "accepted": accepted, "rejected": len(results) - accepted}


@router.get("/conversations/{conversation_id}/evidence", response_model=list[dict])
def conversation_evidence(conversation_id: str, workspace_id: str = Depends(get_workspace_id)) -> list[dict]:
    return evidence_intake.list_for_conversation(conversation_id, workspace_id)


@router.get("/evidence-uploads/{upload_id}")
def uploaded_evidence(upload_id: str, workspace_id: str = Depends(get_workspace_id)) -> dict:
    item = evidence_intake.get_upload(upload_id, workspace_id)
    if not item: raise HTTPException(404, detail={"code":"evidence_upload_not_found","message":"This uploaded evidence is no longer available."})
    return item


@router.get("/evidence-uploads/{upload_id}/content")
def uploaded_evidence_content(upload_id: str, workspace_id: str = Depends(get_workspace_id)) -> FileResponse:
    item = evidence_intake.upload_path(upload_id, workspace_id)
    if not item: raise HTTPException(404, detail={"code":"evidence_upload_not_found","message":"This uploaded evidence is no longer available."})
    path, mime_type, filename = item
    return FileResponse(path, media_type=mime_type, filename=filename, content_disposition_type="inline")


@router.get("/evidence-bundles", response_model=list[AssistantEvidenceBundle])
def pending_evidence_bundles(restaurant_id: str | None = None, workspace_id: str = Depends(get_workspace_id)) -> list[dict]:
    if restaurant_id and not restaurant_directory.get(restaurant_id, workspace_id):
        raise HTTPException(404, detail={"code": "restaurant_not_found", "message": "The selected restaurant is no longer available."})
    return assistant_evidence_store.list_pending(workspace_id, restaurant_id)


@router.get("/evidence-bundles/{bundle_id}", response_model=AssistantEvidenceBundle)
def evidence_bundle(bundle_id: str, workspace_id: str = Depends(get_workspace_id)) -> dict:
    bundle = assistant_evidence_store.get_bundle(bundle_id, workspace_id)
    if not bundle:
        raise HTTPException(404, detail={"code": "evidence_bundle_not_found", "message": "These pending changes are no longer available."})
    return bundle


@router.post("/evidence-bundles/{bundle_id}/confirm")
def confirm_evidence_bundle(bundle_id: str, payload: AssistantEvidenceConfirm, workspace_id: str = Depends(get_workspace_id)) -> dict:
    try:
        return assistant_evidence_store.confirm_locations(bundle_id, workspace_id, payload.locations)
    except assistant_evidence_store.AssistantEvidenceError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)}) from exc


@router.delete("/evidence-bundles/{bundle_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_evidence_bundle(bundle_id: str, workspace_id: str = Depends(get_workspace_id)) -> Response:
    if not assistant_evidence_store.discard_bundle(bundle_id, workspace_id):
        raise HTTPException(404, detail={"code": "evidence_bundle_not_found", "message": "These pending changes are no longer available."})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/manual/search")
def manual_diagnostics(query: str = Query(min_length=1, max_length=500), context: AssistantContextEnvelope | None = None) -> dict:
    _development_only()
    supplied = context or AssistantContextEnvelope()
    chunks, diagnostics = search_manual(query, route=supplied.current_route, feature=supplied.feature)
    return {"diagnostics": diagnostics, "results": [{key: item.get(key) for key in ("document_id", "title", "section", "version", "status", "score", "retrieval_eligible")} for item in chunks]}


@router.get("/manual/preview")
def manual_preview() -> dict:
    _development_only()
    preview = preview_manual_source()
    current = load_manual_index()
    return preview | {
        "current_index_version": current.get("version"),
        "last_indexed_at": current.get("indexed_at"),
        "source_changed": preview.get("source_fingerprint") != current.get("source_fingerprint"),
        "rollback_pinned": INDEX_PIN_PATH.exists(),
        "available_versions": list_manual_index_versions(),
    }


@router.post("/manual/validate")
def validate_manual() -> dict:
    _development_only()
    return preview_manual_source()


@router.post("/manual/rebuild")
def rebuild_manual() -> dict:
    _development_only()
    try:
        payload = rebuild_manual_index()
    except ManualValidationError as error:
        raise HTTPException(422, detail={"code": "manual_validation_failed", "message": "Manual validation failed; the published index was not changed.", "issues": error.issues}) from error
    return {"version": payload["version"], "indexed_at": payload["indexed_at"], "document_count": payload["document_count"], "chunk_count": len(payload["chunks"])}


@router.get("/manual/versions")
def manual_versions() -> dict:
    _development_only()
    current = load_manual_index()
    return {"current_version": current.get("version"), "versions": list_manual_index_versions()}


@router.post("/manual/rollback/{version}")
def rollback_manual(version: str) -> dict:
    _development_only()
    try:
        payload = rollback_manual_index(version)
    except FileNotFoundError as error:
        raise HTTPException(404, detail={"code": "manual_index_version_not_found", "message": "That manual index version was not found."}) from error
    return {"version": payload.get("version"), "indexed_at": payload.get("indexed_at"), "document_count": payload.get("document_count")}
