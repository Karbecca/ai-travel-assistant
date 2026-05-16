from pydantic import BaseModel, ConfigDict, Field


class TripBase(BaseModel):
    destination: str = Field(min_length=1, max_length=255)
    days: int = Field(ge=1, le=365)
    budget: float = Field(gt=0)
    trip_style: str = Field(min_length=1, max_length=50)


class TripCreate(TripBase):
    pass


class TripUpdate(BaseModel):
    destination: str | None = Field(default=None, min_length=1, max_length=255)
    days: int | None = Field(default=None, ge=1, le=365)
    budget: float | None = Field(default=None, gt=0)
    trip_style: str | None = Field(default=None, min_length=1, max_length=50)


class TripPublic(TripBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class TripCreated(TripPublic):
    message: str = "Trip created successfully"
