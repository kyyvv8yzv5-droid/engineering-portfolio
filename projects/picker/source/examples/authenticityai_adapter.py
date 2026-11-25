"""Illustrative future adapter only; AuthenticityAI is not modified by Picker 0.1.0."""
from picker import PickerExtractionResultV1


def to_authenticity_inputs(result: PickerExtractionResultV1) -> dict:
    """Translate visible evidence without producing an authenticity conclusion."""
    return {
        "source_reference": result.source_asset_reference,
        "platform": result.detected_platform.value,
        "account": {"display_name": result.account.display_name.value, "handle": result.account.handle.value},
        "caption_claim": result.authored_caption.value,
        "visible_timestamp": result.visible_date_text.value,
        "primary_media_crop": result.primary_media_crop.bounding_box.model_dump(),
        "content_regions": [region.model_dump(mode="json") for region in result.content_regions],
        "provenance": result.provenance.model_dump(mode="json"),
    }
