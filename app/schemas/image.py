from pydantic import BaseModel


class ImageAnalysisResponse(BaseModel):
    description: str
    suggested_destination: str
