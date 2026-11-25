from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2
import numpy as np
from path_management import MANAGED_PATHS


def decode_image(data):
    return cv2.imdecode(
        np.frombuffer(data, np.uint8),
        cv2.IMREAD_COLOR,
    )


def load_and_sample_video(data, extension):
    temporary_path = None

    try:
        with NamedTemporaryFile(
            suffix=extension,
            delete=False,
            dir=MANAGED_PATHS.temp if MANAGED_PATHS.configured else None,
        ) as temporary_file:
            temporary_file.write(data)
            temporary_path = Path(temporary_file.name)

        capture = cv2.VideoCapture(str(temporary_path))

        if not capture.isOpened():
            return None

        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            frame_count = int(
                capture.get(cv2.CAP_PROP_FRAME_COUNT)
            )
            width = int(
                capture.get(cv2.CAP_PROP_FRAME_WIDTH)
            )
            height = int(
                capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
            )
            duration = frame_count / fps if fps > 0 else 0

            sample_count = min(12, frame_count)
            sampled_frames = []

            if frame_count > 0 and sample_count > 0:
                frame_indices = np.linspace(
                    0,
                    frame_count - 1,
                    num=sample_count,
                    dtype=int,
                )

                for frame_index in frame_indices:
                    capture.set(
                        cv2.CAP_PROP_POS_FRAMES,
                        int(frame_index),
                    )
                    success, frame = capture.read()

                    if success and frame is not None:
                        sampled_frames.append(frame)

            return {
                "fps": fps,
                "frame_count": frame_count,
                "width": width,
                "height": height,
                "duration": duration,
                "sampled_frames": sampled_frames,
            }
        finally:
            capture.release()
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
