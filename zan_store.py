"""User-scoped Supabase data access for Zān.

Use only a user's authenticated Supabase client. Never pass a service-role key here.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps
from supabase import Client, create_client

BUCKET_NAME = "zan-private-images"
DEFAULT_MODEL = "muse-spark-1.3"


def _setting(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        value = st.secrets.get(name)
        return str(value) if value else None
    except Exception:
        return None


def create_supabase_client() -> Client:
    """Create a client using the public/anon key; RLS enforces user access."""
    url = _setting("SUPABASE_URL")
    anon_key = _setting("SUPABASE_ANON_KEY")
    if not url or not anon_key:
        raise RuntimeError(
            "Add SUPABASE_URL and SUPABASE_ANON_KEY to .env or Streamlit secrets."
        )
    return create_client(url, anon_key)


def image_without_metadata(image_bytes: bytes) -> tuple[bytes, str, str]:
    """Re-encode a photo to remove EXIF metadata before private storage."""
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=90, optimize=True)
            return output.getvalue(), "image/jpeg", ".jpg"
    except Exception as exc:
        raise ValueError("The uploaded file is not a valid image.") from exc


def make_input_hash(input_snapshot: Any) -> str:
    encoded = json.dumps(
        input_snapshot,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _data(response: Any) -> list[dict[str, Any]]:
    result = getattr(response, "data", None)
    return result if isinstance(result, list) else []


class ZanStore:
    """Database operations scoped to one currently authenticated user."""

    def __init__(self, client: Client, user_id: str):
        if not client or not user_id:
            raise ValueError("An authenticated Supabase client and user ID are required.")
        self.client = client
        self.user_id = str(user_id)

    # -------------------- PROFILE --------------------
    def get_profile(self) -> dict[str, Any]:
        rows = _data(
            self.client.table("profiles")
            .select("*")
            .eq("user_id", self.user_id)
            .limit(1)
            .execute()
        )
        return rows[0] if rows else {}

    def save_profile(self, values: dict[str, Any]) -> None:
        allowed = {
            "display_name",
            "gender",
            "height_cm",
            "weight_kg",
            "health_data_consent",
            "health_data_consent_at",
            "privacy_notice_version",
        }
        row = {key: value for key, value in values.items() if key in allowed}
        row.update({
            "user_id": self.user_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        self.client.table("profiles").upsert(row, on_conflict="user_id").execute()

    # -------------------- PHOTO SCANS --------------------
    def save_scan(
        self,
        *,
        scan_type: str,
        image_bytes: bytes,
        model_name: str = DEFAULT_MODEL,
        request_payload: dict[str, Any] | None = None,
        response_payload: dict[str, Any] | list[Any] | None = None,
        prompt_version: str | None = None,
    ) -> str:
        if scan_type not in {"fridge", "meal"}:
            raise ValueError("scan_type must be 'fridge' or 'meal'.")

        scan_id = str(uuid.uuid4())
        clean_bytes, mime_type, extension = image_without_metadata(image_bytes)
        image_path = f"{self.user_id}/{scan_id}{extension}"

        # Private bucket; RLS only permits this user's own folder.
        self.client.storage.from_(BUCKET_NAME).upload(
            path=image_path,
            file=clean_bytes,
            file_options={
                "content-type": mime_type,
                "upsert": "false",
            },
        )

        row = {
            "id": scan_id,
            "user_id": self.user_id,
            "scan_type": scan_type,
            "image_path": image_path,
            "model_name": model_name,
            "prompt_version": prompt_version,
            "request_payload": request_payload or {},
            "response_payload": response_payload or {},
        }
        try:
            self.client.table("scans").insert(row).execute()
        except Exception:
            # Avoid orphaned image files if the metadata insert fails.
            try:
                self.client.storage.from_(BUCKET_NAME).remove([image_path])
            except Exception:
                pass
            raise
        return scan_id

    def confirm_scan(self, scan_id: str, confirmed_payload: Any) -> None:
        self.client.table("scans").update({
            "confirmed_payload": confirmed_payload,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", scan_id).eq("user_id", self.user_id).execute()

    # -------------------- INVENTORY --------------------
    def add_inventory_items(self, items: list[dict[str, Any]], scan_id: str | None = None) -> None:
        rows = []
        for item in items:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            rows.append({
                "user_id": self.user_id,
                "scan_id": scan_id,
                "name": name,
                "quantity": str(item.get("quantity", "")).strip() or None,
                "expiry_date": item.get("expiry_date") or None,
                "notes": item.get("notes") or None,
                "is_active": True,
            })
        if rows:
            self.client.table("inventory_items").insert(rows).execute()

    def import_legacy_inventory(self, items: list[dict[str, Any]]) -> None:
        valid = []
        for item in items:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            valid.append({
                "name": item.get("name"),
                "quantity": item.get("quantity") or item.get("estimated_quantity", ""),
                "expiry_date": item.get("expiry_date"),
            })
        if valid:
            self.add_inventory_items(valid)

    def get_inventory(self, active_only: bool = True) -> list[dict[str, Any]]:
        query = (
            self.client.table("inventory_items")
            .select("*")
            .eq("user_id", self.user_id)
        )
        if active_only:
            query = query.eq("is_active", True)
        return _data(query.order("created_at", desc=True).execute())

    def delete_inventory_item(self, item_id: str) -> None:
        self.client.table("inventory_items").delete().eq(
            "id", item_id
        ).eq("user_id", self.user_id).execute()

    # -------------------- MEALS --------------------
    def save_meal(
        self,
        *,
        meal_name: str,
        components: list[dict[str, Any]],
        total_calories: int | None,
        scan_id: str | None = None,
        nutrition_source: str | None = None,
        logged_at: str | None = None,
    ) -> str:
        meal_id = str(uuid.uuid4())
        meal_row = {
            "id": meal_id,
            "user_id": self.user_id,
            "scan_id": scan_id,
            "meal_name": meal_name or "Meal",
            "total_calories": total_calories,
            "nutrition_source": nutrition_source,
            "logged_at": logged_at or datetime.now(timezone.utc).isoformat(),
        }
        self.client.table("meal_logs").insert(meal_row).execute()

        item_rows = []
        for index, component in enumerate(components):
            name = str(component.get("name", "")).strip()
            grams = component.get("portion_grams")
            if not name or grams is None:
                continue
            item_rows.append({
                "user_id": self.user_id,
                "meal_id": meal_id,
                "name": name,
                "portion_grams": grams,
                "calories": component.get("calories"),
                "database_match": component.get("matched_food"),
                "sort_order": index,
            })
        try:
            if item_rows:
                self.client.table("meal_items").insert(item_rows).execute()
        except Exception:
            # Keep the meal header and components consistent if detail insert fails.
            self.client.table("meal_logs").delete().eq(
                "id", meal_id
            ).eq("user_id", self.user_id).execute()
            raise
        return meal_id

    def import_legacy_meals(self, meals: list[dict[str, Any]]) -> None:
        for meal in meals:
            if not isinstance(meal, dict):
                continue
            components = meal.get("components", [])
            cleaned = []
            for item in components:
                if not isinstance(item, dict):
                    continue
                raw_grams = item.get("portion_grams", item.get("portion", 0))
                try:
                    if isinstance(raw_grams, str):
                        raw_grams = raw_grams.lower().replace("grams", "").replace("gram", "").replace("g", "").strip()
                    grams = float(raw_grams)
                except (TypeError, ValueError):
                    continue
                if item.get("name") and grams > 0:
                    cleaned.append({
                        "name": item["name"],
                        "portion_grams": grams,
                        "calories": item.get("calories"),
                        "matched_food": item.get("matched_food"),
                    })
            if cleaned:
                self.save_meal(
                    meal_name=meal.get("meal_name", "Meal"),
                    components=cleaned,
                    total_calories=meal.get("total_calories", meal.get("estimated_calories")),
                    nutrition_source=meal.get("nutrition_source"),
                )

    def get_meals(self, limit: int = 100) -> list[dict[str, Any]]:
        meals = _data(
            self.client.table("meal_logs")
            .select("*")
            .eq("user_id", self.user_id)
            .order("logged_at", desc=True)
            .limit(limit)
            .execute()
        )
        if not meals:
            return []

        meal_ids = [meal["id"] for meal in meals]
        items = _data(
            self.client.table("meal_items")
            .select("*")
            .eq("user_id", self.user_id)
            .in_("meal_id", meal_ids)
            .order("sort_order")
            .execute()
        )
        by_meal: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            by_meal.setdefault(item["meal_id"], []).append(item)
        # Link saved meal logs to the private image uploaded with their scan.
        # Only fetch scans belonging to this authenticated user.
        scan_ids = list({meal.get("scan_id") for meal in meals if meal.get("scan_id")})
        photo_paths = {}
        if scan_ids:
            scan_rows = _data(
                self.client.table("scans")
                .select("id, image_path")
                .eq("user_id", self.user_id)
                .eq("scan_type", "meal")
                .in_("id", scan_ids)
                .execute()
            )
            photo_paths = {scan["id"]: scan.get("image_path") for scan in scan_rows}
        for meal in meals:
            meal["components"] = by_meal.get(meal["id"], [])
            meal["image_path"] = photo_paths.get(meal.get("scan_id"))
        return meals

    def get_private_meal_image(self, image_path: str) -> bytes:
        """Return a meal photo from private Storage using the signed-in user's RLS."""
        if not isinstance(image_path, str) or not image_path.startswith(f"{self.user_id}/"):
            raise ValueError("This photo does not belong to the current account.")
        response = self.client.storage.from_(BUCKET_NAME).download(image_path)
        if not isinstance(response, bytes):
            raise ValueError("The saved photo could not be loaded.")
        return response

    def delete_meal(self, meal_id: str) -> None:
        self.client.table("meal_logs").delete().eq(
            "id", meal_id
        ).eq("user_id", self.user_id).execute()

    # -------------------- RECIPES --------------------
    def save_recipe_generation(
        self,
        *,
        input_snapshot: list[dict[str, Any]],
        response_payload: Any,
        model_name: str = DEFAULT_MODEL,
        request_payload: dict[str, Any] | None = None,
    ) -> str:
        generation_id = str(uuid.uuid4())
        generation_row = {
            "id": generation_id,
            "user_id": self.user_id,
            "model_name": model_name,
            "input_hash": make_input_hash(input_snapshot),
            "input_snapshot": input_snapshot,
            "request_payload": request_payload or {"operation": "suggest_recipes"},
            "response_payload": response_payload,
        }
        self.client.table("recipe_generations").insert(generation_row).execute()

        recipes = response_payload
        if isinstance(response_payload, dict):
            recipes = response_payload.get("recipes", [])
        if not isinstance(recipes, list):
            recipes = []

        rows = []
        for recipe in recipes:
            if not isinstance(recipe, dict):
                continue
            name = str(recipe.get("name", "Recipe")).strip() or "Recipe"
            rows.append({
                "user_id": self.user_id,
                "generation_id": generation_id,
                "name": name,
                "description": recipe.get("description"),
                "prep_time": str(recipe.get("prep_time", "")),
                "cook_time": str(recipe.get("cook_time", "")),
                "servings": str(recipe.get("servings", "")),
                "recipe_data": recipe,
            })
        try:
            if rows:
                self.client.table("recipes").insert(rows).execute()
        except Exception:
            self.client.table("recipe_generations").delete().eq(
                "id", generation_id
            ).eq("user_id", self.user_id).execute()
            raise
        return generation_id

    def find_saved_recipes_for_input(
        self, input_snapshot: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Return a saved generation for this exact input, without another API call."""
        input_hash = make_input_hash(input_snapshot)
        generations = _data(
            self.client.table("recipe_generations")
            .select("id")
            .eq("user_id", self.user_id)
            .eq("input_hash", input_hash)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not generations:
            return []
        return self._recipes_for_generation(generations[0]["id"])

    def _recipes_for_generation(self, generation_id: str) -> list[dict[str, Any]]:
        rows = _data(
            self.client.table("recipes")
            .select("id, generation_id, name, recipe_data, created_at")
            .eq("user_id", self.user_id)
            .eq("generation_id", generation_id)
            .order("created_at")
            .execute()
        )
        return [
            {**(row.get("recipe_data") or {}), "saved_recipe_id": row["id"]}
            for row in rows
        ]

    def get_saved_recipes(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the user's recipe history, newest first; no model call is made."""
        rows = _data(
            self.client.table("recipes")
            .select("id, generation_id, name, recipe_data, created_at")
            .eq("user_id", self.user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [
            {**(row.get("recipe_data") or {}), "saved_recipe_id": row["id"],
             "saved_at": row.get("created_at")}
            for row in rows
        ]

    def import_legacy_recipes(self, recipes: list[dict[str, Any]]) -> str | None:
        """One-time import of recipes still present in Streamlit session state."""
        valid = [item for item in recipes if isinstance(item, dict) and item.get("name")]
        if not valid:
            return None
        return self.save_recipe_generation(
            input_snapshot=[{"legacy_import": True}],
            response_payload=valid,
            model_name="existing-session-data",
            request_payload={"operation": "import_existing_session_recipes"},
        )

    # -------------------- SHOPPING --------------------
    def get_scan_history(self, scan_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = (
            self.client.table("scans")
            .select("id, scan_type, image_path, model_name, request_payload, response_payload, confirmed_payload, created_at, confirmed_at")
            .eq("user_id", self.user_id)
        )
        if scan_type:
            query = query.eq("scan_type", scan_type)
        return _data(query.order("created_at", desc=True).limit(limit).execute())

    def get_shopping_items(self) -> list[dict[str, Any]]:
        return _data(
            self.client.table("shopping_items")
            .select("*")
            .eq("user_id", self.user_id)
            .order("created_at", desc=True)
            .execute()
        )

    def import_legacy_shopping(self, items: list[dict[str, Any]]) -> None:
        for item in items:
            if isinstance(item, dict) and item.get("name"):
                self.add_shopping_item(
                    str(item["name"]),
                    quantity=item.get("quantity"),
                    purchased=bool(item.get("purchased", False)),
                )

    def add_shopping_item(
        self, name: str, quantity: str | None = None,
        source_recipe_id: str | None = None, purchased: bool = False
    ) -> None:
        name = name.strip()
        if not name:
            return
        self.client.table("shopping_items").insert({
            "user_id": self.user_id,
            "name": name,
            "quantity": quantity or None,
            "source_recipe_id": source_recipe_id,
            "purchased": bool(purchased),
        }).execute()

    def update_shopping_item(self, item_id: str, purchased: bool) -> None:
        self.client.table("shopping_items").update({
            "purchased": bool(purchased),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", item_id).eq("user_id", self.user_id).execute()

    def delete_shopping_item(self, item_id: str) -> None:
        self.client.table("shopping_items").delete().eq(
            "id", item_id
        ).eq("user_id", self.user_id).execute()
