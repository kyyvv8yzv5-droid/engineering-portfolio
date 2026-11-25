from picker import PickerConfig, PickerExtractionContextV1, PickerExtractionResultV1

from app.core.config import settings
from app.schemas.social_imports import (
    BoundingBox, ContentRegion, CropField, EngagementMetric, ExtractedComment, ListField,
    SocialScreenshotExtraction, TextField,
)


def picker_config() -> PickerConfig:
    return PickerConfig(
        api_key=settings.openai_api_key, fast_vision_model=settings.social_import_fast_model,
        fallback_vision_model=settings.social_import_fallback_model, model_timeout_seconds=settings.openai_timeout_seconds,
        maximum_upload_bytes=settings.social_import_max_upload_mb * 1024 * 1024,
        maximum_normalized_edge=settings.social_import_fast_max_dimension,
        fallback_maximum_edge=settings.social_import_fallback_max_dimension,
        image_detail=settings.social_import_fast_detail, fallback_image_detail=settings.social_import_fallback_detail,
        perceptual_duplicate_threshold=settings.social_near_duplicate_distance,
        crop_confidence_threshold=settings.social_import_fast_min_confidence,
        required_field_confidence_threshold=settings.social_import_fast_min_confidence,
        concurrency_limit=settings.social_import_concurrency, maximum_output_tokens=settings.social_import_max_output_tokens,
        normalization_quality=settings.social_import_normalization_quality,
        fallback_enabled=settings.social_import_fallback_enabled,
        prompt_version=settings.social_import_prompt_version,
        logging_level=settings.social_import_logging_level,
    )


def picker_context(catalog: list[dict], workspace_restaurant_id: str | None) -> PickerExtractionContextV1:
    ordered = sorted(catalog, key=lambda item: item["restaurant_id"] != workspace_restaurant_id)
    return PickerExtractionContextV1(
        platform_candidates=["Instagram", "Facebook"],
        account_candidates=[{"key": item["restaurant_id"], "name": item["name"], "handles": item["handles"], "locations": [*item["locations"], *item.get("aliases", [])]} for item in ordered],
        known_locations=[location for item in ordered for location in item["locations"]],
    )


def _box(value) -> BoundingBox | None:
    return None if value is None else BoundingBox(x=value.x, y=value.y, width=value.width, height=value.height)


def _text(value) -> TextField:
    return TextField(value=value.value, confidence=value.confidence.value, bounding_box=_box(value.bounding_box))


def _listed(value) -> ListField:
    return ListField(values=value.values, confidence=value.confidence.value, bounding_box=_box(value.bounding_box))


def picker_result_to_social(result: PickerExtractionResultV1) -> SocialScreenshotExtraction:
    region_types = {"authored_caption": "restaurant_post_caption", "authored_reply": "restaurant_reply", "customer_comment": "customer_comment", "interface": "social_platform_interface", "account": "account_metadata", "location": "location_metadata", "engagement": "engagement_metadata", "watermark": "social_platform_interface"}
    comment = lambda item: ExtractedComment(author_type="restaurant" if item.author_type == "content_owner" else item.author_type, author_name=item.author_name, comment_text=item.text, confidence=item.confidence.value, bounding_box=_box(item.bounding_box))
    return SocialScreenshotExtraction(
        platform=_text(result.detected_platform), restaurant_id_candidate=_text(result.account.candidate_key),
        account_name=_text(result.account.display_name), social_handle=_text(result.account.handle),
        post_caption=_text(result.authored_caption),
        post_image_crop=CropField(bounding_box=_box(result.primary_media_crop.bounding_box), confidence=result.primary_media_crop.confidence.value),
        location_name=_text(result.location.visible_location), city_state_address=_text(result.location.visible_address),
        approximate_post_date=_text(result.visible_date_text), hashtags=_listed(result.hashtags), mentions=_listed(result.mentions),
        calls_to_action=_listed(result.calls_to_action),
        engagement_metrics=[EngagementMetric(name=item.name, value=item.value, confidence=item.confidence.value) for item in result.engagement],
        menu_items=_listed(result.menu_items), dishes=_listed(result.dishes), offers=_listed(result.offers),
        event_references=_listed(result.event_references), phone_numbers=_listed(result.phone_numbers),
        website_domains=_listed(result.website_domains), reservation_links=_listed(result.reservation_links),
        delivery_links=_listed(result.delivery_links), brand_phrases=_listed(result.brand_phrases),
        restaurant_authored_replies=[comment(item) for item in result.authored_replies], customer_comments=[comment(item) for item in result.customer_comments],
        content_regions=[ContentRegion(content_type=region_types[item.region_type], text=item.text, confidence=item.confidence.value, bounding_box=_box(item.bounding_box)) for item in result.content_regions],
    )
