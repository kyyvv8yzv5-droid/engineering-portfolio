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
