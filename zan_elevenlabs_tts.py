"""Optional server-side ElevenLabs recipe narration.

Disabled unless ZAN_ENABLE_ELEVENLABS_TTS=1 and both credentials exist.
Never expose the API key to browser JS; never call the API on app startup.
The original browser reader remains the fallback.
"""
from __future__ import annotations

import os
import re

import requests

API_ROOT = "https://api.elevenlabs.io/v1/text-to-speech/"
DEFAULT_MODEL = "eleven_flash_v2_5"
DEFAULT_VOICE_ID = "IwUHRu30D3zHxPZTuTIK"  # user's ElevenLabs voice clone


def selected_voice_id() -> str:
    """An optional override, otherwise use the user's selected voice clone."""
    return (os.getenv("ELEVENLABS_VOICE_ID", "").strip() or DEFAULT_VOICE_ID)



def elevenlabs_enabled() -> bool:
    # The hackathon's Meta-only runtime needs this flag OFF.
    if os.getenv("ZAN_HACKATHON_MODE", "").lower() in ("1", "true", "yes"):
        return False
    return (os.getenv("ZAN_ENABLE_ELEVENLABS_TTS", "").lower() in ("1", "true", "yes")
            and bool(os.getenv("ELEVENLABS_API_KEY", "").strip()))


def recipe_speech_text(recipe: dict) -> str:
    """Read the exact displayed recipe fields, with natural spoken headings."""
    parts = [f"Let's make {str(recipe.get('name') or 'this recipe')}. "]
    if recipe.get('description'):
        parts.append(str(recipe['description']))
    ingredients = recipe.get('ingredients') or []
    if ingredients:
        parts.append('Ingredients. ' + '. '.join(str(i) for i in ingredients) + '.')
    steps = recipe.get('instructions') or []
    if steps:
        parts.append('Instructions. ' + ' '.join(
            f'Step {index}. {step}.' for index, step in enumerate(steps, start=1)
        ))
    return ' '.join(parts).strip()


def synthesize_recipe(text: str) -> bytes:
    """Return MP3 bytes. One explicit call; failures don't affect saved recipes."""
    if not elevenlabs_enabled():
        raise RuntimeError('ElevenLabs is not enabled. The browser voice is still available.')
    api_key = os.environ['ELEVENLABS_API_KEY'].strip()
    voice_id = selected_voice_id()
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}', voice_id):
        raise ValueError('Check ELEVENLABS_VOICE_ID in your .env file.')
    if not text or len(text) > 39000:
        raise ValueError('This recipe is too long for one narration.')
    model_id = os.getenv('ELEVENLABS_MODEL_ID', DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if model_id not in ('eleven_flash_v2_5', 'eleven_multilingual_v2'):
        raise ValueError('Unsupported ElevenLabs model configuration.')
    if model_id == 'eleven_multilingual_v2' and len(text) > 10000:
        raise ValueError('This recipe is too long for multilingual voice mode.')
    try:
        with requests.post(
            API_ROOT + voice_id,
            headers={'xi-api-key': api_key, 'Content-Type': 'application/json', 'Accept': 'audio/mpeg'},
            params={'output_format': 'mp3_44100_128'},
            json={'text': text, 'model_id': model_id,
                  'voice_settings': {'stability': 0.57, 'similarity_boost': 0.75, 'style': 0.0}},
            timeout=(10, 90), stream=True,
        ) as response:
            if not response.ok:
                if response.status_code in (401, 403):
                    raise RuntimeError('Your ElevenLabs key, plan or cloned-voice access needs checking.')
                if response.status_code == 404:
                    raise RuntimeError('That voice is not available. Check ELEVENLABS_VOICE_ID.')
                if response.status_code in (400, 422):
                    raise RuntimeError('That voice or speech model is not available on this ElevenLabs account.')
                if response.status_code == 429:
                    raise RuntimeError('ElevenLabs is rate-limited or your credits are exhausted.')
                raise RuntimeError('ElevenLabs could not generate this recipe audio.')
            if 'audio' not in response.headers.get('Content-Type', 'audio/mpeg').lower():
                raise RuntimeError('Unexpected audio response from ElevenLabs.')
            output = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    output.extend(chunk)
                    if len(output) > 16_000_000:
                        raise RuntimeError('Audio is too long for this preview.')
            if not output:
                raise RuntimeError('ElevenLabs returned an empty recording.')
            return bytes(output)
    except requests.RequestException as exc:
        raise RuntimeError('Could not reach ElevenLabs. Try the browser voice instead.') from exc
