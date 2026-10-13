import io

from gtts import gTTS
import speech_recognition as sr


class SpeechServiceError(Exception):
    pass


def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            audio_data = recognizer.record(source)
        return recognizer.recognize_google(audio_data)
    except sr.UnknownValueError:
        raise SpeechServiceError("Could not understand audio")
    except sr.RequestError as exc:
        raise SpeechServiceError(f"Speech recognition request failed: {exc}") from exc
    except Exception as exc:
        raise SpeechServiceError(f"Audio processing failed: {exc}") from exc


def synthesize_speech(text: str) -> bytes:
    try:
        tts = gTTS(text=text, lang="en")
        buffer = io.BytesIO()
        tts.write_to_fp(buffer)
        buffer.seek(0)
        return buffer.read()
    except Exception as exc:
        raise SpeechServiceError(f"Speech synthesis failed: {exc}") from exc
