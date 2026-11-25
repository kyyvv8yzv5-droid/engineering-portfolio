from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AssistantCurrentFormContext(BaseModel):
    route: str = Field(max_length=300)
    form_type: str = Field(min_length=1, max_length=80)
    entity_type: str = Field(min_length=1, max_length=80)
    entity_id: str | None = Field(default=None, max_length=100)
    restaurant_id: str | None = Field(default=None, max_length=100)
    location_id: str | None = Field(default=None, max_length=100)
    visible_fields: list[str] = Field(default_factory=list, max_length=80)
    allowed_target_fields: list[str] = Field(default_factory=list, max_length=80)
    current_values: dict[str, Any] = Field(default_factory=dict)
    unsaved_values: dict[str, Any] = Field(default_factory=dict)


class AssistantContextEnvelope(BaseModel):
    selected_restaurant_id: str | None = Field(default=None, max_length=100)
    selected_restaurant_name: str | None = Field(default=None, max_length=200)
    selected_location_id: str | None = Field(default=None, max_length=100)
    current_route: str = Field(default="/", max_length=300)
    photo_iq_view: str | None = Field(default=None, max_length=80)
    open_surface: str | None = Field(default=None, max_length=120)
    feature: str | None = Field(default=None, max_length=80)
    unsaved_form: dict[str, Any] = Field(default_factory=dict)
    current_form: AssistantCurrentFormContext | None = None

    @field_validator("current_route")
    @classmethod
    def internal_route_only(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("current_route must be an internal application route")
        return value

    @field_validator("unsaved_form")
    @classmethod
    def bound_unsaved_form(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 30 or len(str(value)) > 6000:
            raise ValueError("unsaved_form context is too large")
        return value


class AssistantConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    context: AssistantContextEnvelope = Field(default_factory=AssistantContextEnvelope)


class AssistantMessageSend(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    context: AssistantContextEnvelope = Field(default_factory=AssistantContextEnvelope)


class AssistantContextUpdate(BaseModel):
    context: AssistantContextEnvelope


class AssistantAction(BaseModel):
    action_type: Literal[
        "open_internal_route", "open_evidence_review", "review_pending_locations",
        "continue_import", "discard_pending_evidence", "apply_picker_to_current_form",
    ] = "open_internal_route"
    label: str = Field(max_length=80)
    route: str | None = Field(default=None, max_length=300)
    evidence_bundle_id: str | None = Field(default=None, max_length=100)


class AssistantMessage(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    response_status: str
    model: str | None = None
    navigation: list[AssistantAction] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class AssistantConversation(BaseModel):
    id: str
    title: str | None = None
    selected_restaurant_id: str | None = None
    selected_location_id: str | None = None
    route_context: str | None = None
    archived: bool
    created_at: datetime
    updated_at: datetime
    messages: list[AssistantMessage] = Field(default_factory=list)


class AssistantSendResult(BaseModel):
    conversation: AssistantConversation
    message: AssistantMessage
    retrieval_diagnostics: dict[str, Any] | None = None


class AssistantCapabilities(BaseModel):
    openai_configured: bool
    apple_maps_configured: bool
    model: str
    manual_index_version: str | None = None
    tools: list[str]
    evidence_max_file_mb: int = 20
    evidence_max_upload_mb: int = 50
    evidence_max_files: int = 12


class AssistantEvidenceUpload(BaseModel):
    id: str | None = None
    filename: str
    mime_type: str | None = None
    size: int
    status: Literal["uploaded", "inspecting", "extracting", "ready_for_review", "unsupported", "failed"]
    message: str | None = None
    uploaded_at: datetime | None = None
    duplicate: bool = False
    review_route: str | None = None


class AssistantEvidenceUploadResult(BaseModel):
    files: list[AssistantEvidenceUpload]
    accepted: int
    rejected: int


class AssistantLocationEvidence(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    address_line_1: str | None = Field(default=None, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default=None, max_length=100)
    formatted_address: str | None = Field(default=None, max_length=400)
    phone: str | None = Field(default=None, max_length=60)
    website: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, max_length=100)
    hours: list[dict[str, Any]] = Field(default_factory=list, max_length=21)
    source_references: list[str] = Field(default_factory=list, max_length=10)


class AssistantEvidencePrepare(BaseModel):
    restaurant_id: str = Field(min_length=1, max_length=100)
    locations: list[AssistantLocationEvidence] = Field(min_length=1, max_length=10)
    source_origin: Literal[
        "user_supplied_chat_text", "assistant_inference", "stored_culinary_iq_data",
        "configured_maps_provider", "website_provider",
    ]
    raw_supplied_text: str | None = Field(default=None, max_length=8000)
    idempotency_key: str = Field(min_length=8, max_length=180)


class AssistantEvidenceItem(BaseModel):
    id: str
    entity_index: int
    field_name: str
    value: Any
    raw_supplied_text: str | None = None
    confidence: float
    confidence_basis: str
    verification_status: str
    source_references: list[str] = Field(default_factory=list)
    provenance_chain: list[dict[str, Any]] = Field(default_factory=list)


class AssistantEvidenceBundle(BaseModel):
    id: str
    restaurant_id: str | None
    conversation_id: str
    bundle_type: str
    source_type: str
    source_origin: str
    source_label: str
    status: str
    model: str | None = None
    locations: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    duplicate_warnings: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AssistantEvidenceConfirm(BaseModel):
    locations: list[AssistantLocationEvidence] = Field(min_length=1, max_length=10)
