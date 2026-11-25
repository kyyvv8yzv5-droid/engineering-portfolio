"""Strict legacy browser settings; executable families are deliberately bounded."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class NotificationPreferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    in_app: StrictBool
    email: StrictBool
    push: StrictBool


class TesterSettingsRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    operating_mode: Literal['automated','approval','ideas','manual','learn'] | None = None
    profile: Literal['conservative','balanced','aggressive'] | None = None
    max_allocation: float | None = Field(None, ge=0, le=.70, strict=True)
    max_modeled_risk_per_trade: float | None = Field(None, ge=0, le=.06, strict=True)
    max_leverage: float | None = Field(None, ge=1, le=3, strict=True)
    enabled_strategy_families: list[Literal['spot','pairs','leveraged']] | None = None
    notification_preferences: NotificationPreferences | None = None

    @field_validator('max_leverage')
    @classmethod
    def leverage(cls, value):
        if value is not None and value not in (1, 1.5, 2, 3):
            raise ValueError('Leverage must be 1x, 1.5x, 2x or 3x')
        return value

    @field_validator('enabled_strategy_families')
    @classmethod
    def unique(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError('Strategy families must be unique')
        return value
