@router.post("/evidence-bundles/{bundle_id}/confirm")
def confirm_evidence_bundle(bundle_id: str, payload: AssistantEvidenceConfirm, workspace_id: str = Depends(get_workspace_id)) -> dict:
    try:
        return assistant_evidence_store.confirm_locations(bundle_id, workspace_id, payload.locations)
    except assistant_evidence_store.AssistantEvidenceError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)}) from exc
