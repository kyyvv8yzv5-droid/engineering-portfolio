import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol
from uuid import uuid4

from picker.config import PickerConfig
from picker.exceptions import PickerStructuredOutputError
from picker.hashing import calculate_hashes
from picker.processors.image import PreparedScreenshot, encode_for_edge, normalize_screenshot, refine_crop_to_visible_edges, remap_box, validate_crop
from picker.providers import OpenAIVisionProvider, PickerVisionProvider, ProviderResponse
from picker.providers.openai import Comment, CompactExtraction
from picker.schemas import (
    PickerAccountMetadataV1, PickerBoundingBoxV1, PickerBulkExtractionRequestV1,
    PickerClassifiedTextV1, PickerConfidenceV1, PickerContentRegionV1, PickerCropV1,
    PickerDimensionsV1, PickerEngagementMetadataV1, PickerExtractionRequestV1,
    PickerExtractionResultV1, PickerListRegionV1, PickerLocationMetadataV1,
    PickerProcessingMetricsV1, PickerProvenanceV1, PickerTextRegionV1,
)
from picker.version import get_package_version


class MetricsRecorder(Protocol):
    def __call__(self, name: str, value: float, attributes: dict) -> None: ...


@dataclass
class PickerDependencies:
    vision_provider: PickerVisionProvider | None = None
    storage_adapter: object | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    id_generator: Callable[[], str] = lambda: str(uuid4())
    metrics_recorder: MetricsRecorder | None = None


REGION_TYPES = {"caption": "authored_caption", "reply": "authored_reply", "comment": "customer_comment", "interface": "interface", "account": "account", "location": "location", "engagement": "engagement", "watermark": "watermark"}


def _box(value) -> PickerBoundingBoxV1 | None:
    return None if value is None else PickerBoundingBoxV1(x=value.x, y=value.y, width=value.w, height=value.h)


def _confidence(value: float) -> PickerConfidenceV1:
    return PickerConfidenceV1(value=value)


def _text(value) -> PickerTextRegionV1:
    return PickerTextRegionV1(value=value.v, confidence=_confidence(value.c), bounding_box=_box(value.b))


def _listed(value) -> PickerListRegionV1:
    return PickerListRegionV1(values=value.v, confidence=_confidence(value.c), bounding_box=_box(value.b))


def _fallback_reasons(value: CompactExtraction, config: PickerConfig) -> list[str]:
    reasons: list[str] = []
    for name, field in (("platform", value.pf), ("caption", value.caption)):
        if not field.v: reasons.append(f"missing_{name}")
        elif field.c < config.required_field_confidence_threshold: reasons.append(f"low_{name}_confidence")
    crop = _box(value.image.b)
    if value.image.c < config.crop_confidence_threshold: reasons.append("low_crop_confidence")
    if crop is None or not validate_crop(crop): reasons.append("invalid_crop")
    return reasons


def _reconcile_classification(value: CompactExtraction, context: dict) -> None:
    region_comments = [item for item in value.regions if item.t == "comment"]
    known = {item.v.strip().lower() for item in value.comments}
    for region in region_comments:
        normalized = region.v.strip().lower()
        if normalized not in known:
            value.comments.append(Comment(t="customer", n=None, v=region.v, c=region.c, b=region.b)); known.add(normalized)
    customer_texts = {item.v.strip().lower() for item in value.comments if item.v.strip()}
    owner_identity = " ".join(filter(None, (value.acct.v, value.handle.v))).lower()
    retained_replies = []
    for item in value.replies:
        normalized = item.v.strip().lower()
        duplicates_customer = any(normalized in text or text in normalized for text in customer_texts)
        wrong_author = bool(item.n and item.n.strip().lower() not in owner_identity)
        if item.t == "customer" or duplicates_customer or wrong_author:
            if not duplicates_customer:
                item.t = "customer"; value.comments.append(item); customer_texts.add(normalized)
        else: retained_replies.append(item)
    value.replies = retained_replies
    if value.caption.v:
        caption = value.caption.v
        trailing_comment = re.search(r"(?:^|\n|(?<=[.!?])\s+)([A-Za-z][A-Za-z0-9_. ]{0,30}):\s+([^#\n]+)$", caption)
        if trailing_comment:
            full_text = trailing_comment.group(0).strip()
            value.comments.append(Comment(t="customer", n=trailing_comment.group(1), v=trailing_comment.group(2).strip(), c=value.caption.c, b=None))
            caption = caption[:trailing_comment.start()].strip()
        for item in value.comments:
            if item.v and item.v.lower() in caption.lower():
                start = caption.lower().find(item.v.lower()); caption = (caption[:start] + caption[start + len(item.v):]).strip(" \n:-")
        value.caption.v = caption or None
    for field in (value.loc, value.address):
        if field.v and field.b is None:
            field.v = None; field.c = 0.0


def _remap_result_boxes(result: PickerExtractionResultV1, prepared: PreparedScreenshot) -> None:
    for field in [result.detected_platform, result.account.display_name, result.account.handle, result.account.candidate_key,
                  result.location.visible_location, result.location.visible_address, result.visible_date_text,
                  result.authored_caption, result.hashtags, result.mentions, result.calls_to_action, result.links,
                  result.phone_numbers, result.menu_items, result.dishes, result.offers, result.event_references, result.brand_phrases]:
        field.bounding_box = remap_box(field.bounding_box, prepared)
    result.primary_media_crop.bounding_box = remap_box(result.primary_media_crop.bounding_box, prepared)
    for field in [*result.content_regions, *result.authored_replies, *result.customer_comments, *result.text_regions]:
        field.bounding_box = remap_box(field.bounding_box, prepared)


def _to_result(value: CompactExtraction, request: PickerExtractionRequestV1, prepared: PreparedScreenshot, response: ProviderResponse,
               exact_hash: str, perceptual_hash: str, config: PickerConfig, dependencies: PickerDependencies,
               metrics: PickerProcessingMetricsV1, fallback_reasons: list[str]) -> PickerExtractionResultV1:
    comment = lambda item: PickerClassifiedTextV1(author_type="content_owner" if item.t == "restaurant" else item.t, author_name=item.n, text=item.v, confidence=_confidence(item.c), bounding_box=_box(item.b))
    content_regions = [PickerContentRegionV1(region_type=REGION_TYPES[item.t], text=item.v, confidence=_confidence(item.c), bounding_box=_box(item.b)) for item in value.regions]
    links = [*value.domains.v, *value.reservation.v, *value.delivery.v]
    link_confidence = max(value.domains.c, value.reservation.c, value.delivery.c)
    refined_crop = refine_crop_to_visible_edges(prepared.trimmed, _box(value.image.b))
    result = PickerExtractionResultV1(
        source_asset_reference=request.source_asset_reference, source_type=request.source_type,
        detected_platform=_text(value.pf), original_dimensions=PickerDimensionsV1(width=prepared.original.width, height=prepared.original.height),
        normalized_dimensions=PickerDimensionsV1(width=prepared.normalized_size[0], height=prepared.normalized_size[1]),
        content_regions=content_regions, text_regions=[_text(item) for item in (value.pf, value.acct, value.handle, value.caption, value.loc, value.address, value.date)],
        primary_media_crop=PickerCropV1(bounding_box=refined_crop, confidence=_confidence(value.image.c)),
        account=PickerAccountMetadataV1(display_name=_text(value.acct), handle=_text(value.handle), candidate_key=_text(value.candidate)),
        location=PickerLocationMetadataV1(visible_location=_text(value.loc), visible_address=_text(value.address)),
        visible_date_text=_text(value.date), authored_caption=_text(value.caption), hashtags=_listed(value.hashtags),
        mentions=_listed(value.mentions), calls_to_action=_listed(value.cta),
        links=PickerListRegionV1(values=links, confidence=_confidence(link_confidence)),
        website_domains=_listed(value.domains), reservation_links=_listed(value.reservation), delivery_links=_listed(value.delivery),
        phone_numbers=_listed(value.phones),
        engagement=[PickerEngagementMetadataV1(name=item.n, value=item.v, confidence=_confidence(item.c)) for item in value.engagement],
        menu_items=_listed(value.menu), dishes=_listed(value.dishes), offers=_listed(value.offers), event_references=_listed(value.events),
        brand_phrases=_listed(value.phrases), authored_replies=[comment(item) for item in value.replies],
        customer_comments=[comment(item) for item in value.comments],
        interface_text=[item.text for item in content_regions if item.region_type == "interface"], exact_hash=exact_hash,
        perceptual_hash=perceptual_hash, model=response.model, prompt_version=config.prompt_version,
        package_version=get_package_version(), image_detail=response.image_detail, fallback_used=metrics.fallback_used,
        fallback_reasons=fallback_reasons,
        provenance=PickerProvenanceV1(request_id=request.request_id or "", source_asset_reference=request.source_asset_reference,
            source_type=request.source_type, provider="openai-compatible", model=response.model,
            prompt_version=config.prompt_version, package_version=get_package_version(), created_at=dependencies.clock()),
        processing_metrics=metrics,
        review_recommendation="review" if fallback_reasons else "accept",
    )
    _remap_result_boxes(result, prepared)
    return result


async def extract_screenshot(*, image_bytes: bytes | None = None, context=None, request: PickerExtractionRequestV1 | None = None,
                             config: PickerConfig | None = None, dependencies: PickerDependencies | None = None,
                             prepared: PreparedScreenshot | None = None,
                             precomputed_hashes: tuple[str, str] | None = None) -> PickerExtractionResultV1:
    config = config or PickerConfig()
    dependencies = dependencies or PickerDependencies()
    if request is None:
        request = PickerExtractionRequestV1(image_bytes=image_bytes or b"", context=context or {})
    if not request.request_id:
        request.request_id = dependencies.id_generator()
    total_started = time.perf_counter()
    prepared = prepared or normalize_screenshot(request.image_bytes, config)
    hash_started = time.perf_counter()
    exact_hash, phash = precomputed_hashes or calculate_hashes(request.image_bytes, prepared.original)
    hashing_ms = 0 if precomputed_hashes else round((time.perf_counter() - hash_started) * 1000)
    candidate_started = time.perf_counter()
    provider_context = request.context.model_dump(mode="json")
    candidate_ms = round((time.perf_counter() - candidate_started) * 1000)
    provider = dependencies.vision_provider or OpenAIVisionProvider(config)
    reasons: list[str] = []
    first_response: ProviderResponse | None = None
    try:
        response = await provider.extract(image_bytes=prepared.normalized_bytes, context=provider_context, request_id=request.request_id,
            model=config.fast_vision_model, detail=config.image_detail, maximum_output_tokens=config.maximum_output_tokens)
        first_response = response
        reasons = _fallback_reasons(response.extraction, config)
    except PickerStructuredOutputError:
        reasons = ["structured_validation_failed"]
        response = None
    if reasons and config.fallback_enabled:
        fallback_bytes, fallback_size = encode_for_edge(prepared, config.fallback_maximum_edge, config.normalization_quality)
        response = await provider.extract(image_bytes=fallback_bytes, context=provider_context, request_id=request.request_id + "-fallback",
            model=config.fallback_vision_model, detail=config.fallback_image_detail, maximum_output_tokens=config.maximum_output_tokens)
        prepared.normalized_size = fallback_size
        if first_response:
            response.connection_ms += first_response.connection_ms; response.response_ms += first_response.response_ms
            response.parse_ms += first_response.parse_ms; response.input_tokens += first_response.input_tokens
            response.output_tokens += first_response.output_tokens; response.request_bytes += first_response.request_bytes
    if response is None:
        raise PickerStructuredOutputError("Picker extraction failed structured validation and fallback is disabled")
    _reconcile_classification(response.extraction, provider_context)
    metrics = PickerProcessingMetricsV1(
        normalization_ms=prepared.normalization_ms, hashing_ms=hashing_ms, candidate_preparation_ms=candidate_ms,
        openai_connection_ms=response.connection_ms, model_response_ms=response.response_ms, structured_parse_ms=response.parse_ms,
        total_ms=round((time.perf_counter() - total_started) * 1000), input_tokens=response.input_tokens,
        output_tokens=response.output_tokens, request_bytes=response.request_bytes, image_detail=response.image_detail,
        fallback_used=bool(reasons and config.fallback_enabled), fallback_reasons=reasons,
    )
    result = _to_result(response.extraction, request, prepared, response, exact_hash, phash, config, dependencies, metrics, reasons)
    if dependencies.metrics_recorder:
        dependencies.metrics_recorder("picker.extraction.total_ms", metrics.total_ms, {"model": response.model, "fallback": metrics.fallback_used})
    return result


async def extract_screenshots_bulk(request: PickerBulkExtractionRequestV1, *, config: PickerConfig | None = None,
                                   dependencies: PickerDependencies | None = None) -> list[PickerExtractionResultV1]:
    config = config or PickerConfig(); dependencies = dependencies or PickerDependencies()
    semaphore = asyncio.Semaphore(config.concurrency_limit)
    async def run(item):
        async with semaphore:
            return await extract_screenshot(request=item, config=config, dependencies=dependencies)
    return await asyncio.gather(*(run(item) for item in request.requests))
