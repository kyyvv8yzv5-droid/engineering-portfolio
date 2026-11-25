from pydantic import BaseModel


class PickerCapabilitiesV1(BaseModel):
    screenshot_single: bool = True
    screenshot_bulk: bool = True
    video_ingestion: bool = True
    video_post_reconstruction: bool = True


def get_capabilities() -> PickerCapabilitiesV1:
    return PickerCapabilitiesV1()
