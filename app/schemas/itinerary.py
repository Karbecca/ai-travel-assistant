from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ItineraryDayInput(BaseModel):
    day: int = Field(ge=1, le=365)
    activities: list[str] = Field(default_factory=list)


class ItineraryCreate(BaseModel):
    trip_id: int = Field(ge=1)
    generate: bool = Field(
        default=False,
        description="When true, generate the itinerary with an LLM using trip details from the database.",
    )
    days: list[ItineraryDayInput] | None = Field(
        default=None,
        description="Day-by-day activities. Required when generate is false.",
    )

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        if self.generate:
            if self.days:
                raise ValueError("days must not be provided when generate is true")
        elif self.days is None:
            raise ValueError("days is required when generate is false")
        return self


class ItineraryDayPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: int
    activities: list[str]


class ItineraryPublic(BaseModel):
    trip_id: int
    itinerary: list[ItineraryDayPublic]


class ItineraryCreateResponse(ItineraryPublic):
    message: str = "Itinerary created successfully"
