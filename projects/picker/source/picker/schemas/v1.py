from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class PickerDimensionsV1(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class PickerBoundingBoxV1(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class PickerConfidenceV1(BaseModel):
    value: float = Field(ge=0, le=1)
    source: str = "vision"


class PickerTextRegionV1(BaseModel):
    value: str | None
    confidence: PickerConfidenceV1
    bounding_box: PickerBoundingBoxV1 | None = None


class PickerListRegionV1(BaseModel):
    values: list[str]
    confidence: PickerConfidenceV1
    bounding_box: PickerBoundingBoxV1 | None = None


class PickerContentRegionV1(BaseModel):
    region_type: Literal["authored_caption", "authored_reply", "customer_comment", "interface", "account", "location", "engagement", "watermark"]
    text: str
    confidence: PickerConfidenceV1
    bounding_box: PickerBoundingBoxV1 | None = None


class PickerClassifiedTextV1(BaseModel):
    author_type: Literal["content_owner", "customer", "unknown"]
    author_name: str | None = None
    text: str
    confidence: PickerConfidenceV1
    bounding_box: PickerBoundingBoxV1 | None = None


class PickerCropV1(BaseModel):
    bounding_box: PickerBoundingBoxV1
    confidence: PickerConfidenceV1


class PickerAccountMetadataV1(BaseModel):
    display_name: PickerTextRegionV1
    handle: PickerTextRegionV1
    candidate_key: PickerTextRegionV1


class PickerLocationMetadataV1(BaseModel):
    visible_location: PickerTextRegionV1
    visible_address: PickerTextRegionV1


class PickerEngagementMetadataV1(BaseModel):
    name: str
    value: str
    confidence: PickerConfidenceV1


class PickerProvenanceV1(BaseModel):
    request_id: str
    source_asset_reference: str | None
    source_type: str
    provider: str
    model: str
    prompt_version: str
    package_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PickerProcessingMetricsV1(BaseModel):
    normalization_ms: int = 0
    hashing_ms: int = 0
    candidate_preparation_ms: int = 0
    openai_connection_ms: int = 0
    model_response_ms: int = 0
    structured_parse_ms: int = 0
    crop_creation_ms: int = 0
    total_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    request_bytes: int = 0
    image_detail: str = ""
    fallback_used: bool = False
    fallback_reasons: list[str] = Field(default_factory=list)


class PickerExtractionContextV1(BaseModel):
    platform_candidates: list[str] = Field(default_factory=lambda: ["Instagram", "Facebook"])
    account_candidates: list[dict[str, Any]] = Field(default_factory=list)
    known_locations: list[str] = Field(default_factory=list)


class PickerExtractionRequestV1(BaseModel):
    image_bytes: bytes
    source_asset_reference: str | None = None
    source_type: str = "screenshot"
    request_id: str | None = None
    context: PickerExtractionContextV1 = Field(default_factory=PickerExtractionContextV1)


class PickerBulkExtractionRequestV1(BaseModel):
    requests: list[PickerExtractionRequestV1] = Field(min_length=1)


class PickerExtractionResultV1(BaseModel):
    source_asset_reference: str | None
    source_type: str
    detected_platform: PickerTextRegionV1
    original_dimensions: PickerDimensionsV1
    normalized_dimensions: PickerDimensionsV1
    content_regions: list[PickerContentRegionV1]
    text_regions: list[PickerTextRegionV1]
    primary_media_crop: PickerCropV1
    account: PickerAccountMetadataV1
    location: PickerLocationMetadataV1
    visible_date_text: PickerTextRegionV1
    authored_caption: PickerTextRegionV1
    hashtags: PickerListRegionV1
    mentions: PickerListRegionV1
    calls_to_action: PickerListRegionV1
    links: PickerListRegionV1
    website_domains: PickerListRegionV1
    reservation_links: PickerListRegionV1
    delivery_links: PickerListRegionV1
    phone_numbers: PickerListRegionV1
    engagement: list[PickerEngagementMetadataV1]
    menu_items: PickerListRegionV1
    dishes: PickerListRegionV1
    offers: PickerListRegionV1
    event_references: PickerListRegionV1
    brand_phrases: PickerListRegionV1
    authored_replies: list[PickerClassifiedTextV1]
    customer_comments: list[PickerClassifiedTextV1]
    interface_text: list[str]
    exact_hash: str
    perceptual_hash: str
    model: str
    prompt_version: str
    package_version: str
    image_detail: str
    fallback_used: bool
    fallback_reasons: list[str]
    provenance: PickerProvenanceV1
    processing_metrics: PickerProcessingMetricsV1
    review_recommendation: Literal["accept", "review"]


class PickerCorrectionV1(BaseModel):
    field_name: str
    original_value: Any
    corrected_value: Any
    reason: str | None = None


class PickerReviewDecisionV1(BaseModel):
    decision: Literal["accepted", "rejected", "corrected"]
    corrections: list[PickerCorrectionV1] = Field(default_factory=list)
    reviewer_reference: str | None = None


class PickerVideoInputV1(BaseModel):
    source_path: str
    source_asset_reference: str | None = None
    source_sha256: str | None = None
    extraction_directory: str


class PickerVideoMetadataV1(BaseModel):
    duration_seconds: float
    width: int
    height: int
    frame_rate: float
    codec: str
    container: str | None = None
    total_source_frames: int | None = None


class PickerFrameMetricsV1(BaseModel):
    sharpness: float
    blur_score: float
    brightness: float
    contrast: float
    visual_change_score: float
    stability_score: float
    frame_quality_score: float


class PickerFrameSampleV1(BaseModel):
    frame_id: str
    frame_index: int
    timestamp_ms: int
    timestamp_seconds: float
    extraction_method: str = "ffmpeg_interval_v1"
    width: int
    height: int
    perceptual_hash: str
    exact_hash: str
    duplicate_cluster_id: str | None = None
    selection_reason: str | None = None
    artifact_reference: str
    metrics: PickerFrameMetricsV1
    warnings: list[str] = Field(default_factory=list)


class PickerFrameCandidateV1(PickerFrameSampleV1):
    selected: bool = True


class PickerFrameClusterV1(BaseModel):
    cluster_id: str
    frame_ids: list[str]
    representative_frame_id: str
    probable_revisit: bool = False


class PickerFrameDiagnosticV1(BaseModel):
    frame_id: str
    frame_index: int
    timestamp_ms: int
    metrics: PickerFrameMetricsV1
    perceptual_hash_cluster: str | None = None
    retained: bool
    selection_reason: str | None = None
    rejection_reason: str | None = None
    stable_window_id: str | None = None
    post_candidate_id: str | None = None
    representative_rank: int | None = None
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    grouping_confidence: float | None = Field(default=None, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class PickerPostCandidateV1(BaseModel):
    candidate_id: str
    ordered_frame_ids: list[str]
    representative_frame_id: str
    start_timestamp_ms: int
    end_timestamp_ms: int
    grouping_confidence: float
    platform_hypothesis: Literal["instagram", "facebook", "tiktok", "google_business_profile", "unknown"] = "unknown"
    content_type_hypothesis: str = "social_post"
    ocr_result: dict[str, Any] | None = None
    visual_extraction_result: dict[str, Any] | None = None
    extracted_caption_text: str | None = None
    extracted_username_or_page_name: str | None = None
    extracted_post_date: str | None = None
    extracted_engagement_metrics: list[dict[str, Any]] = Field(default_factory=list)
    detected_menu_items: list[str] = Field(default_factory=list)
    detected_promotional_text: list[str] = Field(default_factory=list)
    detected_calls_to_action: list[str] = Field(default_factory=list)
    detected_hashtags: list[str] = Field(default_factory=list)
    detected_pricing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    review_required: bool = True
    grouping_reasons: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class PickerVideoProcessingMetricsV1(BaseModel):
    probe_ms: int = 0
    ffmpeg_ms: int = 0
    total_ms: int = 0
    sampled_frames: int = 0
    stable_windows: int = 0
    selected_frames: int = 0
    duplicate_clusters: int = 0
    post_candidates: int = 0
    estimated_provider_calls: int = 0
    warnings: list[str] = Field(default_factory=list)


class PickerVideoAnalysisV1(BaseModel):
    schema_version: Literal["picker-video-v1"] = "picker-video-v1"
    source_asset_reference: str | None = None
    source_sha256: str | None = None
    metadata: PickerVideoMetadataV1
    frames: list[PickerFrameCandidateV1]
    clusters: list[PickerFrameClusterV1]
    post_candidates: list[PickerPostCandidateV1]
    processing_metrics: PickerVideoProcessingMetricsV1
    frame_diagnostics: list[PickerFrameDiagnosticV1] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


PickerRestaurantSourceV1 = Literal["apple_maps","google_maps","restaurant_website","facebook_about","yelp","reservation_platform","delivery_platform","menu_or_contact_page","unknown"]

class PickerRestaurantScreenshotInputV1(BaseModel):
    screenshot_id: str
    image_bytes: bytes = Field(repr=False)
    visible_text_hint: str | None = None

class PickerRestaurantSourceHypothesisV1(BaseModel):
    source: PickerRestaurantSourceV1 = "unknown"
    confidence: float = Field(default=0,ge=0,le=1)
    evidence: list[str] = Field(default_factory=list)

class PickerRestaurantFieldEvidenceV1(BaseModel):
    field_name: str
    source_screenshot_id: str
    raw_ocr_text: str | None = None
    normalized_value: str | None = None
    crop_coordinates: PickerBoundingBoxV1 | None = None
    source_hypothesis: PickerRestaurantSourceV1 = "unknown"
    confidence: float = Field(default=0,ge=0,le=1)
    extraction_provider: str = "local"
    extraction_model: str = "picker-restaurant-local-v1"
    extraction_version: str = "picker-restaurant-v1"
    observation_only: bool = False

class PickerRestaurantLocationEvidenceV1(PickerRestaurantFieldEvidenceV1): pass
class PickerRestaurantHoursEvidenceV1(PickerRestaurantFieldEvidenceV1): pass
class PickerRestaurantSocialEvidenceV1(PickerRestaurantFieldEvidenceV1): pass

class PickerRestaurantScreenshotAnalysisV1(BaseModel):
    schema_version: Literal["picker-restaurant-v1"] = "picker-restaurant-v1"
    screenshot_id: str
    source_hypothesis: PickerRestaurantSourceHypothesisV1
    fields: list[PickerRestaurantFieldEvidenceV1] = Field(default_factory=list)
    excluded_customer_review_text: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class PickerRestaurantConflictV1(BaseModel):
    field_name: str
    values: list[str]
    evidence_ids: list[str]
    requires_review: bool = True

class PickerRestaurantEvidenceBundleV1(BaseModel):
    schema_version: Literal["picker-restaurant-bundle-v1"] = "picker-restaurant-bundle-v1"
    analyses: list[PickerRestaurantScreenshotAnalysisV1]
    fields: dict[str,list[PickerRestaurantFieldEvidenceV1]] = Field(default_factory=dict)
    proposed_values: dict[str,str] = Field(default_factory=dict)
    conflicts: list[PickerRestaurantConflictV1] = Field(default_factory=list)
    overall_confidence: float = Field(default=0,ge=0,le=1)
    warnings: list[str] = Field(default_factory=list)
