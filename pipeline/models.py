from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import MAX_MARK, MAX_TIER, MIN_TIER


class Marks(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    m65: int = Field(alias="65", ge=1, le=MAX_MARK)
    m85: int = Field(alias="85", ge=1, le=MAX_MARK)
    m95: int = Field(alias="95", ge=1, le=MAX_MARK)
    m100: int = Field(alias="100", ge=1, le=MAX_MARK)

    @model_validator(mode="after")
    def thresholds_are_ordered(self) -> "Marks":
        if not (self.m65 < self.m85 < self.m95 <= self.m100):
            raise ValueError(
                f"неверный порядок порогов: {self.m65} < {self.m85} < {self.m95} <= {self.m100}"
            )
        return self

    def as_public(self) -> dict[str, int]:
        return {
            "65": self.m65,
            "85": self.m85,
            "95": self.m95,
            "100": self.m100,
        }


class VehicleMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(gt=0)
    tag: str = ""
    nation: str
    type: str
    tier: int = Field(ge=MIN_TIER, le=MAX_TIER)
    name: str
    short_name: str = ""
    is_premium: bool = False
    is_special: bool = False
    is_collector: bool = False
    role: str = ""

    @field_validator("nation", "type", "name")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("пустое значение")
        return value


class VehicleSnapshot(VehicleMeta):
    marks: Marks

    def as_public(self) -> dict:
        data = self.model_dump()
        data.pop("marks", None)
        data["marks"] = self.marks.as_public()
        return data


class VehiclesCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_at: str
    version: int
    icons_url: str
    vehicles: list[VehicleMeta]


class LatestSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_at: str
    version: int
    icons_url: str
    vehicles: list[VehicleSnapshot]
