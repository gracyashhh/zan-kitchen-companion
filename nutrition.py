import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

FDC_API_KEY = os.getenv("FDC_API_KEY", "DEMO_KEY")
FDC_BASE_URL = "https://api.nal.usda.gov/fdc/v1"


def get_energy_value(food_nutrients):
    """Extract energy in kcal per 100 g from USDA nutrient data."""

    energy_values = []

    for item in food_nutrients:
        nutrient = item.get("nutrient") or {}

        nutrient_id = str(
            item.get("nutrientId")
            or nutrient.get("id")
            or ""
        )

        nutrient_name = str(
            item.get("nutrientName")
            or nutrient.get("name")
            or ""
        ).lower()

        unit = str(
            item.get("unitName")
            or nutrient.get("unitName")
            or ""
        ).lower()

        value = item.get("value")

        if value is None:
            value = item.get("amount")

        if value is None:
            continue

        try:
            value = float(value)
        except (TypeError, ValueError):
            continue

        # Prefer the standard general energy value.
        if nutrient_id == "1008":
            return value

        if nutrient_id in {"2047", "2048"}:
            energy_values.append(value)

        elif "energy" in nutrient_name and unit in {"kcal", "kilocalories"}:
            energy_values.append(value)

    return energy_values[0] if energy_values else None


@st.cache_data(ttl=86400, show_spinner=False)
def calories_per_100g(food_name):
    """Find a generic food in USDA FoodData Central."""

    response = requests.post(
        f"{FDC_BASE_URL}/foods/search",
        params={"api_key": FDC_API_KEY},
        json={
            "query": food_name,
            "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)"],
            "pageSize": 10
        },
        timeout=20
    )

    response.raise_for_status()
    foods = response.json().get("foods", [])

    if not foods:
        raise ValueError(
            f"No nutrition database match found for '{food_name}'. "
            "Try a clearer food name."
        )

    # Search results often already contain energy information.
    for food in foods:
        energy = get_energy_value(food.get("foodNutrients", []))

        if energy is not None:
            return {
                "calories_per_100g": energy,
                "matched_food": food.get("description", food_name)
            }

    # Retrieve full details if the search result does not contain energy.
    for food in foods:
        fdc_id = food.get("fdcId")

        if not fdc_id:
            continue

        detail_response = requests.get(
            f"{FDC_BASE_URL}/food/{fdc_id}",
            params={"api_key": FDC_API_KEY},
            timeout=20
        )

        detail_response.raise_for_status()
        details = detail_response.json()

        energy = get_energy_value(details.get("foodNutrients", []))

        if energy is not None:
            return {
                "calories_per_100g": energy,
                "matched_food": details.get("description", food_name)
            }

    raise ValueError(
        f"Could not retrieve calorie information for '{food_name}'. "
        "Try a clearer food name."
    )


def calculate_meal_nutrition(components):
    """Calculate calories from confirmed food names and gram amounts."""

    results = []
    total_calories = 0

    for component in components:
        name = str(component.get("name", "")).strip()

        try:
            grams = float(component.get("portion_grams", 0))
        except (TypeError, ValueError):
            raise ValueError(f"Enter a valid amount for {name or 'each food'}.")

        if not name or grams <= 0:
            raise ValueError("Every food needs a name and an amount in grams.")

        nutrition = calories_per_100g(name)

        calories = (
            nutrition["calories_per_100g"] * grams / 100
        )

        results.append({
            "name": name,
            "portion_grams": round(grams),
            "calories": round(calories),
            "matched_food": nutrition["matched_food"]
        })

        total_calories += calories

    return {
        "total_calories": round(total_calories),
        "items": results,
        "source": "USDA FoodData Central"
    }