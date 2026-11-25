from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ProviderResponse:
    extraction: Any
    model: str
    connection_ms: int
    response_ms: int
    parse_ms: int
    input_tokens: int
    output_tokens: int
    request_bytes: int
    image_detail: str


class PickerVisionProvider(Protocol):
    async def extract(self, *, image_bytes: bytes, context: dict, request_id: str, model: str, detail: str, maximum_output_tokens: int) -> ProviderResponse: ...
