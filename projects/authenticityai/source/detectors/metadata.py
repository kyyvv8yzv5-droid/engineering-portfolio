import io
import json
import shutil
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
from path_management import MANAGED_PATHS

from PIL import Image, UnidentifiedImageError


NO_METADATA_CONTEXT = (
    "metadata may be removed by social media, screenshots, messaging apps, "
    "or recompression; absence alone is not evidence that media is "
    "AI-generated"
)

EDITING_SOFTWARE_MARKERS = (
    "adobe photoshop",
    "adobe lightroom",
    "affinity photo",
    "capture one",
    "davinci resolve",
    "final cut pro",
    "gimp",
    "premiere pro",
)

GENERATOR_OR_AI_SOFTWARE_MARKERS = (
    "automatic1111",
    "comfyui",
    "dall-e",
    "dall·e",
    "firefly",
    "fooocus",
    "generative fill",
    "invokeai",
    "midjourney",
    "stable diffusion",
)


def _clean_value(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        value = value.strip().strip("\x00")
        return value or None
    return value


def _software_warnings(software):
    if not software:
        return []

    normalized = str(software).casefold()
    warnings = []

    if any(marker in normalized for marker in EDITING_SOFTWARE_MARKERS):
        warnings.append("editing_software_detected")

    if any(
        marker in normalized
        for marker in GENERATOR_OR_AI_SOFTWARE_MARKERS
    ):
        warnings.append("generator_or_ai_software_detected")

    return warnings


def _empty_video_metadata(warnings):
    return {
        "format_name": None,
        "codec_name": None,
        "encoder": None,
        "creation_time": None,
        "bitrate": None,
        "metadata_present": False,
        "metadata_warnings": warnings,
    }


def inspect_image_metadata(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            exif = image.getexif()
            info = image.info

            camera_make = _clean_value(exif.get(271))
            camera_model = _clean_value(exif.get(272))
            software = _clean_value(
                exif.get(305)
                or info.get("Software")
                or info.get("software")
            )

            datetime_fields = [
                _clean_value(exif.get(306)),
                _clean_value(exif.get(36867)),
                _clean_value(exif.get(36868)),
            ]
            capture_datetime = (
                datetime_fields[1]
                or datetime_fields[2]
                or datetime_fields[0]
                or _clean_value(
                    info.get("creation_time")
                    or info.get("Creation Time")
                    or info.get("date:create")
                )
            )

            gps_present = False
            try:
                gps_present = bool(exif.get_ifd(34853))
            except (KeyError, TypeError, ValueError):
                gps_present = bool(exif.get(34853))

            orientation = _clean_value(exif.get(274))
            color_space_value = _clean_value(exif.get(40961))

            if color_space_value == 1:
                color_space = "sRGB"
            elif color_space_value == 65535:
                color_space = "Uncalibrated"
            elif color_space_value is not None:
                color_space = str(color_space_value)
            elif info.get("icc_profile"):
                color_space = "ICC profile embedded"
            else:
                color_space = None

            descriptive_info_present = any(
                info.get(key)
                for key in (
                    "Software",
                    "software",
                    "creation_time",
                    "Creation Time",
                    "date:create",
                    "icc_profile",
                    "exif",
                )
            )
            metadata_present = bool(exif) or descriptive_info_present

    except (OSError, UnidentifiedImageError, ValueError):
        return {
            "metadata_present": False,
            "camera_make": None,
            "camera_model": None,
            "software": None,
            "capture_datetime": None,
            "gps_present": False,
            "orientation": None,
            "color_space": None,
            "metadata_warnings": [
                "metadata_inspection_failed",
                NO_METADATA_CONTEXT,
            ],
        }

    warnings = _software_warnings(software)
    populated_datetimes = {
        value for value in datetime_fields if value is not None
    }

    if len(populated_datetimes) > 1:
        warnings.append("inconsistent_datetime_fields")

    # Missing metadata is common after ordinary platform processing. It must
    # never be treated as evidence that an image was AI-generated.
    if not metadata_present:
        warnings.extend(["no_metadata", NO_METADATA_CONTEXT])

    return {
        "metadata_present": bool(metadata_present),
        "camera_make": camera_make,
        "camera_model": camera_model,
        "software": software,
        "capture_datetime": capture_datetime,
        "gps_present": gps_present,
        "orientation": orientation,
        "color_space": color_space,
        "metadata_warnings": warnings,
    }


def inspect_video_metadata(data, extension, ffprobe_path=None):
    ffprobe = ffprobe_path or shutil.which("ffprobe")

    if not ffprobe:
        return _empty_video_metadata(
            ["ffprobe_unavailable", NO_METADATA_CONTEXT]
        )

    temporary_path = None

    try:
        with NamedTemporaryFile(
            suffix=extension,
            delete=False,
            dir=MANAGED_PATHS.temp if MANAGED_PATHS.configured else None,
        ) as temporary_file:
            temporary_file.write(data)
            temporary_path = Path(temporary_file.name)

        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(temporary_path),
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=15,
        )
        probe = json.loads(completed.stdout)
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return _empty_video_metadata(
            ["metadata_inspection_failed", NO_METADATA_CONTEXT]
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    format_data = probe.get("format") or {}
    streams = probe.get("streams") or []
    video_stream = next(
        (
            stream
            for stream in streams
            if stream.get("codec_type") == "video"
        ),
        {},
    )
    format_tags = format_data.get("tags") or {}
    stream_tags = video_stream.get("tags") or {}

    format_name = _clean_value(format_data.get("format_name"))
    codec_name = _clean_value(video_stream.get("codec_name"))
    encoder = _clean_value(
        format_tags.get("encoder") or stream_tags.get("encoder")
    )
    creation_time = _clean_value(
        format_tags.get("creation_time")
        or stream_tags.get("creation_time")
    )
    bitrate_value = _clean_value(format_data.get("bit_rate"))

    try:
        bitrate = int(bitrate_value) if bitrate_value is not None else None
    except (TypeError, ValueError):
        bitrate = bitrate_value

    metadata_present = any(
        value is not None
        for value in (
            format_name,
            codec_name,
            encoder,
            creation_time,
            bitrate,
        )
    )
    warnings = _software_warnings(encoder)

    if not metadata_present:
        warnings.extend(["no_metadata", NO_METADATA_CONTEXT])

    return {
        "format_name": format_name,
        "codec_name": codec_name,
        "encoder": encoder,
        "creation_time": creation_time,
        "bitrate": bitrate,
        "metadata_present": metadata_present,
        "metadata_warnings": warnings,
    }
