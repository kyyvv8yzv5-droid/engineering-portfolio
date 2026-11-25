import asyncio
from datetime import datetime, timezone
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from picker import (
    PickerBulkExtractionRequestV1, PickerConfig, PickerDependencies, PickerExtractionContextV1,
    PickerExtractionRequestV1, calculate_hashes, compare_exact_hashes, compare_perceptual_hashes,
    crop_content_region, extract_screenshot, extract_screenshots_bulk, get_capabilities,
    get_package_version, normalize_screenshot, validate_crop,
)
from picker.exceptions import PickerProviderError, PickerStructuredOutputError
from picker.providers import ProviderResponse
from picker.providers.openai import CompactExtraction
from picker.schemas import PickerBoundingBoxV1
from picker.video import ingest_video


def image_bytes(size=(480, 800), margin=0, orientation=None):
    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).rectangle((margin + 20, margin + 40, size[0] - margin - 20, size[1] - margin - 80), fill=(120, 50, 30))
    output = BytesIO()
    exif = Image.Exif()
    if orientation: exif[274] = orientation
    image.save(output, "JPEG", exif=exif)
    return output.getvalue()


def extraction(confidence=.95, platform="Instagram", caption="Dinner at Bella Vita.", crop=None):
    box = crop or {"x": .04, "y": .18, "w": .92, "h": .5}
    text = lambda value, conf=confidence: {"v": value, "c": conf, "b": None}
    listed = lambda values: {"v": values, "c": confidence, "b": None}
    return CompactExtraction.model_validate({
        "pf": text(platform), "candidate": text("account-1"), "acct": text("Bella Vita"), "handle": text("@bellavita"),
        "caption": text(caption), "image": {"b": box, "c": confidence},
        "loc": {"v": "Chicago", "c": confidence, "b": {"x": .1, "y": .8, "w": .3, "h": .04}},
        "address": {"v": "Chicago, IL", "c": confidence, "b": {"x": .1, "y": .84, "w": .3, "h": .04}},
        "date": text("June 2026"), "hashtags": listed(["#Dinner"]),
        "mentions": listed([]), "cta": listed(["Reserve"]), "engagement": [{"n": "likes", "v": "42", "c": confidence}],
        "menu": listed(["ravioli"]), "dishes": listed(["ravioli"]), "offers": listed([]), "events": listed([]),
        "phones": listed([]), "domains": listed(["example.com"]), "reservation": listed(["example.com/reserve"]),
        "delivery": listed([]), "phrases": listed(["Reserve"]),
        "replies": [{"t": "restaurant", "n": "Bella Vita", "v": "Thank you!", "c": confidence, "b": None}],
        "comments": [{"t": "customer", "n": "Guest", "v": "Looks great!", "c": confidence, "b": None}],
        "regions": [
            {"t": "caption", "v": caption, "c": confidence, "b": None},
            {"t": "comment", "v": "Looks great!", "c": confidence, "b": None},
            {"t": "interface", "v": "Like", "c": confidence, "b": None},
        ],
    })


def response(value=None, model="fast"):
    return ProviderResponse(value or extraction(), model, 5, 25, 2, 1000, 300, 15000, "high")


class FakeProvider:
    def __init__(self, values): self.values = list(values); self.calls = 0; self.active = 0; self.peak = 0
    async def extract(self, **kwargs):
        self.calls += 1; self.active += 1; self.peak = max(self.peak, self.active)
        await asyncio.sleep(.01)
        self.active -= 1
        value = self.values[min(self.calls - 1, len(self.values) - 1)]
        if isinstance(value, Exception): raise value
        return value


def request(seed=1):
    return PickerExtractionRequestV1(image_bytes=image_bytes((480 + seed, 800)), source_asset_reference=f"shot-{seed}.jpg", context=PickerExtractionContextV1(account_candidates=[{"key": "account-1"}]))


def test_version_and_capabilities():
    assert get_package_version() == "0.1.0"
    assert get_capabilities().model_dump() == {"screenshot_single": True, "screenshot_bulk": True, "video_ingestion": True, "video_post_reconstruction": True}


def test_orientation_normalization():
    prepared = normalize_screenshot(image_bytes((300, 500), orientation=6))
    assert prepared.original.width > prepared.original.height


def test_margin_trimming_and_resizing():
    prepared = normalize_screenshot(image_bytes((1600, 3000), margin=180))
    assert prepared.trim_box != (0, 0, 1600, 3000)
    assert max(prepared.normalized_size) <= 1600


def test_hashing_and_duplicate_primitives():
    data = image_bytes()
    exact, perceptual = calculate_hashes(data)
    assert compare_exact_hashes(exact, exact)
    assert compare_perceptual_hashes(perceptual, perceptual) == 0
    assert len(exact) == 64 and len(perceptual) == 16


def test_crop_validation_and_creation():
    valid = PickerBoundingBoxV1(x=.1, y=.1, width=.8, height=.6)
    invalid = PickerBoundingBoxV1(x=.8, y=.8, width=.4, height=.4)
    assert validate_crop(valid) and not validate_crop(invalid)
    crop, size = crop_content_region(image_bytes(), valid)
    assert crop.startswith(b"\xff\xd8") and size == (384, 480)


def test_single_extraction_contract_and_classification():
    provider = FakeProvider([response()])
    result = asyncio.run(extract_screenshot(request=request(), dependencies=PickerDependencies(vision_provider=provider)))
    assert provider.calls == 1
    assert result.detected_platform.value == "Instagram"
    assert result.account.handle.value == "@bellavita"
    assert result.location.visible_location.value == "Chicago"
    assert result.authored_caption.value == "Dinner at Bella Vita."
    assert result.customer_comments[0].author_type == "customer"
    assert result.authored_replies[0].author_type == "content_owner"
    assert result.interface_text == ["Like"]
    assert result.provenance.package_version == "0.1.0"
    assert result.processing_metrics.input_tokens == 1000
    assert result.fallback_used is False


def test_low_confidence_triggers_fallback():
    provider = FakeProvider([response(extraction(.5)), response(extraction(.95), "fallback")])
    result = asyncio.run(extract_screenshot(request=request(2), dependencies=PickerDependencies(vision_provider=provider)))
    assert provider.calls == 2 and result.fallback_used
    assert "low_caption_confidence" in result.fallback_reasons
    assert result.model == "fallback"


def test_invalid_crop_triggers_fallback():
    provider = FakeProvider([response(extraction(crop={"x": .8, "y": .8, "w": .4, "h": .4})), response()])
    result = asyncio.run(extract_screenshot(request=request(3), dependencies=PickerDependencies(vision_provider=provider)))
    assert "invalid_crop" in result.fallback_reasons


def test_structured_failure_triggers_fallback():
    provider = FakeProvider([PickerStructuredOutputError("bad schema"), response()])
    result = asyncio.run(extract_screenshot(request=request(4), dependencies=PickerDependencies(vision_provider=provider)))
    assert result.fallback_reasons == ["structured_validation_failed"]


def test_provider_error_does_not_fallback():
    provider = FakeProvider([PickerProviderError("401")])
    with pytest.raises(PickerProviderError): asyncio.run(extract_screenshot(request=request(5), dependencies=PickerDependencies(vision_provider=provider)))
    assert provider.calls == 1


def test_bounded_bulk_concurrency():
    provider = FakeProvider([response()] * 5)
    bulk = PickerBulkExtractionRequestV1(requests=[request(index + 10) for index in range(5)])
    results = asyncio.run(extract_screenshots_bulk(bulk, config=PickerConfig(concurrency_limit=2), dependencies=PickerDependencies(vision_provider=provider)))
    assert len(results) == 5 and provider.peak == 2


def test_invalid_structured_output_rejected():
    with pytest.raises(Exception): CompactExtraction.model_validate({"pf": {"v": "Instagram"}})


def test_clock_id_and_metrics_injection():
    recorded = []
    dependencies = PickerDependencies(
        vision_provider=FakeProvider([response()]),
        clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc), id_generator=lambda: "picker-test-id",
        metrics_recorder=lambda name, value, attributes: recorded.append((name, value, attributes)),
    )
    item = request(50); item.request_id = None
    result = asyncio.run(extract_screenshot(request=item, dependencies=dependencies))
    assert result.provenance.request_id == "picker-test-id"
    assert result.provenance.created_at == datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert recorded[0][0] == "picker.extraction.total_ms"


def test_fallback_can_be_disabled():
    provider = FakeProvider([response(extraction(.4))])
    result = asyncio.run(extract_screenshot(request=request(51), config=PickerConfig(fallback_enabled=False), dependencies=PickerDependencies(vision_provider=provider)))
    assert provider.calls == 1 and result.fallback_used is False and result.review_recommendation == "review"


def test_video_input_is_typed():
    with pytest.raises(AttributeError): asyncio.run(ingest_video(b"video"))
