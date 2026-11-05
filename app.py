
from pathlib import Path
from html import escape
import uuid
import base64
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import re
import os
import hashlib
from nutrition import calculate_meal_nutrition
import streamlit as st
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime
from muse import analyse_fridge, analyse_meal, suggest_recipes
from auth_ui import render_auth_gate, render_personal_page
from zan_store import ZanStore, DEFAULT_MODEL
from zan_search import recipe_search
from zan_voice_ui import render_shopping_mic
from zan_shopping_speech import split_items, parse_voice_items
from zan_elevenlabs_tts import elevenlabs_enabled, recipe_speech_text
from zan_recipe_audio_cache import audio_cache_key, get_or_create_recipe_audio
load_dotenv()

# --------------------------------------------------
# PAGE SETUP
# --------------------------------------------------

st.set_page_config(
    page_title="Zān — Your Kitchen Companion",
    page_icon="♡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BASE_DIR = Path(__file__).parent
CSS_PATH = BASE_DIR / "assets" / "style.css"

VALID_PAGES = {"home", "fridge", "meals", "recipes", "shopping", "personal"}

# A small optimised transparent PNG is bundled directly so Home always has
# the sticker. No filesystem URL, CDN, or CSS background loading is required.
ZAN_KITTY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAANwAAADKCAMAAAD5C941AAACQFBMVEXbppndqpfSbF/co5asZVrgrp20j3Lk39ivnZDv0bruzLN2JSDMd27SknLY"
    "ybGqVSH5693rzLhVVVWxXlfMknzRjnl/fw/LbV/14dTx3dEA//+xKhj/f///sf8A/wBqAGptU05///+7ema6dqiq/6r/arQ/AAAAAP9RJh+oQDq8"
    "iHG8gmy6kH62o6f/fwDFkHzMzGYAAAD35dnz2Mv47OLvxrbxuK758er0ycP////sp5nuqqby0rvomZDXppTVmIvatqjQeHPYiYZXNzPltJvMhnb/"
    "f3/+qqn3vblrSUNrQzv/AADLamVpOjKJWEzPmZWqeWp/f3/dsZvWppHqxrHqyLOQZVmqqqqvZ1V4U0zpx7TsyLP//wC6fnnpx7L//3/PknuzhXb2"
    "vsDy2MnVraLpx7HMmIf//7G/v3/v1sjjjIfWpZHjuabpxrTw2MmHSTrRmYjYuavjuqbx18jKiHfPp5K/v7/FXVnWl4rVl4eYdGvku6ft1MaVbGHZ"
    "p5Pap5X2y8rw18j35NbSmIjVpJHmu6asVlPHZFzjh3j249WzV02zclzKiXjNlnTXtqTku6e0jIPJiXfWl4rappXZtpbltZzkvKe6lo3JhnbjtJz6"
    "ypjz2c/w5M+qqlXOeHXdwLX/qlXx1bnx0bv249dOKybSi4TKknvct6bMzJnqqKT/v3/t0btdQT23lo7JinfSqH3euKf7mZnkmJTvuZfjs5nVi4TN"
    "lHrOy8v/AP/kmZTlmZTjtJv14tb//8+GTUG1iXbW/yG+AAAAwHRSTlMdXByjGdcbGQ1Y4ARSEhUJ26sD/JzTAvxYpwEHAgMBAv0CXgUDAwQB/f1Y"
    "i/39AkwFAPz8/Pz8/PwB/Pz7/Pv6/Pz8/Pr7AgMI/PwB/Pz8C/sC/C1uLfwD/PyxzwEITwL8/PzP/BMtAwSu/E/NkGz8TRRvkDAUBPys0fyMMPyP"
    "zglR0HFsMQX8/Kv8/HAOLbD8kYuwD3FS/E/QBxESAwz8Aw2KbPwycWwF0wQr/BCuB44F1A+uTSsIAYmsko0F/RQhGlQ7AAAv1UlEQVR42t19hYPb"
    "Rtr37obKdEwvvx/TaDRjSbYl22taZshiks0m2WyYmdM2TG3KzHRtr3jFf+17ngFpJHupueslUbdO7HVs/fQwqoHcKYfrukv9Jw13CLTJarW6canw"
    "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"
)


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------

defaults = {
    "active_page": "home",
    "inventory": [],
    "recipes": [],
    "grocery_list": [],
    "detected_ingredients": [],
    "scan_completed": False,
    "fridge_scan_id": "",
    "meal_scan_result": None,
    "meal_scan_id": "",
    "meals": [],
    "recipe_ingredient_selection": [],
    "recipe_source": [],
    "diary_recipe_name": None,
    "_recipe_job": None,
    "_recipe_notice": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

if st.session_state.active_page not in VALID_PAGES:
    st.session_state.active_page = "home"


# --------------------------------------------------
# HELPERS AND CALLBACKS
# --------------------------------------------------

def navigate(page):
    """Change page within the existing Streamlit session."""
    if page in VALID_PAGES:
        st.session_state.active_page = page


def navigate_mobile(page):
    """Navigate and close the keyed mobile popover in the same callback.

    Stateful Streamlit popovers otherwise remain open across page reruns.
    """
    navigate(page)
    # This key is available after opening the mobile menu. Close it even
    # when the selected destination is the page already on screen.
    if "zan_mobile_menu" in st.session_state:
        st.session_state["zan_mobile_menu"] = False


def go_to_diary_with_recipe(recipe_name):
    """Link a recipe to a new plate photo without guessing its portions."""
    st.session_state.diary_recipe_name = recipe_name
    navigate("meals")


def toggle_open_recipe(recipe_id):
    """One recipe open at a time; tapping it again closes it."""
    recipe_id = str(recipe_id)
    st.session_state["_zan_open_recipe_id"] = (
        None if st.session_state.get("_zan_open_recipe_id") == recipe_id
        else recipe_id
    )


def use_suggested_food(name_key, option_key):
    """On selecting a suggested name, fill the existing editable field."""
    selected = st.session_state.get(option_key)
    if selected:
        st.session_state[name_key] = selected


def recipe_executor():
    """Shared executor, no Streamlit calls are made inside background workers."""
    return _recipe_executor()


@st.cache_resource
def _recipe_executor():
    return ThreadPoolExecutor(max_workers=3, thread_name_prefix="zan-recipes")


def retry_recipe_save():
    job = st.session_state.get("_recipe_job")
    if job:
        job.pop("save_failed", None)


def delete_inventory_item(item_id):
    store.delete_inventory_item(item_id)
    st.session_state.inventory = store.get_inventory()


def remove_meal_item(meal_id):
    store.delete_meal(meal_id)
    st.session_state.meals = store.get_meals()


def get_meal_thumbnail(image_path):
    """Keep small private thumbnails inside this user's Streamlit session."""
    from io import BytesIO
    from PIL import Image, ImageOps

    current_user = store.user_id
    if st.session_state.get("_zan_meal_photo_cache_user") != current_user:
        st.session_state["_zan_meal_photo_cache_user"] = current_user
        st.session_state["_zan_meal_photo_cache"] = {}
    cache = st.session_state["_zan_meal_photo_cache"]
    if image_path not in cache:
        try:
            original = store.get_private_meal_image(image_path)
            with Image.open(BytesIO(original)) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((520, 420), Image.Resampling.LANCZOS)
                buf = BytesIO()
                image.save(buf, "JPEG", quality=77, optimize=True)
                preview = buf.getvalue()
        except Exception:
            preview = None
        # Bound the in-memory cache so a large diary doesn't grow indefinitely.
        if len(cache) >= 128:
            cache.pop(next(iter(cache)))
        cache[image_path] = preview
    return cache[image_path]


def add_shopping_from_input():
    """Save comma-separated (typed or dictated) groceries as individual rows.

    Do not silently retry items already saved if a later item raises an error.
    """
    raw = str(st.session_state.get("zan_shopping_new_item") or "").strip()
    names = split_items(raw)
    if not names:
        st.session_state.shopping_error = "Type or say a shopping item first."
        return
    added = []
    for item in names:
        try:
            store.add_shopping_item(item)
            added.append(item)
        except Exception as exc:
            # Only keep the remaining entries in the input, avoiding accidental
            # duplicate insertions on a second tap.
            remaining = names[len(added):]
            st.session_state["zan_shopping_new_item"] = ", ".join(remaining)
            st.session_state.shopping_error = f"Couldn't add {item}: {exc}"
            break
    else:
        st.session_state["zan_shopping_new_item"] = ""
    if added:
        try:
            st.session_state.grocery_list = store.get_shopping_items()
        except Exception:
            # Preserve the old list on a read failure; a later rerun will reload.
            pass
        st.session_state.shopping_notice = "Added to your list."


def remove_grocery_item(item_id):
    store.delete_shopping_item(item_id)
    st.session_state.grocery_list = store.get_shopping_items()


def render_html(content):
    """Render HTML directly without Markdown parsing."""
    st.html(content)


def render_delete_control(kind, item_id, label, delete_action, *, show_trigger=True, show_confirm=True):
    """Two-stage delete for every review, fridge, meal and shopping item.

    Native buttons keep Streamlit's accessibility/focus behaviour. Nothing is
    changed in Supabase until the user confirms the second action.
    """
    ident = (kind, str(item_id))
    pending_key = "_zan_delete_confirmation"
    if show_trigger and st.button(
        "×", key=f"delete_open_{kind}_{item_id}",
        help=f"Remove {label}", type="tertiary",
    ):
        st.session_state[pending_key] = ident
    if show_confirm and st.session_state.get(pending_key) == ident:
        with st.container(key=f"delete_confirm_{kind}_{item_id}"):
            st.caption(f"Remove {label}?")
            keep_col, remove_col = st.columns(2, gap="small")
            with keep_col:
                if st.button("Keep", key=f"delete_keep_{kind}_{item_id}", width="stretch"):
                    st.session_state.pop(pending_key, None)
                    st.rerun()
            with remove_col:
                if st.button("Yes, remove", key=f"delete_yes_{kind}_{item_id}",
                             width="stretch"):
                    try:
                        delete_action()
                        st.session_state.pop(pending_key, None)
                        st.session_state["_zan_deleted_notice"] = f"Removed {label}."
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Couldn't remove {label}: {exc}")


def show_deleted_notice():
    notice = st.session_state.pop("_zan_deleted_notice", None)
    if notice:
        st.toast(notice, icon="✅")


def meal_group_heading(iso_stamp):
    """Group entries in the user's UK-local calendar day; handle UTC offsets."""
    from datetime import timedelta, timezone
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/London")
    try:
        stamp = datetime.fromisoformat(str(iso_stamp or "").replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        local_day = stamp.astimezone(tz).date()
    except (TypeError, ValueError, OverflowError):
        return "Earlier"
    today = datetime.now(tz).date()
    if local_day == today:
        return "Today"
    if local_day == today - timedelta(days=1):
        return "Yesterday"
    return local_day.strftime("%A, %d %B %Y").replace(" 0", " ")


def transcribe_shopping_recording(audio_bytes):
    """Use Meta Muse Voice Transcribe; only the approved transcript is saved."""
    import io
    import json
    import os
    import wave
    import requests
    if len(audio_bytes) > 30_000_000:
        raise ValueError("Recording is too large. Please make a shorter recording.")
    with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
        if (wav.getnchannels() != 1 or wav.getsampwidth() != 2 or
                wav.getframerate() not in (16000, 24000)):
            raise ValueError("Please record a new short message using the microphone above.")
        if wav.getnframes() > wav.getframerate() * 120:
            raise ValueError("Please keep shopping-list recordings under two minutes.")
    key = os.getenv("MODEL_API_KEY")
    if not key:
        raise RuntimeError("MODEL_API_KEY is missing from your .env file.")
    data = {"mode": "PUSH_TO_TALK", "model": "muse-voice-transcribe-1.0",
            "audioEncoding": "WAV"}
    response = requests.post(
        "https://api.meta.ai/v1/asr/transcribe",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        files={
            "request": (None, json.dumps(data), "application/json"),
            "audio": ("shopping.wav", audio_bytes, "audio/wav"),
        },
        timeout=60,
    )
    response.raise_for_status()
    transcript = response.json().get("transcript", "")
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("No words were detected. Try recording again.")
    return transcript.strip()


def show_recipe_reader(recipe, recipe_id):
    """Optional browser-based TTS; no third-party text/speech model requests."""
    import json
    name = str(recipe.get("name") or "Recipe")
    bits = [f"Let's make {name}."]
    description = recipe.get("description")
    if description:
        bits.append(str(description))
    ingredients = recipe.get("ingredients") or []
    if ingredients:
        bits.append("Ingredients. " + ". ".join(str(x) for x in ingredients) + ".")
    steps = recipe.get("instructions") or []
    if steps:
        bits.append("Instructions. " + " ".join(
            f"Step {i}. {step}." for i, step in enumerate(steps, 1)
        ))
    # JSON-encode before embedding any user/model-generated recipe into a script;
    # escape closing tags and HTML metacharacters to prevent script injection.
    speech_data = json.dumps(" ".join(bits), ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    uid = str(recipe_id).replace("-", "")[:14]
    widget = f"""<div class="zan-reader" data-reader="{safe_text(uid)}">
      <div class="zan-reader-label">Listen while you cook ♡</div>
      <div class="zan-reader-actions">
        <button type="button" data-act="play">▶ Read aloud</button>
        <button type="button" data-act="pause">Ⅱ Pause</button>
        <button type="button" data-act="stop">■ Stop</button>
      </div>
      <span class="zan-reader-status" aria-live="polite">Ready to listen</span>
    </div>
    <script>
    (() => {{
      const host=document.querySelector('[data-reader="{safe_text(uid)}"]');
      if(!host || host.dataset.ready) return;
      host.dataset.ready='yes';
      const status=host.querySelector('.zan-reader-status');
      const words={speech_data};
      if(!('speechSynthesis' in window)) {{
        status.textContent='Read aloud is unavailable in this browser.';return;
      }}
      let utterance=null;
      // Browser voices are not downloads from the app. Only use Veena or Karen,
      // and show the actual voice selected so a silent fallback is never confusing.
      const chooseVoice=()=> {{
        const voices=window.speechSynthesis.getVoices()||[];
        const english=v=>/^(?:en)(?:[-_]|$)/i.test(v.lang||'') &&
          !/jester|novelty|hysterical|whisper|bubbles|bad news|good news|zarvox/i.test(v.name||'');
        const matches=(name)=>voices.filter(v=>{{
          if(!english(v))return false;
          const title=(v.name||'').trim().toLowerCase();
          return title===name || title.startsWith(name+' ') || title.startsWith(name+'(');
        }});
        const pick=arr=>arr.sort((a,b)=>
          Number(/premium|enhanced/i.test(b.name))-Number(/premium|enhanced/i.test(a.name)))[0]||null;
        return pick(matches('veena')) || pick(matches('karen')) || null;
      }};
      const voiceName=voice=>voice?.name||'Unavailable';
      const getPreferredVoice=async()=> {{
        const initial=chooseVoice();
        if(initial) return initial;
        await new Promise(resolve=>{{
          let settled=false;
          const done=()=>{{if(settled)return;settled=true;window.speechSynthesis.removeEventListener('voiceschanged',done);resolve();}};
          window.speechSynthesis.addEventListener('voiceschanged',done);
          setTimeout(done,1200);
        }});
        return chooseVoice();
      }};
      let isStarting=false;
      host.querySelector('[data-act="play"]').addEventListener('click',async()=> {{
        if(isStarting)return;
        if(window.speechSynthesis.paused && utterance) {{
          window.speechSynthesis.resume();
          status.textContent='Reading with '+voiceName(utterance.voice)+'…';return;
        }}
        isStarting=true;
        window.speechSynthesis.cancel();
        status.textContent='Preparing voice…';
        let voice=null;
        try {{voice=await getPreferredVoice();}}
        finally {{isStarting=false;}}
        if(!voice) {{
          status.textContent='Veena or Karen is not available in this browser. Install a voice and refresh.';
          return;
        }}
        const fallback=!String(voice.name||'').trim().toLowerCase().startsWith('veena');
        const voiceLabel='Voice: '+voiceName(voice)+(fallback?' (Veena not available)':'');
        utterance=new SpeechSynthesisUtterance(words);
        utterance.voice=voice;
        utterance.lang=voice.lang;
        utterance.rate=.96;utterance.pitch=1.0;
        status.textContent=voiceLabel;
        utterance.onstart=()=>status.textContent='Reading · '+voiceLabel;
        utterance.onend=()=>status.textContent='Finished ♡ · '+voiceLabel;
        utterance.onerror=()=>status.textContent='Could not play · '+voiceLabel;
        window.speechSynthesis.speak(utterance);
      }});
      host.querySelector('[data-act="pause"]').addEventListener('click',()=> {{
        if(window.speechSynthesis.speaking) {{
          window.speechSynthesis.pause();status.textContent='Paused';
        }}
      }});
      host.querySelector('[data-act="stop"]').addEventListener('click',()=> {{
        window.speechSynthesis.cancel();utterance=null;status.textContent='Stopped';
      }});
    }})();
    </script>"""
    # st.html executes trusted, locally-authored script in Streamlit >=1.55;
    # the speech text is always JSON-encoded, never interpolated as HTML.
    st.html(widget, unsafe_allow_javascript=True)


def safe_text(value):
    return escape(str(value))






def remove_review_item(prefix, item_id):
    if prefix == "fridge":
        items = st.session_state.get("detected_ingredients", [])

    elif prefix == "meal":
        result = st.session_state.get("meal_scan_result") or {}
        items = result.get("components", [])

    else:
        return

    items[:] = [
        item for item in items
        if str(item.get("_review_id")) != str(item_id)
    ]



def start_new_photo_review(prefix):
    """Discard the unconfirmed draft; the existing saved data remains untouched."""
    if prefix == "fridge":
        st.session_state.detected_ingredients = []
        st.session_state.fridge_scan_id = ""
    elif prefix == "meal":
        st.session_state.meal_scan_result = None
        st.session_state.meal_scan_id = ""
    else:
        return

    st.session_state.pop(f"{prefix}_photo_bytes", None)
    st.session_state.pop(f"{prefix}_raw_result", None)
    st.session_state.pop(f"{prefix}_scan_warning", None)


def render_scan_photo_preview(prefix):
    """Keep the exact uploaded photo visible throughout the edit-and-confirm step."""
    image_bytes = st.session_state.get(f"{prefix}_photo_bytes")
    with st.container(key=f"{prefix}_scan_photo_preview"):
        render_html('''<div class="zan-scan-photo-label">YOUR PHOTO <span>✦</span></div>''')
        if image_bytes:
            st.image(image_bytes, width="stretch")
        else:
            st.caption("Your photo isn't available. Please choose it again.")
        st.caption("Keep your photo in view while you check the list.")
        st.button(
            "Use another photo",
            key=f"{prefix}_change_photo",
            width="stretch",
            on_click=start_new_photo_review,
            args=(prefix,),
        )


def render_detection_cards(items, prefix, amount_key, amount_label):
    """Minimal review cards: tap a suggestion or edit only when needed."""
    edited_items = []
    scan_id = st.session_state.get(f"{prefix}_scan_id") or "draft"

    for item in items:
        item_id = str(item.setdefault("_review_id", uuid.uuid4().hex[:10]))
        name_key = f"{prefix}_name_{scan_id}_{item_id}"
        amount_key_widget = f"{prefix}_amount_{scan_id}_{item_id}"
        suggestion_key = f"suggest_{prefix}_{scan_id}_{item_id}"

        if name_key not in st.session_state:
            st.session_state[name_key] = str(item.get("name", ""))
        if amount_key_widget not in st.session_state:
            st.session_state[amount_key_widget] = str(item.get(amount_key, ""))

        with st.container(border=True, key=f"reviewcard_{prefix}_{scan_id}_{item_id}"):
            if str(item.get("uncertain", False)).strip().lower() in ("true", "1", "yes"):
                render_html(
                    '<div class="zan-review-caution">✧ Worth checking against the photo</div>'
                )
            st.text_input(
                "Ingredient" if prefix == "fridge" else "Food",
                placeholder="e.g. Tomatoes" if prefix == "fridge" else "e.g. Cooked rice",
                key=name_key,
            )

            alternatives = item.get("alternatives") or []
            if isinstance(alternatives, list):
                # Don't show duplicate suggestions or an option identical to the current entry.
                suggestions = []
                original = str(item.get("name", "")).strip().casefold()
                for raw in alternatives:
                    candidate = str(raw).strip()
                    if (candidate and candidate.casefold() != original and
                            candidate.casefold() not in {v.casefold() for v in suggestions}):
                        suggestions.append(candidate)
                    if len(suggestions) >= 3:
                        break
                if suggestions:
                    st.pills(
                        "Did you mean?",
                        options=suggestions,
                        selection_mode="single",
                        key=suggestion_key,
                        width="stretch",
                        wrap=True,
                        on_change=use_suggested_food,
                        args=(name_key, suggestion_key),
                    )
                    # A selected option already replaces the name immediately.
                    # Show a persistent, accessible confirmation so the edit
                    # isn't missed when two food names look very similar.
                    chosen = st.session_state.get(suggestion_key)
                    current_name = str(st.session_state.get(name_key, "")).strip()
                    if chosen and current_name == str(chosen).strip():
                        render_html(
                            '<div class="zan-review-selection" role="status">'
                            '<span class="zan-review-selection-tick" aria-hidden="true">✓</span>'
                            f'Updated to <strong>{safe_text(current_name)}</strong>'
                            '</div>'
                        )

            st.text_input(
                amount_label,
                key=amount_key_widget,
                placeholder="e.g. 4 pieces" if prefix == "fridge" else "e.g. 150",
            )
            render_delete_control(
                f"review_{prefix}", item_id,
                "this ingredient" if prefix == "fridge" else "this food",
                lambda p=prefix, iid=item_id: remove_review_item(p, iid),
            )

        edited_items.append({
            **item,
            "name": str(st.session_state[name_key]).strip(),
            amount_key: str(st.session_state[amount_key_widget]).strip(),
        })

    return edited_items


def parse_grams(value):
    """Accept values such as 150, 150g or 0.15kg."""

    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*(kg|g|grams?)?\s*",
        str(value).strip().lower()
    )

    if not match:
        return None

    amount = float(match.group(1))
    unit = match.group(2)

    if unit == "kg":
        amount *= 1000

    if amount <= 0:
        return None

    return round(amount)

def saved_scan_id(value):
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


# Give existing items stable IDs.
for item in st.session_state.inventory:
    item.setdefault("id", uuid.uuid4().hex)

for item in st.session_state.grocery_list:
    item.setdefault("id", uuid.uuid4().hex)
    item.setdefault("purchased", False)


# --------------------------------------------------
# LOAD CSS
# --------------------------------------------------

if CSS_PATH.exists():
    render_html(
        f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>"
    )
else:
    st.error("Cannot find assets/style.css")


# Additional Zān styling is loaded separately. Your original style.css stays untouched.
POLISH_CSS_PATH = BASE_DIR / "assets" / "zan_polish.css"
if POLISH_CSS_PATH.exists():
    render_html(f"<style>{POLISH_CSS_PATH.read_text(encoding='utf-8')}</style>")

# Replace the older CSS-only text cat with a real decorative sticker on Home.
# This deliberately loads after the user's customised zan_polish.css so no
# colours, card styles, or other selectors need to be replaced.
render_html("<style>.section-heading h2::after { content: none !important; display: none !important; }</style>")


# Supabase Auth runs before any private account content is rendered.
if not render_auth_gate():
    st.stop()

store = ZanStore(st.session_state["sb_client"], st.session_state["sb_user_id"])

if not st.session_state.get("_zan_data_loaded", False):
    try:
        # Import old in-memory data before replacing session lists with DB records.
        # This runs only once per authenticated Streamlit session.
        if not st.session_state.get("_zan_legacy_recipes_imported", False):
            store.import_legacy_recipes(st.session_state.get("recipes", []))
            store.import_legacy_inventory(st.session_state.get("inventory", []))
            store.import_legacy_meals(st.session_state.get("meals", []))
            store.import_legacy_shopping(st.session_state.get("grocery_list", []))
            st.session_state["_zan_legacy_recipes_imported"] = True
        st.session_state.inventory = store.get_inventory()
        st.session_state.recipes = store.get_saved_recipes()
        st.session_state.meals = store.get_meals()
        st.session_state.grocery_list = store.get_shopping_items()
        st.session_state["_zan_data_loaded"] = True
    except Exception as exc:
        st.error(f"Couldn't load your Zān account: {exc}")
        st.stop()

# Feedback from a confirmed delete appears once after the page refreshes.
show_deleted_notice()


def finish_recipe_job():
    """Save a completed Muse result once, even if the user changed pages."""
    job = st.session_state.get("_recipe_job")
    if not job or not job["future"].done() or job.get("save_failed"):
        return False
    try:
        if "result" not in job:
            try:
                job["result"] = job["future"].result()
            except Exception:
                st.session_state["_recipe_job"] = None
                st.session_state["_recipe_notice"] = (
                    "Couldn't create those recipes this time. Give it another try ♡"
                )
                return True
        if job["result"] and not job.get("saved"):
            store.save_recipe_generation(
                input_snapshot=job["input_snapshot"],
                response_payload=job["result"],
                model_name=DEFAULT_MODEL,
                request_payload={
                    "operation": "suggest_recipes",
                    "ingredients": job["input_snapshot"],
                },
            )
            job["saved"] = True
        st.session_state.recipes = store.get_saved_recipes()
        st.session_state["_recipe_job"] = None
        st.session_state["_recipe_notice"] = (
            "Fresh ideas are ready in your recipe library ♡"
            if job["result"] else "No recipe ideas this time. Try another mix of ingredients."
        )
        return True
    except Exception as exc:
        # Keep the complete Muse response in memory for a save retry; never
        # run the model again automatically because a database write failed.
        if job.get("saved"):
            st.session_state["_recipe_job"] = None
        st.session_state["_recipe_notice"] = (
            "Your ideas are ready but couldn't be saved yet. "
            "Please check your connection and try again."
        )
        job["last_error"] = str(exc)
        job["save_failed"] = True
        return False


@st.fragment(run_every="2s")
def recipe_job_status():
    job = st.session_state.get("_recipe_job")
    if job:
        if job.get("save_failed"):
            st.warning("Your new ideas are ready, but couldn't be saved just yet.")
            st.button("Try saving again", key="retry_recipe_job",
                      on_click=retry_recipe_save)
        elif job["future"].done():
            if finish_recipe_job():
                st.rerun()
            elif st.session_state.get("_recipe_job", {}).get("save_failed"):
                st.warning("Your new ideas are ready, but couldn't be saved just yet.")
                st.button("Try saving again", key="retry_recipe_job",
                          on_click=retry_recipe_save)
        else:
            st.info("New ideas are on their way ♡ You can explore other pages while we work.")


# Complete a finished request on any page navigation.
finish_recipe_job()
current_page = st.session_state.active_page


# --------------------------------------------------
# STREAMLIT NAVIGATION STYLING
# --------------------------------------------------

render_html(
    f"""
    <style>
        .st-key-nav_meals button,
        .st-key-mobile_nav_meals button,
        .st-key-nav_personal button,
        .st-key-mobile_nav_personal button,
        .st-key-nav_home button,
        .st-key-nav_fridge button,
        .st-key-nav_recipes button,
        .st-key-nav_shopping button,
        .st-key-mobile_nav_home button,
        .st-key-mobile_nav_fridge button,
        .st-key-mobile_nav_recipes button,
        .st-key-mobile_nav_shopping button {{

            min-height: 42px;
            border-radius: 12px;
            background: transparent;
            color: #806B77;
            border: 1px solid transparent;
            box-shadow: none;
            font-size: .82rem;
            font-weight: 600;
            white-space: nowrap;
        }}

        .st-key-nav_{current_page} button,
        .st-key-mobile_nav_{current_page} button {{

            background: #FBE8EF !important;
            color: #A95D7D !important;
            border: 1px solid #F0D9E3 !important;
            font-weight: 700 !important;
        }}

        .st-key-nav_kitchen button {{

            min-height: 42px;
            border-radius: 13px;
            background: #513747;
            color: white;
            border: 1px solid #513747;
            font-size: .8rem;
            font-weight: 700;
            white-space: nowrap;
        }}

        .st-key-nav_kitchen button:hover {{

            background: #A95D7D;
            color: white;
            border-color: #A95D7D;
        }}

        .st-key-mobile_navigation {{
            display: none;
        }}

        .st-key-desktop_navigation {{
            display: block;
        }}


        .st-key-mobile_navigation [data-testid="stPopover"] > button {{

            min-height: 42px;
            border-radius: 12px;
            background: white;
            color: #513747;
            border: 1px solid #F0E3E9;
            font-size: .8rem;
            font-weight: 700;
        }}

        .st-key-mobile_navigation [data-testid="stPopoverBody"] {{

            background: #FFFAFC;
            border: 1px solid #F0E3E9;
            border-radius: 15px;
        }}

        @media (max-width: 760px) {{

            .st-key-desktop_navigation {{
                display: none !important;
            }}

            .st-key-mobile_navigation {{
                display: block !important;
            }}

            .st-key-app_header [data-testid="stHorizontalBlock"] {{

                display: grid !important;
                grid-template-columns: minmax(0, 1fr) auto !important;
                align-items: center !important;
                gap: 8px !important;
            }}

            .st-key-app_header [data-testid="column"] {{

                width: auto !important;
                min-width: 0 !important;
                flex: initial !important;
            }}

            .st-key-app_header [data-testid="column"]:nth-child(1) {{
                grid-column: 1;
            }}

            .st-key-app_header [data-testid="column"]:nth-child(2) {{
                grid-column: 2;
            }}



            .st-key-nav_kitchen button {{

                min-height: 40px;
                padding: 0 9px;
                font-size: .7rem;
            }}

            .st-key-mobile_navigation [data-testid="stPopover"] > button {{

                min-height: 40px;
                padding: 0 10px;
            }}
        }}

    </style>
    """
)


# --------------------------------------------------
# RESPONSIVE HEADER
# --------------------------------------------------

with st.container(key="app_header"):

    brand_col, nav_col = st.columns(
        [1.35, 5.45],
        vertical_alignment="center",
        gap="small",
    )

    # BRAND

    with brand_col:

        render_html(
            """
            <div class="brand">

                <span class="brand-mark">z<span>♡</span></span>

                <span class="brand-copy">
                    <span class="brand-name">Zān</span>

                    <span class="brand-subtitle">
                        THE KITCHEN COMPANION
                    </span>
                </span>

            </div>
            """
        )

    pages = [
        ("Home", "home"),
        ("My fridge", "fridge"),
        ("Food diary", "meals"),
        ("Recipes", "recipes"),
        ("Shopping list", "shopping"),
        ("Personal", "personal"),
    ]


    # DESKTOP NAVIGATION

    with nav_col:

        with st.container(key="desktop_navigation"):

            nav_columns = st.columns(len(pages), gap="small")
            for column, (label, page) in zip(nav_columns, pages):

                with column:

                    st.button(
                        label,
                        key=f"nav_{page}",
                        use_container_width=True,
                        on_click=navigate,
                        args=(page,),
                    )

        # MOBILE NAVIGATION


        with st.container(key="mobile_navigation"):

            menu = st.popover(
                "☰",
                help="Open Zān navigation",
                width=105,
                key="zan_mobile_menu",
                on_change="rerun",  # Track state so a destination can close it.
            )

            with menu:

                # Give the actual dropdown content a fixed usable width.
                with st.container(width=260, gap="small"):

                    st.markdown("**Explore Zān ♡**")

                    for label, page in pages:

                        st.button(
                            label,
                            key=f"mobile_nav_{page}",
                            use_container_width=True,
                            on_click=navigate_mobile,
                            args=(page,),
                        )

    # # KITCHEN BUTTON

    # with kitchen_col:

    #     st.button(
    #         "♡ My kitchen",
    #         key="nav_kitchen",
    #         use_container_width=True,
    #         on_click=navigate,
    #         args=("fridge",),
    #     )


render_html('<div class="nav-divider"></div>')

# Read the active page after navigation callbacks.
current_page = st.session_state.active_page


# ==================================================
# HOME
# ==================================================

if current_page == "home":

    inventory_count = len(st.session_state.inventory)

    recipe_count = len(st.session_state.recipes)

    shopping_count = sum(
        1
        for item in st.session_state.grocery_list
        if not item.get("purchased", False)
    )

    render_html(
        f"""
        <main class="page-container">

            <section class="hero">

                <div class="hero-copy">

                    <div class="eyebrow">
                        <span class="eyebrow-dot"></span>
                        A LITTLE MORE MINDFUL, EVERY DAY
                    </div>

                    <h1>
                        Make more of<br>
                        what you <em>have.</em>
                    </h1>

                    <p class="hero-description">
                        Know what's in your kitchen, discover what to cook
                        and make every grocery trip count.
                    </p>

                    <div class="hero-tags">
                        <span>✳ Less food waste</span>
                        <span>♡ Smarter shopping</span>
                    </div>

                </div>

                <div class="hero-art" aria-hidden="true">

                    <div class="art-orbit orbit-one"></div>
                    <div class="art-orbit orbit-two"></div>

                    <div class="art-circle">
                        <span class="fruit fruit-one">🍓</span>
                        <span class="fruit fruit-two">🥑</span>
                        <span class="fruit fruit-three">🥬</span>
                        <span class="fruit fruit-four">🍋</span>
                        <span class="art-sparkle">✧</span>
                    </div>

                    <div class="art-note">
                        A fresher way<br>
                        to organise ♡
                    </div>

                </div>

            </section>

        </main>
        """
    )

    # Visible kitten: a *normal-flow* Streamlit image, not HTML, a background
    # URL, or a hidden zero-height overlay. The PNG is embedded here, so this
    # works even if a separate sticker file was never copied into assets/.
    # The small upward shift is decorative only: if its CSS is overridden, the
    # sticker still appears immediately below the hero instead of disappearing.
    render_html("""
        <style>
        .st-key-zan_visible_kitty {
            position: relative !important;
            z-index: 5 !important;
            transform: translateY(-55px);
            margin-bottom: -55px !important;
            pointer-events: none !important;
        }
        .st-key-zan_visible_kitty img {
            max-width: 112px !important;
            height: auto !important;
            display: block !important;
            margin-left: auto !important;
            filter: drop-shadow(0 4px 9px rgba(147,75,106,.13));
        }
        @media (max-width: 760px) {
            .st-key-zan_visible_kitty {
                transform: translateY(-35px);
                margin-bottom: -35px !important;
            }
        }
        @media (prefers-reduced-motion: reduce) {
            .st-key-zan_visible_kitty {transition: none !important;}
        }
        </style>
    """)
    with st.container(key="zan_visible_kitty"):
        _, kitten_col = st.columns([7, 2], gap="small")
        with kitten_col:
            st.image(base64.b64decode(ZAN_KITTY_PNG_BASE64), width="stretch")

    # DASHBOARD — original overview stats, now each one is a full-card link.
    # The same native Streamlit navigation callbacks power the two feature cards.
    render_html("""
        <div class="page-container">
            <section class="overview-section">
                <div class="section-heading">
                    <div>
                        <div class="eyebrow">YOUR KITCHEN, AT A GLANCE</div>
                        <h2>A little overview</h2>
                    </div>
                    <span class="section-note">Everything in its place.</span>
                </div>
            </section>
        </div>
    """)

    # The current custom CSS styles .overview-card-shell and
    # .overview-card-content. These small scoped rules prevent the older
    # negative-margin overlay approach from misaligning on mobile.
    render_html("""
        <style>
        .st-key-overview_fridge, .st-key-overview_recipes, .st-key-overview_shopping {
            position: relative !important;
            isolation: isolate;
            height: 100%;
            cursor: pointer;
        }
        .st-key-overview_fridge .overview-card-shell,
        .st-key-overview_recipes .overview-card-shell,
        .st-key-overview_shopping .overview-card-shell {
            margin-bottom: 0 !important;
            width: 100%;
        }
        .st-key-overview_fridge .overview-card-content,
        .st-key-overview_recipes .overview-card-content,
        .st-key-overview_shopping .overview-card-content {
            position: relative;
            height: 100%;
            min-height: 158px;
            transition: background .22s ease, transform .22s ease, box-shadow .22s ease;
        }
        .st-key-overview_fridge [data-testid="stButton"],
        .st-key-overview_recipes [data-testid="stButton"],
        .st-key-overview_shopping [data-testid="stButton"],
        .st-key-overview_fridge .st-key-overview_fridge_open,
        .st-key-overview_recipes .st-key-overview_recipes_open,
        .st-key-overview_shopping .st-key-overview_shopping_open {
            position: absolute !important;
            inset: 0 !important;
            z-index: 5 !important;
            width: 100% !important;
            height: 100% !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .st-key-overview_fridge [data-testid="stButton"] button,
        .st-key-overview_recipes [data-testid="stButton"] button,
        .st-key-overview_shopping [data-testid="stButton"] button {
            position: absolute !important;
            inset: 0 !important;
            width: 100% !important;
            height: 100% !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            opacity: 0 !important;
            cursor: pointer !important;
        }
        .st-key-overview_fridge:hover .overview-card-content,
        .st-key-overview_recipes:hover .overview-card-content,
        .st-key-overview_shopping:hover .overview-card-content,
        .st-key-overview_fridge:focus-within .overview-card-content,
        .st-key-overview_recipes:focus-within .overview-card-content,
        .st-key-overview_shopping:focus-within .overview-card-content {
            background: linear-gradient(180deg, #FFF7FB 0%, #FBE6F0 100%) !important;
            transform: translateY(-2px);
            box-shadow: 0 12px 28px rgba(138, 71, 104, .10) !important;
        }
        .st-key-overview_fridge:focus-within .overview-card-content,
        .st-key-overview_recipes:focus-within .overview-card-content,
        .st-key-overview_shopping:focus-within .overview-card-content {
            outline: 2px solid #C77998;
            outline-offset: 2px;
        }
        .zan-overview-arrow {
            position: absolute;
            right: 16px;
            top: 12px;
            font-size: 1rem;
            color: #B56B8D;
            opacity: .7;
            transition: transform .2s ease, opacity .2s ease;
            pointer-events: none;
        }
        .st-key-overview_fridge:hover .zan-overview-arrow,
        .st-key-overview_recipes:hover .zan-overview-arrow,
        .st-key-overview_shopping:hover .zan-overview-arrow {
            transform: translate(2px,-2px);
            opacity: 1;
        }
        @media (prefers-reduced-motion: reduce) {
          .st-key-overview_fridge .overview-card-content,
          .st-key-overview_recipes .overview-card-content,
          .st-key-overview_shopping .overview-card-content,
          .zan-overview-arrow {transition: none !important; transform: none !important;}
        }
        </style>
    """)

    overview_columns = st.columns(3, gap="medium")
    overview_cards = (
        ("fridge", "✿", inventory_count, "Ingredients tracked", "In your kitchen", "My fridge"),
        ("recipes", "♡", recipe_count, "Recipes discovered", "Ideas for later", "Recipes"),
        ("shopping", "✧", shopping_count, "To pick up", "On your shopping list", "Shopping list"),
    )
    for column, (page, symbol, count, label, note, destination) in zip(overview_columns, overview_cards):
        with column:
            with st.container(key=f"overview_{page}"):
                render_html(f"""
                    <div class="overview-card-shell">
                      <div class="overview-card-content">
                        <span class="zan-overview-arrow" aria-hidden="true">↗</span>
                        <div class="stat-icon">{symbol}</div>
                        <div class="stat-number">{count}</div>
                        <div class="stat-label">{label}</div>
                        <div class="stat-note">{note}</div>
                      </div>
                    </div>
                """)
                st.button(
                    f"Open {destination}",
                    key=f"overview_{page}_open",
                    help=f"Open {destination}",
                    width="stretch",
                    on_click=navigate,
                    args=(page,),
                )

    # Original feature cards, unchanged in appearance. An invisible native
    # Streamlit button covers each card so navigating does not reload the page.
    fridge_column, shopping_column = st.columns(2, gap="medium")

    with fridge_column:
        with st.container(key="home_inventory_card"):
            render_html("""
                <div class="feature-card">
                    <div class="feature-kicker">01 / YOUR INVENTORY</div>
                    <div class="feature-title">What's in your fridge?</div>
                    <p>Keep track of ingredients, quantities and what's best used first.</p>
                    <div class="feature-bottom"><span>View ingredients</span><span>↗</span></div>
                    <div class="feature-decoration">🥑　🥬　🍅</div>
                </div>
            """)
            st.button(
                "Open your fridge",
                key="home_inventory_open",
                help="Open your fridge inventory",
                on_click=navigate,
                args=("fridge",),
                width="stretch",
            )

    with shopping_column:
        with st.container(key="home_shopping_card"):
            render_html("""
                <div class="feature-card feature-card-pink">
                    <div class="feature-kicker">02 / YOUR NEXT SHOP</div>
                    <div class="feature-title">Only buy what you need.</div>
                    <p>Bring your grocery list together with ingredients you already have.</p>
                    <div class="feature-bottom"><span>Open shopping list</span><span>↗</span></div>
                    <div class="feature-decoration">🛒　♡　✧</div>
                </div>
            """)
            st.button(
                "Open shopping list",
                key="home_shopping_open",
                help="Open your shopping list",
                on_click=navigate,
                args=("shopping",),
                width="stretch",
            )

    # Preserve the original footer markup. The kitty is above, inside Home.
    render_html("""
        <footer class="page-footer">
            <span>Zān ♡</span>
            <span>MAKE MORE OF WHAT YOU HAVE.</span>
        </footer>
    """)


# ==================================================
# MY FRIDGE — SCAN, REVIEW AND CONFIRM
# ==================================================

elif current_page == "fridge":
    with st.container(key="fridge_page_content"):
        render_html("""
            <section class="page-intro zan-centred-intro">
                <div class="eyebrow">YOUR KITCHEN INVENTORY</div>
                <h1>My fridge <em>♡</em></h1>
                <p>Know what you have. Make more of every ingredient.</p>
            </section>
        """)

        # During review, show the actual image instead of an attachment-like uploader.
        fridge_photo = None
        if not st.session_state.get("detected_ingredients"):
            fridge_photo = st.file_uploader(
                "Take or upload a fridge photo",
                type=["jpg", "jpeg", "png"], key="fridge_photo",
            )
            if st.button("Scan fridge", key="scan_fridge", type="primary", width="stretch"):
                if fridge_photo is None:
                    st.warning("Choose a fridge photo first.")
                else:
                    try:
                        with st.spinner("Finding your ingredients..."):
                            detected = analyse_fridge(fridge_photo)
                        st.session_state.detected_ingredients = detected
                        st.session_state.fridge_raw_result = deepcopy(detected)
                        st.session_state.fridge_photo_bytes = fridge_photo.getvalue()
                        st.session_state.fridge_scan_id = ""
                        st.session_state.fridge_scan_warning = None
                        for item in detected:
                            item["_review_id"] = uuid.uuid4().hex[:10]
                        # Back up both image and Muse response immediately.
                        try:
                            st.session_state.fridge_scan_id = store.save_scan(
                                scan_type="fridge", image_bytes=st.session_state.fridge_photo_bytes,
                                model_name=DEFAULT_MODEL,
                                request_payload={"operation": "analyse_fridge"},
                                response_payload=st.session_state.fridge_raw_result,
                                prompt_version="fridge-v2",
                            )
                        except Exception:
                            st.session_state.fridge_scan_warning = (
                                "Ingredients found, but cloud backup failed. "
                                "Save to fridge will retry without rescanning."
                            )
                        if not detected:
                            st.info("No ingredients identified. Try another photo or add them manually.")
                        else:
                            # Hide the uploader and show the photo beside editable results.
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Couldn't scan your fridge: {exc}")

        detected = st.session_state.get("detected_ingredients", [])
        if detected:
            photo_column, review_column = st.columns([0.88, 1.12], gap="large")
            with photo_column:
                render_scan_photo_preview("fridge")
            with review_column:
                if st.session_state.get("fridge_scan_warning"):
                    st.warning(st.session_state["fridge_scan_warning"])
                st.markdown('<div class="zan-section-title">Review ingredients</div>', unsafe_allow_html=True)
                st.caption("Edit only what needs changing, then save.")
                scan_id = st.session_state.fridge_scan_id
                edited_items = render_detection_cards(
                    detected, "fridge", "quantity", "Quantity",
                )
                with st.expander("+ Add a missed ingredient"):
                    with st.form(f"add_fridge_{scan_id}", clear_on_submit=True):
                        new_food = st.text_input("Ingredient", placeholder="e.g. Tomatoes")
                        new_quantity = st.text_input("Quantity (optional)", placeholder="e.g. 4")
                        if st.form_submit_button("Add ingredient", width="stretch"):
                            if new_food.strip():
                                detected.append({
                                    "name": new_food.strip(),
                                    "quantity": new_quantity.strip(),
                                    "_review_id": uuid.uuid4().hex[:10],
                                })
                                st.rerun()
                            else:
                                st.warning("Enter an ingredient name.")

                if st.button(
                    "Save to fridge", key=f"save_fridge_{scan_id}",
                    type="primary", width="stretch",
                ):
                    final_items = [
                        {"name": item["name"], "quantity": item.get("quantity", "")}
                        for item in edited_items if item.get("name")
                    ]
                    if not final_items:
                        st.warning("Add at least one ingredient.")
                    else:
                        try:
                            if not saved_scan_id(scan_id):
                                image_bytes = (st.session_state.get("fridge_photo_bytes") or
                                               (fridge_photo.getvalue() if fridge_photo else None))
                                if not image_bytes:
                                    raise ValueError("Upload the photo again to back up this scan.")
                                scan_id = store.save_scan(
                                    scan_type="fridge", image_bytes=image_bytes,
                                    model_name=DEFAULT_MODEL,
                                    request_payload={"operation": "analyse_fridge"},
                                    response_payload=st.session_state.get("fridge_raw_result", detected),
                                    prompt_version="fridge-v2",
                                )
                                st.session_state.fridge_scan_id = scan_id
                            store.confirm_scan(scan_id, final_items)
                            store.add_inventory_items(final_items, scan_id=scan_id)
                            st.session_state.inventory = store.get_inventory()
                            st.session_state.detected_ingredients = []
                            st.session_state.fridge_scan_id = ""
                            st.session_state.pop("fridge_photo_bytes", None)
                            st.session_state.pop("fridge_raw_result", None)
                            st.session_state.pop("fridge_scan_warning", None)
                            st.session_state.fridge_saved_notice = f"Saved {len(final_items)} ingredients to your fridge."
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Couldn't save ingredients: {exc}")

        st.markdown('<div class="zan-section-title">In your fridge</div>', unsafe_allow_html=True)
        saved_notice = st.session_state.pop("fridge_saved_notice", None)
        if saved_notice:
            st.success(saved_notice, icon="✅")
        if not st.session_state.inventory:
            st.caption("Your saved ingredients will appear here.")
        else:
            for item in st.session_state.inventory:
                with st.container(border=True, key=f"inventory_row_{item['id']}"):
                    render_html(
                        f'<div class="zan-saved-row"><b>{safe_text(item.get("name", "Ingredient"))}</b>'
                        f'<span>{safe_text(item.get("quantity") or "")}</span></div>'
                    )
                    render_delete_control(
                        "inventory", item["id"], str(item.get("name") or "ingredient"),
                        lambda iid=item["id"]: delete_inventory_item(iid),
                    )

        with st.expander("+ Add an ingredient manually"):
            with st.form("manual_inventory_form", clear_on_submit=True):
                food = st.text_input("Ingredient", placeholder="e.g. Eggs")
                amount = st.text_input("Quantity (optional)", placeholder="e.g. 6")
                if st.form_submit_button("Add to fridge", width="stretch"):
                    if not food.strip():
                        st.warning("Enter an ingredient name.")
                    else:
                        try:
                            store.add_inventory_items([{"name": food.strip(), "quantity": amount.strip()}])
                            st.session_state.inventory = store.get_inventory()
                            st.session_state.fridge_saved_notice = f"Added {food.strip()} to your fridge ♡"
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Couldn't add ingredient: {exc}")

        st.button(
            "Find something to cook →",
            key="fridge_to_recipes",
            type="secondary",
            width="stretch",
            on_click=navigate,
            args=("recipes",),
        )

        with st.expander("Past fridge scans"):
            try:
                scans = store.get_scan_history("fridge", limit=40)
                if not scans:
                    st.caption("No previous scans yet.")
                for scan in scans:
                    created = str(scan.get("created_at", ""))[:16].replace("T", " ")
                    result = scan.get("confirmed_payload") or scan.get("response_payload") or []
                    st.markdown(f"**{created}**")
                    if isinstance(result, list):
                        st.caption(", ".join(str(x.get("name", "")) for x in result if isinstance(x, dict)))
                    st.divider()
            except Exception as exc:
                st.error(f"Couldn't load previous scans: {exc}")


# ==================================================
# MEALS — SCAN, EDIT, SAVE AND SHOW CALORIES
# ==================================================

elif current_page == "meals":
    with st.container(key="meals_page_content"):
        render_html("""
            <section class="page-intro zan-centred-intro">
                <div class="eyebrow">LITTLE MOMENTS AROUND THE TABLE</div>
                <h1>Your food diary <em>♡</em></h1>
                <p>A place for the plates you loved, with a little insight into each one.</p>
            </section>
        """)

        if st.session_state.get("diary_recipe_name"):
            st.caption(
                "Making " + st.session_state["diary_recipe_name"] +
                "? Add a photo of your plate below ♡"
            )

        meal_photo = None
        if not st.session_state.get("meal_scan_result"):
            meal_photo = st.file_uploader(
                "Take or upload a meal photo", type=["jpg", "jpeg", "png"], key="meal_photo",
            )
            if st.button("Scan my plate", key="scan_meal", type="primary", width="stretch"):
                if meal_photo is None:
                    st.warning("Choose a meal photo first.")
                else:
                    try:
                        with st.spinner("Looking at your meal..."):
                            result = analyse_meal(meal_photo)
                        if st.session_state.get("diary_recipe_name"):
                            result["meal_name"] = st.session_state["diary_recipe_name"]
                        st.session_state.meal_scan_result = result
                        st.session_state.meal_raw_result = deepcopy(result)
                        st.session_state.meal_photo_bytes = meal_photo.getvalue()
                        st.session_state.meal_scan_id = ""
                        st.session_state.meal_scan_warning = None
                        try:
                            st.session_state.meal_scan_id = store.save_scan(
                                scan_type="meal", image_bytes=st.session_state.meal_photo_bytes,
                                model_name=DEFAULT_MODEL,
                                request_payload={"operation": "analyse_meal"},
                                response_payload=st.session_state.meal_raw_result,
                                prompt_version="meal-v3",
                            )
                        except Exception:
                            st.session_state.meal_scan_warning = (
                                "Meal found, but cloud backup failed. "
                                "Save meal will retry without rescanning."
                            )
                        # Show the real photo and ingredients together during review.
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Couldn't scan your meal: {exc}")

        draft = st.session_state.get("meal_scan_result")
        if draft:
            photo_column, review_column = st.columns([0.88, 1.12], gap="large")
            with photo_column:
                render_scan_photo_preview("meal")
            with review_column:
                if st.session_state.get("meal_scan_warning"):
                    st.warning(st.session_state["meal_scan_warning"])
                st.markdown(
                    f'<div class="zan-section-title">{safe_text(draft.get("meal_name", "Your meal"))}</div>',
                    unsafe_allow_html=True,
                )
                st.caption("Correct any food names or amounts before saving.")
                scan_id = st.session_state.meal_scan_id
                edited_components = render_detection_cards(
                    draft.get("components", []), "meal", "portion_grams", "Amount (g)",
                )
                with st.expander("+ Add a missed food"):
                    with st.form(f"add_meal_food_{scan_id}", clear_on_submit=True):
                        name = st.text_input("Food", placeholder="e.g. Boiled egg")
                        grams = st.text_input("Amount (g)", placeholder="e.g. 60")
                        if st.form_submit_button("Add food", width="stretch"):
                            valid_grams = parse_grams(grams)
                            if name.strip() and valid_grams:
                                draft["components"].append({
                                    "name": name.strip(), "portion_grams": str(valid_grams),
                                    "_review_id": uuid.uuid4().hex[:10],
                                })
                                st.rerun()
                            else:
                                st.warning("Enter a food name and a valid amount in grams.")

                if st.button(
                    "Save meal", key=f"save_meal_{scan_id}", type="primary", width="stretch",
                ):
                    foods = []
                    invalid = False
                    for item in edited_components:
                        grams = parse_grams(item.get("portion_grams", ""))
                        if not item.get("name") or grams is None:
                            invalid = True
                            break
                        foods.append({"name": item["name"], "portion_grams": grams})
                    if invalid or not foods:
                        st.warning("Check every food name and amount before saving.")
                    else:
                        try:
                            with st.spinner("Calculating calories..."):
                                nutrition = calculate_meal_nutrition(foods)
                            if not saved_scan_id(scan_id):
                                image_bytes = (st.session_state.get("meal_photo_bytes") or
                                               (meal_photo.getvalue() if meal_photo else None))
                                if not image_bytes:
                                    raise ValueError("Upload the photo again to back up this scan.")
                                scan_id = store.save_scan(
                                    scan_type="meal", image_bytes=image_bytes,
                                    model_name=DEFAULT_MODEL,
                                    request_payload={"operation": "analyse_meal"},
                                    response_payload=st.session_state.get("meal_raw_result", draft),
                                    prompt_version="meal-v3",
                                )
                                st.session_state.meal_scan_id = scan_id
                            store.confirm_scan(scan_id, foods)
                            store.save_meal(
                                meal_name=draft.get("meal_name") or "Meal",
                                components=nutrition["items"],
                                total_calories=nutrition["total_calories"],
                                nutrition_source=nutrition.get("source"), scan_id=scan_id,
                            )
                            st.session_state.meals = store.get_meals()
                            st.session_state.meal_scan_result = None
                            st.session_state.meal_scan_id = ""
                            st.session_state.diary_recipe_name = None
                            st.session_state.pop("meal_photo_bytes", None)
                            st.session_state.pop("meal_raw_result", None)
                            st.session_state.pop("meal_scan_warning", None)
                            st.session_state.meal_saved_notice = f"Meal saved — approximately {nutrition['total_calories']} kcal ♡"
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Couldn't save your meal: {exc}")

        st.markdown('<div class="zan-section-title">Your recent plates</div>', unsafe_allow_html=True)
        saved_notice = st.session_state.pop("meal_saved_notice", None)
        if saved_notice:
            st.success(saved_notice, icon="✅")
        # On first visit after this update, refresh meal records from Supabase.
        # Streamlit otherwise keeps the old in-memory list without image_path fields
        # even when the updated get_meals() method has been installed.
        if not st.session_state.get("_zan_meal_photo_controls_loaded_v2"):
            try:
                st.session_state.meals = store.get_meals()
                st.session_state["_zan_meal_photo_controls_loaded_v2"] = True
            except Exception as exc:
                st.warning(f"Couldn't refresh saved meal photos: {exc}")
        if not st.session_state.meals:
            st.caption("Your saved meals will appear here.")
        else:
            previous_group = None
            for meal in st.session_state.meals:
                group = meal_group_heading(meal.get("logged_at"))
                if group != previous_group:
                    render_html(f'<div class="zan-diary-date">{safe_text(group)}</div>')
                    previous_group = group
                with st.container(border=True, key=f"meal_history_{meal['id']}"):
                    image_path = meal.get("image_path")
                    # Show the saved photo directly in every diary entry.
                    # No extra View/Hide photo action is needed.
                    if image_path:
                        photo_col, details_col = st.columns(
                            [1.2, 3.3], gap="medium", vertical_alignment="center"
                        )
                        with photo_col:
                            thumbnail = get_meal_thumbnail(image_path)
                            if thumbnail:
                                with st.container(key=f"meal_history_photo_{meal['id']}"):
                                    st.image(thumbnail, width="stretch")
                            else:
                                st.caption("Photo unavailable")
                    else:
                        details_col = st.container()
                    with details_col:
                        st.markdown(f"**{safe_text(meal.get('meal_name') or 'Meal')}**")
                        if meal.get("total_calories") is not None:
                            st.markdown(
                                f"<div class='zan-calorie-total'>~{meal['total_calories']} kcal</div>",
                                unsafe_allow_html=True,
                            )
                        stamp = str(meal.get("logged_at") or "")[:16].replace("T", " ")
                        st.caption(f"Estimated calories · {stamp}")
                        if not image_path:
                            st.caption("No photo saved with this meal")
                    with st.expander("Food breakdown"):
                        for item in meal.get("components", []):
                            st.write(
                                f"{item.get('name', 'Food')} · "
                                f"{item.get('portion_grams', '')} g · "
                                f"{item.get('calories', '—')} kcal"
                            )
                    render_delete_control(
                        "meal", meal["id"], str(meal.get("meal_name") or "this meal"),
                        lambda iid=meal["id"]: remove_meal_item(iid),
                    )

        st.button(
            "See what's in my fridge →",
            key="diary_to_fridge",
            width="stretch",
            on_click=navigate,
            args=("fridge",),
        )

        with st.expander("Past meal scans"):
            try:
                scans = store.get_scan_history("meal", limit=40)
                if not scans:
                    st.caption("No previous scans yet.")
                for scan in scans:
                    stamp = str(scan.get("created_at", ""))[:16].replace("T", " ")
                    result = scan.get("response_payload") or {}
                    st.write(f"**{result.get('meal_name', 'Meal') if isinstance(result, dict) else 'Meal'}** · {stamp}")
            except Exception as exc:
                st.error(f"Couldn't load previous scans: {exc}")


# ==================================================
# RECIPES — PICK INGREDIENTS, REUSE CACHE, SAVE HISTORY
# ==================================================

elif current_page == "recipes":
    with st.container(key="recipes_page_content"):
        render_html("""
            <section class="page-intro zan-centred-intro">
                <div class="eyebrow">MAKE SOMETHING DELICIOUS</div>
                <h1>Recipe inspiration <em>♡</em></h1>
                <p>Pick ingredients to discover new ideas, or revisit your saved recipes.</p>
            </section>
        """)
        inventory = st.session_state.inventory
        if inventory:
            st.markdown('<div class="zan-section-title">What would you like to use?</div>', unsafe_allow_html=True)
            ingredient_lookup = {}
            for item in inventory:
                name = str(item.get("name", "")).strip()
                if name:
                    ingredient_lookup.setdefault(name.casefold(), item)
            ingredient_options = [item["name"] for item in ingredient_lookup.values()]
            # Streamlit owns the selection widget state; don't modify its key after creation.
            st.session_state.recipe_ingredient_selection = [
                name for name in st.session_state.recipe_ingredient_selection
                if name in ingredient_options
            ]
            selected_names = st.pills(
                "Tap ingredients to select", options=ingredient_options,
                selection_mode="multi", key="recipe_ingredient_selection",
                width="stretch", wrap=True, persist_state="session",
            ) or []
            selected_inventory = [ingredient_lookup[name.casefold()] for name in selected_names]
            if selected_names:
                st.caption(f"{len(selected_names)} ingredients selected")
            else:
                st.caption("No selection? Find recipes will use your fridge; Surprise me picks a few ingredients.")
            busy = st.session_state.get("_recipe_job") is not None
            primary, secondary = st.columns(2, gap="small")
            with primary:
                find_recipes = st.button(
                    "Finding recipes…" if busy else "Find recipes",
                    key="generate_recipes", type="primary",
                    width="stretch", disabled=busy,
                )
            with secondary:
                fresh_recipes = st.button(
                    "Coming up with ideas…" if busy else "Surprise me",
                    key="fresh_recipes", width="stretch", disabled=busy,
                )
            if find_recipes or fresh_recipes:
                # Selected ingredients always win. With none selected, Find
                # searches using the fridge and Surprise samples 2-4 items.
                if selected_inventory:
                    cooking_inventory = selected_inventory
                elif fresh_recipes:
                    from random import SystemRandom
                    count = min(len(inventory), SystemRandom().randint(2, 4))
                    cooking_inventory = SystemRandom().sample(inventory, count)
                else:
                    cooking_inventory = inventory

                input_snapshot = sorted(
                    [{"name": str(item.get("name", "")).strip(),
                      "quantity": str(item.get("quantity") or "").strip()}
                     for item in cooking_inventory if str(item.get("name", "")).strip()],
                    key=lambda x: x["name"].casefold(),
                )
                try:
                    cached = (
                        store.find_saved_recipes_for_input(input_snapshot)
                        if find_recipes else []
                    )
                    if cached:
                        st.session_state["_recipe_notice"] = (
                            "A little déjà vu ♡ Here are some favourites from your recipe library."
                        )
                        # Put the matching collection first, so the choice has an
                        # immediately visible result even if it was generated long ago.
                        cached_ids = {r.get("saved_recipe_id") for r in cached}
                        all_recipes = store.get_saved_recipes()
                        st.session_state.recipes = sorted(
                            all_recipes,
                            key=lambda r: r.get("saved_recipe_id") not in cached_ids,
                        )
                    else:
                        st.session_state["_recipe_notice"] = None
                        st.session_state["_recipe_job"] = {
                            "future": recipe_executor().submit(
                                suggest_recipes, deepcopy(cooking_inventory)
                            ),
                            "input_snapshot": input_snapshot,
                        }
                except Exception as exc:
                    st.error(f"Couldn't find recipes: {exc}")

            if st.session_state.get("_recipe_job"):
                recipe_job_status()

            notice = st.session_state.pop("_recipe_notice", None)
            if notice:
                st.success(notice)

        else:
            st.caption("Add ingredients in My fridge to start generating recipes.")
            st.button("Go to my fridge →", key="recipe_go_fridge",
                      on_click=navigate, args=("fridge",))

        st.markdown('<div class="zan-section-title">Saved recipes ♡</div>', unsafe_allow_html=True)
        recipes = st.session_state.get("recipes", [])
        search_term = recipe_search(
            recipes,
            key="zan_live_recipe_search",
        ).strip().casefold()
        matching_recipes = [
            recipe for recipe in recipes
            if not search_term or search_term in " ".join(
                [str(recipe.get("name") or ""), str(recipe.get("description") or "")]
                + [str(x) for key in ("ingredients", "available_ingredients", "missing_ingredients")
                   for x in (recipe.get(key) or [])]
            ).casefold()
        ]
        if not recipes:
            st.caption("Your generated recipes will stay here once saved.")
        elif not matching_recipes:
            st.caption("No matches yet. Try another ingredient or recipe name.")
        else:
            st.caption(f"{len(matching_recipes)} of {len(recipes)} saved recipes")
            # One-open-at-a-time recipe accordion. Streamlit expanders cannot
            # close one another on click, so use accessible native button headers
            # and render the existing recipe body only for the selected entry.
            # No JavaScript and no changes to narration, saves, or other pages.
            visible_recipe_ids = [
                str(r.get("saved_recipe_id") or r.get("id") or str(i))
                for i, r in enumerate(matching_recipes)
            ]
            if "_zan_open_recipe_id" not in st.session_state:
                st.session_state["_zan_open_recipe_id"] = visible_recipe_ids[0]
            elif (st.session_state["_zan_open_recipe_id"] is not None
                  and st.session_state["_zan_open_recipe_id"] not in visible_recipe_ids):
                # A changed search should never leave a hidden recipe selected.
                st.session_state["_zan_open_recipe_id"] = None

            render_html("""<style>
                /* Recipe headings only; preserve Zān's existing button palette elsewhere. */
                .st-key-recipes_page_content div[class*="st-key-recipe_accordion_selected_"] button,
                .st-key-recipes_page_content div[class*="st-key-recipe_accordion_closed_"] button {
                    width: 100%; min-height: 53px;
                    display: flex; align-items: center; justify-content: flex-start;
                    padding: 12px 17px !important; text-align: left !important;
                    background: #FFFFFF !important; color: #513747 !important;
                    border: 1px solid #EEDCE4 !important; border-radius: 15px !important;
                    box-shadow: 0 3px 12px rgba(81,55,71,.035) !important;
                    transition: background .2s ease, border-color .2s ease,
                                box-shadow .2s ease !important;
                }
                .st-key-recipes_page_content div[class*="st-key-recipe_accordion_selected_"] button *,
                .st-key-recipes_page_content div[class*="st-key-recipe_accordion_closed_"] button * {
                    font-family: 'Manrope', sans-serif !important;
                    color: #513747 !important; -webkit-text-fill-color: #513747 !important;
                    font-size: .92rem !important; font-weight: 600 !important;
                    text-align: left !important;
                }
                .st-key-recipes_page_content div[class*="st-key-recipe_accordion_selected_"] button:hover,
                .st-key-recipes_page_content div[class*="st-key-recipe_accordion_closed_"] button:hover,
                .st-key-recipes_page_content div[class*="st-key-recipe_accordion_selected_"] button {
                    background: #FFF0F6 !important;
                    border-color: #E9C5D6 !important;
                    box-shadow: 0 5px 15px rgba(184,79,126,.08) !important;
                }
                .st-key-recipes_page_content div[class*="st-key-recipe_accordion_selected_"] button:focus-visible,
                .st-key-recipes_page_content div[class*="st-key-recipe_accordion_closed_"] button:focus-visible {
                    outline: 2px solid #B84F7E !important; outline-offset: 2px !important;
                }
                .st-key-recipes_page_content div[class*="st-key-recipe_accordion_body_"] {
                    background: linear-gradient(180deg, #FFFFFF, #FFFAFC) !important;
                    border: 1px solid #F0E3E9 !important;
                    border-radius: 15px !important;
                    padding: 15px 18px !important;
                    margin-bottom: 8px;
                }
                @media (max-width: 760px) {
                    .st-key-recipes_page_content div[class*="st-key-recipe_accordion_body_"] {
                        padding: 12px !important;
                    }
                }
            </style>""")
            for index, recipe in enumerate(matching_recipes):
                recipe_id = recipe.get("saved_recipe_id") or recipe.get("id") or str(index)
                title = recipe.get("name", "Recipe")
                is_open = st.session_state.get("_zan_open_recipe_id") == str(recipe_id)
                # Stable, short CSS/widget keys even if the database ID contains symbols.
                accordion_key = hashlib.sha256(str(recipe_id).encode("utf-8")).hexdigest()[:16]
                state_label = "selected" if is_open else "closed"
                with st.container(key=f"recipe_accordion_{state_label}_{accordion_key}"):
                    st.button(
                        f"{'⌄' if is_open else '›'}  {title}",
                        key=f"recipe_accordion_toggle_{accordion_key}",
                        help="Close recipe" if is_open else "Open recipe",
                        width="stretch", type="secondary",
                        on_click=toggle_open_recipe, args=(str(recipe_id),),
                    )
                if is_open:
                    with st.container(key=f"recipe_accordion_body_{accordion_key}"):
                        description = recipe.get("description")
                        if description:
                            st.write(description)
                        st.caption(
                            f"Prep: {recipe.get('prep_time', '—')} · "
                            f"Cook: {recipe.get('cook_time', '—')} · "
                            f"Serves: {recipe.get('servings', '—')}"
                        )
                        # Put the optional audio control where users can find it: at the
                        # top of each expanded recipe, before the ingredient list.
                        if elevenlabs_enabled():
                            # One tap to generate the chosen voice clone. The API key
                            # stays on the Python server, never in browser code.
                            speech_text = recipe_speech_text(recipe)
                            # The hash includes the exact spoken text, voice, model and
                            # audio settings. Identical narration can be reused even
                            # after a restart or on a second device.
                            cache_key = f"{store.user_id}/{audio_cache_key(speech_text)}"
                            audio_cache = st.session_state.setdefault("_zan_elevenlabs_audio", {})
                            natural_audio_error = None
                            storage_warning = None
                            play_clicked = st.button(
                                "♡ Read aloud with my voice",
                                key=f"elevenlabs_play_{recipe_id}", width="stretch",
                            )
                            if play_clicked and cache_key not in audio_cache:
                                try:
                                    with st.spinner("Preparing recipe audio…"):
                                        audio_bytes, source, storage_warning = get_or_create_recipe_audio(
                                            store.client, store.user_id, speech_text,
                                        )
                                        audio_cache[cache_key] = audio_bytes
                                    # Limit in-memory MP3s; all successfully uploaded
                                    # files remain reusable in private Supabase Storage.
                                    while len(audio_cache) > 4:
                                        audio_cache.pop(next(iter(audio_cache)))
                                except Exception as exc:
                                    natural_audio_error = str(exc)
                            if cache_key in audio_cache:
                                st.audio(
                                    audio_cache[cache_key], format="audio/mpeg",
                                    autoplay=play_clicked,
                                )
                                if storage_warning:
                                    st.caption(storage_warning)
                            elif natural_audio_error:
                                st.caption("Natural voice unavailable. You can still use the device reader.")
                                with st.expander("Use device voice instead"):
                                    show_recipe_reader(recipe, recipe_id)
                                st.caption(natural_audio_error)
                        elif st.toggle("🔊 Read this recipe aloud", key=f"listen_to_{recipe_id}"):
                            # Original no-cost device reader, including Meta-only mode.
                            show_recipe_reader(recipe, recipe_id)
                        st.markdown("**Ingredients**")
                        for ingredient in recipe.get("ingredients", []):
                            st.write(f"✿ {ingredient}")
                        missing = recipe.get("missing_ingredients") or []
                        if missing:
                            st.markdown("**You'll need to buy**")
                            st.caption(", ".join(str(x) for x in missing))
                            if st.button("Add missing to shopping list", key=f"recipe_shop_{recipe_id}", width="stretch"):
                                try:
                                    existing = {str(x.get("name", "")).casefold() for x in st.session_state.grocery_list}
                                    added = 0
                                    for raw_name in missing:
                                        name = str(raw_name).strip()
                                        if name and name.casefold() not in existing:
                                            store.add_shopping_item(name)
                                            existing.add(name.casefold())
                                            added += 1
                                    st.session_state.grocery_list = store.get_shopping_items()
                                    st.success(f"Added {added} items to your shopping list.")
                                except Exception as exc:
                                    st.error(f"Couldn't update shopping list: {exc}")
                        else:
                            st.caption("You have the ingredients for this recipe.")
                        st.markdown("**Instructions**")
                        for step, instruction in enumerate(recipe.get("instructions", []), start=1):
                            st.write(f"{step}. {instruction}")
                        st.button(
                            "Cooked this? Add to my food diary →",
                            key=f"recipe_to_diary_{recipe_id}",
                            width="stretch",
                            on_click=go_to_diary_with_recipe,
                            args=(title,),
                        )


# ==================================================
# SHOPPING LIST
# ==================================================

elif current_page == "shopping":
    with st.container(key="shopping_page_content"):
        render_html("""
            <section class="page-intro zan-centred-intro">
                <div class="eyebrow">SHOP WITH A LITTLE MORE INTENTION</div>
                <h1>Shopping list <em>♡</em></h1>
                <p>Everything you need, without buying what you already have.</p>
            </section>
        """)
        # One small microphone beside the *same* input used for typed shopping.
        # The completed recording is transcribed automatically by Meta. No
        # voice expander, transcription button, or duplicate confirmation form.
        entry_col, mic_col = st.columns([9, 1], gap="small", vertical_alignment="bottom")
        with mic_col:
            # The mic must receive an acknowledgement after each completed clip,
            # including failures, so it never stays stuck on "Transcribing".
            voice_result = render_shopping_mic(
                acknowledgement=st.session_state.get("_zan_voice_ack", 0)
            )
            if voice_result.wav:
                import base64
                try:
                    raw_audio = base64.b64decode(voice_result.wav, validate=True)
                    transcript = transcribe_shopping_recording(raw_audio)
                    items, hint = parse_voice_items(transcript)
                    if not items:
                        st.session_state["_zan_voice_note"] = hint or "Couldn't catch that. Try again."
                    else:
                        previous = st.session_state.get("zan_shopping_new_item", "").strip()
                        current_items = split_items(previous)
                        seen = {x.casefold() for x in current_items}
                        for item in items:
                            if item.casefold() not in seen:
                                current_items.append(item)
                                seen.add(item.casefold())
                        st.session_state["zan_shopping_new_item"] = ", ".join(current_items)
                        # The updated input is the feedback; no separate text is needed.
                        st.session_state.pop("_zan_voice_note", None)
                        if hint:
                            st.session_state["_zan_voice_note"] = hint
                except Exception:
                    st.session_state["_zan_voice_note"] = (
                        "Couldn't transcribe that. Tap the mic to try again."
                    )
                finally:
                    # A trigger is delivered once by Streamlit; acknowledge every
                    # recording (even repeated audio) to restore the mic to idle.
                    st.session_state["_zan_voice_ack"] = (
                        st.session_state.get("_zan_voice_ack", 0) + 1
                    )
                st.rerun()
        with entry_col:
            st.text_input(
                "Add to your list", placeholder="Milk, eggs, tomatoes…",
                key="zan_shopping_new_item",
            )
        voice_note = st.session_state.pop("_zan_voice_note", None)
        if voice_note:
            st.caption(voice_note)
        st.button(
            "+ Add to shopping list", key="zan_shopping_add", type="primary",
            width="stretch", on_click=add_shopping_from_input,
        )
        shopping_error = st.session_state.pop("shopping_error", None)
        if shopping_error:
            st.warning(shopping_error)

        st.markdown('<div class="zan-section-title">Your list</div>', unsafe_allow_html=True)
        shopping_notice = st.session_state.pop("shopping_notice", None)
        if shopping_notice:
            st.caption(shopping_notice)
        if not st.session_state.grocery_list:
            st.caption("Your shopping list is empty.")
        else:
            to_buy = [i for i in st.session_state.grocery_list if not i.get("purchased")]
            picked_up = [i for i in st.session_state.grocery_list if i.get("purchased")]
            if picked_up:
                st.caption(f"{len(picked_up)} of {len(st.session_state.grocery_list)} picked up ♡")
            for title, items, bought in (
                ("Still to pick up", to_buy, False),
                ("Picked up ♡", picked_up, True),
            ):
                if not items:
                    continue
                render_html(f'<div class="zan-shopping-group-title">{safe_text(title)}</div>')
                for item in items:
                    with st.container(border=True, key=f"shopping_row_{item['id']}"):
                        name = str(item.get("name") or "Item")
                        done_class = " is-done" if bought else ""
                        done_label = '<span class="zan-shopping-done-label">✓ Picked up</span>' if bought else ""
                        render_html(
                            f'<div class="zan-shopping-name{done_class}"><span>{safe_text(name)}</span>'
                            f'{done_label}</div>'
                        )
                        status_col, remove_col = st.columns([3, 1], gap="small")
                        with status_col:
                            if st.button(
                                "↶ Add back" if bought else "✓ Mark bought",
                                key=f"toggle_shopping_{item['id']}", width="stretch",
                            ):
                                try:
                                    store.update_shopping_item(item["id"], not bought)
                                    st.session_state.grocery_list = store.get_shopping_items()
                                    st.session_state.shopping_notice = (
                                        f"{name} is back on your list." if bought
                                        else f"✓ {name} marked as picked up."
                                    )
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Couldn't update item: {exc}")
                        with remove_col:
                            render_delete_control(
                                "shopping", item["id"], name,
                                lambda iid=item["id"]: remove_grocery_item(iid),
                                show_confirm=False,
                            )
                        render_delete_control(
                            "shopping", item["id"], name,
                            lambda iid=item["id"]: remove_grocery_item(iid),
                            show_trigger=False,
                        )


# ==================================================
# PERSONAL — OPTIONAL PROFILE, BMI AND LOG OUT
# ==================================================

elif current_page == "personal":
    with st.container(key="personal_page_content"):
        render_personal_page(store)
