"""Persistent private Supabase audio cache for optional ElevenLabs narration.

No service role key, extra SQL table, or public URL. Uses the current user's
authenticated Supabase client. Checks storage BEFORE spending any TTS credits.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from typing import Any

from zan_elevenlabs_tts import selected_voice_id, synthesize_recipe

AUDIO_BUCKET = "zan-private-audio"
AUDIO_VERSION = "elevenlabs-recipe-v1-stability057-sim075-style0-mp3-44100-128"
_MAX_MP3_BYTES = 16_000_000
# Prevent two reruns/sessions in the same Python process from generating the
# same audio at once. The destination path is also deterministic across workers.
_AUDIO_GENERATION_LOCK = threading.Lock()


def audio_cache_key(speech_text: str) -> str:
    """Only identical voice settings + exact recipe narration reuse an MP3."""
    data = {
        "version": AUDIO_VERSION,
        "voice_id": selected_voice_id(),
        "model": os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5").strip() or "eleven_flash_v2_5",
        "speech_text": speech_text,
    }
    return hashlib.sha256(json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _audio_path(user_id: str, speech_text: str) -> str:
    # Protect against arbitrary Storage paths even if user_id were malformed.
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", str(user_id)):
        raise ValueError("Please sign in to save private recipe audio.")
    return f"{user_id}/recipes/{audio_cache_key(speech_text)}.mp3"


def _private_audio_bucket(client: Any):
    return client.storage.from_(AUDIO_BUCKET)


def _get_existing_audio(bucket: Any, path: str) -> bytes | None:
    """List in the user's own private folder; only download an exact match.

    If bucket/RLS is not configured, let the exception stop generation so a
    failed cache lookup NEVER causes an unnecessarily billed voice request.
    """
    folder, filename = path.rsplit("/", 1)
    rows = bucket.list(path=folder, options={"search": filename, "limit": 10})
    if not isinstance(rows, list):
        raise RuntimeError("Audio storage did not return a valid file list.")
    if not any(isinstance(row, dict) and row.get("name") == filename for row in rows):
        return None
    audio = bucket.download(path)
    if not isinstance(audio, (bytes, bytearray)) or not 100 < len(audio) <= _MAX_MP3_BYTES:
        raise RuntimeError("Saved recipe audio is unavailable or incomplete.")
    return bytes(audio)


def _already_exists(exc: Exception) -> bool:
    message = str(exc).lower()
    return "already exists" in message or "duplicate" in message or "resourcealreadyexists" in message


def get_or_create_recipe_audio(client: Any, user_id: str, speech_text: str) -> tuple[bytes, str, str | None]:
    """Return (mp3, 'cache'|'generated', optional warning).

    One TTS call for a given recipe/voice/model/user, then reuse its Supabase
    MP3 on future sessions and after deploys. Fails closed on a cache lookup
    error (no new TTS call), to avoid burning credits if Storage is broken.
    """
    if not speech_text.strip():
        raise ValueError("There is no recipe text to read.")
    path = _audio_path(user_id, speech_text)
    bucket = _private_audio_bucket(client)
    with _AUDIO_GENERATION_LOCK:
        try:
            cached = _get_existing_audio(bucket, path)
        except Exception as exc:
            raise RuntimeError(
                "Audio cache is unavailable. Run the supplied Supabase audio-cache SQL first; "
                "no ElevenLabs credits were used."
            ) from exc
        if cached is not None:
            return cached, "cache", None

        # Only now is a paid API call allowed; this will not run during page
        # rendering or when the recipe button was not clicked.
        generated = synthesize_recipe(speech_text)
        if not isinstance(generated, (bytes, bytearray)) or not 100 < len(generated) <= _MAX_MP3_BYTES:
            raise RuntimeError("ElevenLabs returned an invalid or oversized MP3.")
        generated = bytes(generated)
        try:
            bucket.upload(
                path=path, file=generated,
                file_options={"content-type": "audio/mpeg", "upsert": "false"},
            )
        except Exception as exc:
            if _already_exists(exc):
                try:
                    cached = _get_existing_audio(bucket, path)
                    if cached is not None:
                        return cached, "cache", None
                except Exception:
                    pass
            # The user can hear what they already paid to generate during this
            # session. Don't lie that permanent caching succeeded.
            return (generated, "generated",
                    "Audio played, but couldn't be saved for later. Check Supabase Storage.")
        return generated, "generated", None
