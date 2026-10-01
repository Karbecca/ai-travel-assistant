from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.deps import get_current_user
from app.models.user import User
from app.schemas.image import ImageAnalysisResponse
from app.services.image_analysis import ImageAnalysisError, analyze_destination_image

router = APIRouter(tags=["Image"])

_ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@router.post("/analyze", response_model=ImageAnalysisResponse)
def analyze_image(
    file: UploadFile,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ImageAnalysisResponse:
    media_type = file.content_type or "image/jpeg"
    if media_type not in _ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type: {media_type}",
        )
    image_bytes = file.file.read()
    try:
        result = analyze_destination_image(image_bytes, media_type)
    except ImageAnalysisError as exc:
        detail = str(exc)
        code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if "not configured" in detail
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=code, detail=detail)
    return ImageAnalysisResponse(**result)
