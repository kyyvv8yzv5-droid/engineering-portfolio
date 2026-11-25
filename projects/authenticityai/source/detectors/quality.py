import cv2
import numpy as np


def analyze_image_quality(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    sharpness = float(
        cv2.Laplacian(gray, cv2.CV_64F).var()
    )

    warnings = []

    if brightness < 40:
        warnings.append("Very dark")

    if brightness > 220:
        warnings.append("Overexposed")

    if sharpness < 100:
        warnings.append("Blurry")

    if contrast < 25:
        warnings.append("Low contrast")

    return {
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "sharpness": round(sharpness, 2),
    }, warnings


def analyze_video_quality(frames):
    sharpness_scores = []
    brightness_scores = []

    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        sharpness_scores.append(
            float(
                cv2.Laplacian(
                    gray,
                    cv2.CV_64F,
                ).var()
            )
        )
        brightness_scores.append(float(np.mean(gray)))

    return {
        "average_brightness": (
            round(float(np.mean(brightness_scores)), 2)
            if brightness_scores
            else None
        ),
        "average_sharpness": (
            round(float(np.mean(sharpness_scores)), 2)
            if sharpness_scores
            else None
        ),
    }
