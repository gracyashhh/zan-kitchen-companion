
import os
import json
import base64

from io import BytesIO
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageOps
import uuid
load_dotenv()

MODEL = "muse-spark-1.3"


def get_client():
    api_key = os.getenv("MODEL_API_KEY")

    if not api_key:
        raise RuntimeError(
            "MODEL_API_KEY is missing. Check your .env file."
        )

    return OpenAI(
        base_url="https://api.meta.ai/v1",
        api_key=api_key
    )


def prepare_image(uploaded_image):
    """Convert uploaded images into optimised JPEG data URLs."""

    image = Image.open(
        BytesIO(uploaded_image.getvalue())
    )

    image = ImageOps.exif_transpose(image)
    image.thumbnail((1600, 1600))
    image = image.convert("RGB")

    buffer = BytesIO()

    image.save(
        buffer,
        format="JPEG",
        quality=85,
        optimize=True
    )

    encoded = base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

    return f"data:image/jpeg;base64,{encoded}"


def ask_muse_about_image(uploaded_image, prompt):
    """Send one image and a prompt to Muse Spark."""

    image_url = prepare_image(uploaded_image)

    client = get_client()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url
                        }
                    }
                ]
            }
        ]
    )

    result = response.choices[0].message.content

    if not result:
        raise RuntimeError(
            "Muse Spark returned an empty response."
        )

    cleaned = result.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "", 1)
        cleaned = cleaned.replace("```", "").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1:
        raise ValueError(
            f"Muse Spark did not return valid JSON: {result}"
        )

    return json.loads(cleaned[start:end + 1])


def parse_bool(value, default=False):
    """Safely interpret boolean values returned by the model."""

    if isinstance(value, bool):
        return value

    if value is None:
        return default

    return str(value).strip().lower() in {
        "true", "yes", "1"
    }


def clean_alternatives(item):
    """Return up to three valid alternative food names."""

    alternatives = item.get("alternatives", [])

    if not isinstance(alternatives, list):
        return []

    cleaned = []

    for option in alternatives:

        name = str(option).strip()

        if name and name.casefold() not in {
            existing.casefold() for existing in cleaned
        }:
            cleaned.append(name)

        if len(cleaned) == 3:
            break

    return cleaned

# --------------------------------------------------
# FRIDGE RECOGNITION
# --------------------------------------------------


def analyse_fridge(uploaded_image):

    prompt = """
    Identify visible food ingredients and grocery products
    in this fridge or pantry photograph.

    Return JSON in this structure:

    {
      "ingredients": [
        {
          "name": "Tomatoes",
          "quantity": "Approximately 4 pieces",
          "uncertain": false,
          "alternatives": []
        },
        {
          "name": "Possibly chickpeas",
          "quantity": "One container",
          "uncertain": true,
          "alternatives": [
            "Soya chunks",
            "Cooked chickpeas"
          ]
        }
      ]
    }

    Rules:
    - Identify only visibly distinguishable food items.
    - Do not invent hidden ingredients.
    - Do not guess expiry or purchase dates.
    - Quantity estimates must be approximate.
    - Set uncertain to true when identification or quantity
      needs user verification.
    - When a food could be confused with another, provide
      up to three plausible alternative food names.
    - Do not use colour or texture descriptions as a substitute
      for an ingredient name.
    - If a food cannot be identified, use "Unidentified food".
    - Do not pretend that alternatives are confirmed.
    - Return an empty ingredients array if nothing can be identified.
    - Return valid JSON only.
    """

    result = ask_muse_about_image(
        uploaded_image,
        prompt
    )

    ingredients = result.get("ingredients", [])

    if not isinstance(ingredients, list):
        raise ValueError("Unexpected fridge response format.")

    cleaned = []

    for item in ingredients:

        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()

        if not name:
            continue

        cleaned.append({
            "name": name,
            "quantity": str(
                item.get("quantity", "")
            ).strip(),
            "uncertain": parse_bool(
                item.get("uncertain"),
                default=True
            ),
            "alternatives": clean_alternatives(item)
        })

    return cleaned


# --------------------------------------------------
# MEAL RECOGNITION
# --------------------------------------------------



def analyse_meal(uploaded_image):
    """Detect visible foods, rough portions and visually plausible alternatives."""
    prompt = """
    You are looking at a photo of a prepared meal.
    Identify each food component and estimate its edible portion in grams.

    Return ONLY a JSON object with this exact format:
    {
      "meal_name": "Short, friendly dish name",
      "components": [
        {
          "name": "Cooked white rice",
          "portion_grams": 150,
          "uncertain": false,
          "alternatives": ["Cooked basmati rice", "Cooked jasmine rice"]
        },
        {
          "name": "Grilled paneer",
          "portion_grams": 100,
          "uncertain": true,
          "alternatives": ["Grilled tofu", "Grilled chicken"]
        }
      ]
    }

    Rules:
    - Return only visible food; no invented ingredients or hidden oil.
    - Use a name that helps match an ordinary food nutrition database.
    - Include identifiable preparation state (cooked, fried, boiled, etc.).
    - Guess an approximate edible weight in grams for each component.
    - Set uncertain=true if the visual identity is ambiguous.
    - When plausible visually, suggest up to 3 alternative food names a
      person can tap if you misidentified the component. Suggestions should
      be actual distinct possible foods or variants, never guesses that are
      not supported by the visible photo.
    - If the identification is unambiguous, alternatives can be [].
    - Do not estimate calories or nutritional values.
    - Use numeric portion_grams and Boolean uncertain values.
    - Return no markdown, only valid JSON.
    """

    result = ask_muse_about_image(uploaded_image, prompt)
    if not isinstance(result, dict):
        raise ValueError("The meal scan returned an unexpected result.")

    components = []
    raw_components = result.get("components", [])
    if not isinstance(raw_components, list):
        raise ValueError("The meal scan returned an unexpected food list.")

    for item in raw_components:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            amount = round(float(item.get("portion_grams") or 0))
        except (ValueError, TypeError):
            amount = 0
        components.append({
            "name": name,
            "portion_grams": str(amount) if amount > 0 else "",
            "uncertain": parse_bool(item.get("uncertain"), default=True),
            "alternatives": [
                option for option in clean_alternatives(item)
                if option.casefold() != name.casefold()
            ],
            "_review_id": uuid.uuid4().hex[:10],
        })

    return {
        "meal_name": str(result.get("meal_name") or "Meal").strip(),
        "components": components,
    }


# --------------------------------------------------
# RECIPE SUGGESTIONS FROM FRIDGE INVENTORY
# --------------------------------------------------


def suggest_recipes(selected_inventory):

    if not selected_inventory:
        return []

    selected = []

    for item in selected_inventory:

        name = str(item.get("name", "")).strip()
        quantity = str(item.get("quantity", "")).strip()

        if name:
            selected.append({
                "name": name,
                "quantity": quantity
            })

    prompt = f"""
    You are Zān, an intelligent kitchen companion.

    The user specifically selected these ingredients to cook with:

    {json.dumps(selected, ensure_ascii=False)}

    Suggest exactly 3 practical and appealing recipes.

    IMPORTANT:
    - Build every recipe around the selected ingredients.
    - Do not use other ingredients from the user's unselected
      inventory.
    - Do not force every selected ingredient into every recipe.
    - Prefer recipes that use two or more selected ingredients
      when practical.
    - Common pantry basics such as salt, pepper, oil and water
      can be assumed.
    - Other required ingredients must be listed as missing.
    - Clearly distinguish available and missing ingredients.
    - Avoid recipes that require excessive additional shopping.
    - Do not provide calorie counts, nutrition or health advice.

    Return JSON only, in this structure:

    {{
      "recipes": [
        {{
          "name": "Recipe name",
          "description": "Short appealing description",
          "prep_time": "10 minutes",
          "cook_time": "20 minutes",
          "servings": "2",
          "ingredients": [
            "200 g chicken",
            "1 onion"
          ],
          "available_ingredients": [
            "Chicken",
            "Onion"
          ],
          "missing_ingredients": [
            "Garlic"
          ],
          "instructions": [
            "Prepare the ingredients.",
            "Cook the chicken.",
            "Combine and serve."
          ]
        }}
      ]
    }}
    """

    client = get_client()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    result = response.choices[0].message.content

    if not result:
        raise RuntimeError("Muse Spark returned no recipes.")

    cleaned = result.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "", 1)
        cleaned = cleaned.replace("```", "").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("Muse Spark returned invalid recipe JSON.")

    payload = json.loads(cleaned[start:end + 1])
    recipes = payload.get("recipes", [])

    if not isinstance(recipes, list):
        raise ValueError("Unexpected recipe response format.")

    cleaned_recipes = []

    for recipe in recipes:

        if not isinstance(recipe, dict):
            continue

        name = str(recipe.get("name", "")).strip()

        if not name:
            continue

        def clean_list(key):
            value = recipe.get(key, [])

            if not isinstance(value, list):
                return []

            return [
                str(entry).strip()
                for entry in value
                if str(entry).strip()
            ]

        cleaned_recipes.append({
            "id": uuid.uuid4().hex,
            "name": name,
            "description": str(
                recipe.get("description", "")
            ).strip(),
            "prep_time": str(
                recipe.get("prep_time", "")
            ).strip(),
            "cook_time": str(
                recipe.get("cook_time", "")
            ).strip(),
            "servings": str(
                recipe.get("servings", "")
            ).strip(),
            "ingredients": clean_list("ingredients"),
            "available_ingredients": clean_list(
                "available_ingredients"
            ),
            "missing_ingredients": clean_list(
                "missing_ingredients"
            ),
            "instructions": clean_list("instructions")
        })

    return cleaned_recipes
