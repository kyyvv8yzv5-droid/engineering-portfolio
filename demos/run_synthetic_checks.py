"""Run only the two standalone checks described in README.md."""

import hashlib
import importlib.util
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    metrics = load(
        "showcase_metrics",
        "projects/authenticityai/source/evaluation/metrics.py",
    )
    result = metrics.confusion([0.1, 0.9], ["real", "ai"])
    assert result["tp"] == 1 and result["tn"] == 1, result

    hashing = load(
        "showcase_hashing", "projects/picker/source/picker/hashing/__init__.py"
    )
    image = Image.new("RGB", (9, 8), "white")
    pixels = image.tobytes()
    exact, perceptual = hashing.calculate_hashes(pixels, image)
    assert exact == hashlib.sha256(pixels).hexdigest()
    assert hashing.compare_perceptual_hashes(perceptual, perceptual) == 0
    print("Passed synthetic evaluation and image hashing checks.")


if __name__ == "__main__":
    main()
