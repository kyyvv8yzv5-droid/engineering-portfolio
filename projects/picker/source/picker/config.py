from dataclasses import dataclass


@dataclass(frozen=True)
class PickerConfig:
    api_key: str | None = None
    fast_vision_model: str = "gpt-4.1-2025-04-14"
    fallback_vision_model: str = "gpt-5-mini"
    model_timeout_seconds: float = 45
    maximum_upload_bytes: int = 20 * 1024 * 1024
    maximum_normalized_edge: int = 1600
    fallback_maximum_edge: int = 1800
    image_detail: str = "high"
    fallback_image_detail: str = "high"
    normalization_quality: int = 86
    perceptual_duplicate_threshold: int = 8
    crop_confidence_threshold: float = 0.72
    required_field_confidence_threshold: float = 0.72
    fallback_enabled: bool = True
    concurrency_limit: int = 3
    maximum_output_tokens: int = 3500
    prompt_version: str = "picker-screenshot-v1"
    logging_level: str = "INFO"
    video_maximum_upload_bytes: int = 250 * 1024 * 1024
    video_maximum_duration_seconds: float = 180
    video_minimum_width: int = 320
    video_minimum_height: int = 320
    video_maximum_width: int = 2160
    video_maximum_height: int = 3840
    video_maximum_fps: float = 60
    video_processing_timeout_seconds: float = 180
    video_sample_interval_seconds: float = 0.75
    video_maximum_candidate_frames: int = 60
    video_maximum_extracted_posts: int = 30
    video_stable_change_threshold: float = 0.09
    video_transition_change_threshold: float = 0.24
    video_blur_threshold: float = 0.08
    video_duplicate_hash_distance: int = 8
    video_maximum_temporary_bytes: int = 500 * 1024 * 1024
