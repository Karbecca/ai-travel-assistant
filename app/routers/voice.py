import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.deps import get_current_user
from app.models.user import User
from app.schemas.voice import SynthesizeRequest, TranscribeResponse
from app.services.speech import SpeechServiceError, synthesize_speech, transcribe_audio

router = APIRouter(tags=["Voice"])


@router.post("/transcribe", response_model=TranscribeResponse)
def transcribe(
    file: UploadFile,
    current_user: Annotated[User, Depends(get_current_user)],
) -> TranscribeResponse:
    audio_bytes = file.file.read()
    try:
        text = transcribe_audio(audio_bytes, file.filename or "audio.wav")
    except SpeechServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return TranscribeResponse(text=text)


@router.post("/synthesize")
def synthesize(
    payload: SynthesizeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    try:
        audio_bytes = synthesize_speech(payload.text)
    except SpeechServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "attachment; filename=speech.mp3"},
    )
