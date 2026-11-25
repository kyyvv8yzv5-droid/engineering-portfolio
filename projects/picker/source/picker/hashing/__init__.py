import hashlib

from PIL import Image


def perceptual_hash(image: Image.Image) -> str:
    sample = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(sample.getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | int(pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return f"{value:016x}"


def calculate_hashes(image_bytes: bytes, image: Image.Image | None = None) -> tuple[str, str]:
    if image is None:
        from io import BytesIO
        with Image.open(BytesIO(image_bytes)) as source:
            image = source.convert("RGB").copy()
    return hashlib.sha256(image_bytes).hexdigest(), perceptual_hash(image)


def compare_exact_hashes(left: str, right: str) -> bool:
    return left == right


def compare_perceptual_hashes(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()
