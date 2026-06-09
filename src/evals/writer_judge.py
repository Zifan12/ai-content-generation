from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    dimension: str
    score: int = Field(ge=1, le=5)
    reason: str = Field(max_length=500)


class PackageVerdict(BaseModel):
    scores: list[DimensionScore]
