import io
import json
import subprocess
import unittest
from unittest.mock import patch

from PIL import Image

from detectors.metadata import (
    NO_METADATA_CONTEXT,
    inspect_image_metadata,
    inspect_video_metadata,
)


def make_jpeg(exif=None):
    output = io.BytesIO()
    image = Image.new("RGB", (16, 16), color="white")
    save_options = {"exif": exif} if exif is not None else {}
    image.save(output, format="JPEG", **save_options)
    return output.getvalue()


class ImageMetadataTests(unittest.TestCase):
    def test_image_with_exif(self):
        exif = Image.Exif()
        exif[271] = "Example Camera Co."
        exif[272] = "Model One"
        exif[305] = "Adobe Photoshop 2026; Stable Diffusion"
        exif[306] = "2026:07:14 10:00:00"
        exif[36867] = "2026:07:14 09:59:00"
        exif[274] = 1
        exif[40961] = 1

        metadata = inspect_image_metadata(make_jpeg(exif))

        self.assertTrue(metadata["metadata_present"])
        self.assertEqual(metadata["camera_make"], "Example Camera Co.")
        self.assertEqual(metadata["camera_model"], "Model One")
        self.assertEqual(
            metadata["software"],
            "Adobe Photoshop 2026; Stable Diffusion",
        )
        self.assertEqual(
            metadata["capture_datetime"],
            "2026:07:14 09:59:00",
        )
        self.assertFalse(metadata["gps_present"])
        self.assertEqual(metadata["orientation"], 1)
        self.assertEqual(metadata["color_space"], "sRGB")
        self.assertIn(
            "editing_software_detected",
            metadata["metadata_warnings"],
        )
        self.assertIn(
            "generator_or_ai_software_detected",
            metadata["metadata_warnings"],
        )
        self.assertIn(
            "inconsistent_datetime_fields",
            metadata["metadata_warnings"],
        )

    def test_image_without_exif(self):
        metadata = inspect_image_metadata(make_jpeg())

        self.assertFalse(metadata["metadata_present"])
        self.assertIn("no_metadata", metadata["metadata_warnings"])
        self.assertIn(NO_METADATA_CONTEXT, metadata["metadata_warnings"])
        self.assertNotIn(
            "generator_or_ai_software_detected",
            metadata["metadata_warnings"],
        )


class VideoMetadataTests(unittest.TestCase):
    @patch("detectors.metadata.subprocess.run")
    @patch("detectors.metadata.shutil.which", return_value="ffprobe")
    def test_video_metadata(self, _which, run):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "format": {
                        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                        "bit_rate": "812345",
                        "tags": {
                            "encoder": "Lavf62.3.100",
                            "creation_time": "2026-07-14T15:00:00Z",
                        },
                    },
                    "streams": [
                        {
                            "codec_type": "video",
                            "codec_name": "h264",
                        }
                    ],
                }
            ),
        )

        metadata = inspect_video_metadata(b"video", ".mp4")

        self.assertTrue(metadata["metadata_present"])
        self.assertEqual(
            metadata["format_name"],
            "mov,mp4,m4a,3gp,3g2,mj2",
        )
        self.assertEqual(metadata["codec_name"], "h264")
        self.assertEqual(metadata["encoder"], "Lavf62.3.100")
        self.assertEqual(
            metadata["creation_time"],
            "2026-07-14T15:00:00Z",
        )
        self.assertEqual(metadata["bitrate"], 812345)

    @patch("detectors.metadata.shutil.which", return_value=None)
    def test_missing_ffprobe_fallback(self, _which):
        metadata = inspect_video_metadata(b"video", ".mp4")

        self.assertFalse(metadata["metadata_present"])
        self.assertIsNone(metadata["format_name"])
        self.assertIsNone(metadata["codec_name"])
        self.assertIn(
            "ffprobe_unavailable",
            metadata["metadata_warnings"],
        )
        self.assertIn(NO_METADATA_CONTEXT, metadata["metadata_warnings"])


if __name__ == "__main__":
    unittest.main()
