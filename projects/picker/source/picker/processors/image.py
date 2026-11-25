import time
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from picker.config import PickerConfig
from picker.schemas import PickerBoundingBoxV1


@dataclass
class PreparedScreenshot:
    original: Image.Image
    trimmed: Image.Image
    trim_box: tuple[int, int, int, int]
    normalized_bytes: bytes
    normalized_size: tuple[int, int]
    normalization_ms: int


def _safe_trim(image: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    width, height = image.size
    corners = [image.getpixel(point) for point in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))]
    background_color = tuple(sorted(pixel[channel] for pixel in corners)[len(corners) // 2] for channel in range(3))
    background = Image.new("RGB", image.size, background_color)
    difference = ImageChops.difference(image, background).convert("L").point(lambda value: 255 if value > 14 else 0)
    box = difference.getbbox()
    if not box:
        return image, (0, 0, width, height)
    left, top, right, bottom = box
    retained = ((right - left) * (bottom - top)) / (width * height)
    if retained < 0.60 or (left < width * .01 and top < height * .01 and right > width * .99 and bottom > height * .99):
        return image, (0, 0, width, height)
    padding = max(2, round(min(width, height) * .004))
    box = (max(0, left - padding), max(0, top - padding), min(width, right + padding), min(height, bottom + padding))
    return image.crop(box), box


def _encode(image: Image.Image, maximum_edge: int, quality: int) -> tuple[bytes, tuple[int, int]]:
    normalized = image.copy()
    normalized.thumbnail((maximum_edge, maximum_edge), Image.Resampling.LANCZOS)
    if normalized.size != image.size:
        normalized = normalized.filter(ImageFilter.UnsharpMask(radius=.7, percent=115, threshold=2))
    output = BytesIO()
    normalized.save(output, "JPEG", quality=quality, optimize=True)
    return output.getvalue(), normalized.size


def normalize_screenshot(image_bytes: bytes, config: PickerConfig | None = None, *, maximum_edge: int | None = None) -> PreparedScreenshot:
    config = config or PickerConfig()
    if len(image_bytes) > config.maximum_upload_bytes:
        raise ValueError("Screenshot exceeds the configured maximum upload size")
    started = time.perf_counter()
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            oriented = ImageOps.exif_transpose(source)
            if "A" in oriented.getbands():
                alpha_box = oriented.getchannel("A").getbbox()
                oriented = oriented.crop(alpha_box) if alpha_box else oriented
            original = oriented.convert("RGB").copy()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("The screenshot could not be decoded as an image") from exc
    trimmed, trim_box = _safe_trim(original)
    normalized_bytes, normalized_size = _encode(trimmed, maximum_edge or config.maximum_normalized_edge, config.normalization_quality)
    return PreparedScreenshot(original, trimmed, trim_box, normalized_bytes, normalized_size, round((time.perf_counter() - started) * 1000))


def encode_for_edge(prepared: PreparedScreenshot, maximum_edge: int, quality: int) -> tuple[bytes, tuple[int, int]]:
    return _encode(prepared.trimmed, maximum_edge, quality)


def validate_crop(box: PickerBoundingBoxV1, minimum_area: float = .03) -> bool:
    return box.x + box.width <= 1.001 and box.y + box.height <= 1.001 and box.width * box.height >= minimum_area


def refine_crop_to_visible_edges(image: Image.Image, box: PickerBoundingBoxV1) -> PickerBoundingBoxV1:
    """Snap a model crop to nearby strong horizontal media/UI boundaries."""
    if box.width < .75:
        return box
    sample = image.convert("L")
    sample.thumbnail((360, 900), Image.Resampling.BOX)
    scores = [0.0]
    for y in range(1, sample.height):
        difference = ImageChops.difference(sample.crop((0, y - 1, sample.width, y)), sample.crop((0, y, sample.width, y + 1)))
        scores.append(ImageStat.Stat(difference).mean[0])
    def strongest(center: float, radius: float) -> tuple[float, float]:
        start = max(1, round((center - radius) * sample.height)); end = min(sample.height - 1, round((center + radius) * sample.height))
        index = max(range(start, end + 1), key=lambda item: scores[item])
        return index / sample.height, scores[index]
    top, top_score = strongest(box.y, .07)
    bottom, bottom_score = strongest(box.y + box.height, .16)
    if top_score < 10 or bottom_score < 10 or bottom - top < .2:
        return box
    return PickerBoundingBoxV1(x=box.x, y=top, width=box.width, height=bottom - top)


def remap_box(box: PickerBoundingBoxV1 | None, prepared: PreparedScreenshot) -> PickerBoundingBoxV1 | None:
    if box is None:
        return None
    left, top, right, bottom = prepared.trim_box
    original_width, original_height = prepared.original.size
    trimmed_width, trimmed_height = right - left, bottom - top
    return PickerBoundingBoxV1(
        x=(left + box.x * trimmed_width) / original_width,
        y=(top + box.y * trimmed_height) / original_height,
        width=box.width * trimmed_width / original_width,
        height=box.height * trimmed_height / original_height,
    )


def crop_content_region(image_bytes: bytes, box: PickerBoundingBoxV1, *, quality: int = 92) -> tuple[bytes, tuple[int, int]]:
    if not validate_crop(box):
        raise ValueError("Crop coordinates are invalid")
    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        left = max(0, min(image.width - 1, round(box.x * image.width)))
        top = max(0, min(image.height - 1, round(box.y * image.height)))
        right = max(left + 1, min(image.width, round((box.x + box.width) * image.width)))
        bottom = max(top + 1, min(image.height, round((box.y + box.height) * image.height)))
        crop = image.crop((left, top, right, bottom))
    output = BytesIO(); crop.save(output, "JPEG", quality=quality, optimize=True)
    return output.getvalue(), crop.size
