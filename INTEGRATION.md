# Zān: database + account integration

This patch adds Supabase Auth, a user-owned Postgres database, private photo storage, recipe history, and optional personal details. It does **not** replace your current `app.py` or Muse functions: the latest working `app.py` was not included in the files available for this patch, so use the exact insertion points below rather than overwriting it with the older UI snapshot.

## A. Set up Supabase once

1. Create a Supabase project.
2. Open **SQL Editor → New query** and run all of `schema.sql`.
3. Open **Project Settings → API** and copy the Project URL and the publishable/anon key. Do not use the `service_role` key in Streamlit.
4. In **Authentication → Providers → Email**, enable email/password. Keep email confirmation enabled for a real deployment; a new user will need to confirm the email before logging in. Supabase Auth handles the password storage and hashing.
5. Add the following to your local `.env` (keep `.env` in `.gitignore`):

```dotenv
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_ANON_KEY=YOUR_PUBLIC_ANON_OR_PUBLISHABLE_KEY
```

The SQL creates a private bucket named `zan-private-images`. Photos are saved under `{user_id}/{scan_id}.jpg`; RLS prevents one user from reading another user's rows or images.

## B. Install and add imports

Add this to `requirements.txt`:

```text
supabase>=2.0.0
```

Install:

```bash
pip install -r requirements.txt
```

At the top of `app.py`, add:

```python
from auth_ui import render_auth_gate, render_personal_page
from zan_store import ZanStore, DEFAULT_MODEL
```

After your CSS is loaded and **before** the navigation/header is rendered, add:

```python
if not render_auth_gate():
    st.stop()

store = ZanStore(
    st.session_state["sb_client"],
    st.session_state["sb_user_id"],
)

# Import anything still in the old Streamlit session once, then load the
# persistent account data. Old recipes are migrated before the state is replaced.
if not st.session_state.get("_zan_data_loaded", False):
    if not st.session_state.get("_zan_legacy_recipes_imported", False):
        store.import_legacy_recipes(st.session_state.get("recipes", []))
        store.import_legacy_inventory(st.session_state.get("inventory", []))
        store.import_legacy_meals(st.session_state.get("meals", []))
        store.import_legacy_shopping(st.session_state.get("grocery_list", []))
        st.session_state["_zan_legacy_recipes_imported"] = True

    st.session_state["inventory"] = store.get_inventory()
    st.session_state["recipes"] = store.get_saved_recipes()
    st.session_state["meals"] = store.get_meals()
    st.session_state["grocery_list"] = store.get_shopping_items()
    st.session_state["_zan_data_loaded"] = True
```

Add `"personal"` to `VALID_PAGES` if you have that set, and add `("Personal", "personal")` to your navigation page list. Add this page branch:

```python
elif current_page == "personal":
    render_personal_page(store)
```

The Personal page includes optional gender, height and weight. Users must explicitly choose to save those details; choosing not to save clears them. BMI is calculated from saved height and weight and is not stored separately. Gender is not used in the BMI formula.

## C. Persist fridge scans and confirmed ingredients

After `analyse_fridge(uploaded)` succeeds, save both the uploaded photo and the structured Muse response. Use the same result object that you already show for user editing:

```python
fridge_result = analyse_fridge(uploaded)
fridge_scan_id = store.save_scan(
    scan_type="fridge",
    image_bytes=uploaded.getvalue(),
    model_name=DEFAULT_MODEL,
    request_payload={"operation": "analyse_fridge"},
    response_payload=fridge_result,
    prompt_version="fridge-v1",
)
st.session_state["fridge_scan_id"] = fridge_scan_id
st.session_state["detected_ingredients"] = fridge_result
```

When the user taps **Save to fridge**, after your existing validation and editing, persist the exact final values:

```python
store.confirm_scan(fridge_scan_id, items_to_save)
store.add_inventory_items(items_to_save, scan_id=fridge_scan_id)
st.session_state["inventory"] = store.get_inventory()
```

`items_to_save` should use the existing simple shape `[{"name": "Tomatoes", "quantity": "4"}, ...]`.

## D. Persist meal photos, Muse responses and confirmed meal logs

Immediately after `analyse_meal(uploaded)` succeeds:

```python
meal_result = analyse_meal(uploaded)
meal_scan_id = store.save_scan(
    scan_type="meal",
    image_bytes=uploaded.getvalue(),
    model_name=DEFAULT_MODEL,
    request_payload={"operation": "analyse_meal"},
    response_payload=meal_result,
    prompt_version="meal-v1",
)
st.session_state["meal_scan_id"] = meal_scan_id
st.session_state["meal_scan_result"] = meal_result
```

When the user taps **Save meal**, you already have confirmed names, gram amounts and the calorie result from your nutrition lookup. Save them together:

```python
store.confirm_scan(meal_scan_id, foods_to_save)
store.save_meal(
    meal_name=meal_name,
    components=nutrition["items"],
    total_calories=nutrition["total_calories"],
    nutrition_source=nutrition.get("source"),
    scan_id=meal_scan_id,
)
st.session_state["meals"] = store.get_meals()
```

Keep the API response from the photo scan in `scans.response_payload`; the edited/confirmed list is separately kept in `scans.confirmed_payload`.

## E. Save recipes and reuse them instead of calling Muse again

The recipe page should load saved recipes from `st.session_state["recipes"]`; it must not call `suggest_recipes()` just because the page opens or reruns. The one-time migration block above imports older recipes that still exist in the current Streamlit session before loading the saved history. Recipes already lost when an earlier session ended cannot be recovered.

Replace the body of your existing **Generate recipes** button with this pattern. `selected_inventory` is the same list of selected inventory items you already pass to `suggest_recipes()`:

```python
input_snapshot = [
    {
        "name": item.get("name", ""),
        "quantity": item.get("quantity", ""),
    }
    for item in selected_inventory
]

# Reuse the newest identical result first: no Muse request and no API cost.
saved_match = store.find_saved_recipes_for_input(input_snapshot)
if saved_match:
    # Keep the whole recipe history visible, not only this matching generation.
    st.session_state["recipes"] = store.get_saved_recipes()
    st.success("Loaded your saved recipe ideas.")
else:
    generated = suggest_recipes(selected_inventory)  # the existing Muse function
    store.save_recipe_generation(
        input_snapshot=input_snapshot,
        response_payload=generated,
        model_name=DEFAULT_MODEL,
        request_payload={"operation": "suggest_recipes", "ingredients": input_snapshot},
    )
    st.session_state["recipes"] = store.get_saved_recipes()
```

For a deliberate new API generation with the same ingredients, add a separate **Generate new ideas** button that calls `suggest_recipes()` and then `save_recipe_generation()` without the cache lookup. Never generate on page load. The recipe history returned by `store.get_saved_recipes()` includes older saved recipes across sessions.

## F. Make the Fridge and Meals pages match the rest of the design

1. Wrap the **entire contents** of the Fridge page branch in:

```python
with st.container(key="fridge_page_content"):
    # existing full Fridge page branch content, indented one level
```

2. Do the same for Meals:

```python
with st.container(key="meals_page_content"):
    # existing full Meals page branch content, indented one level
```

3. In `render_detection_cards()`, change the remove control to a small icon button:

```python
st.button(
    "×",
    key=f"remove_{prefix}_{scan_id}_{item_id}",
    help="Remove this item",
    type="tertiary",
    on_click=remove_review_item,
    args=(prefix, item_id),
)
```

4. Give your save buttons these keys so the supplied CSS can style them:

```python
# Fridge
st.button("Save to fridge", key="save_fridge", type="primary", use_container_width=True)

# Meal
st.button("Save meal", key="save_meal", type="primary", use_container_width=True)
```

Keep your existing `if` handling around those buttons; these are key/type/label examples, not extra buttons to add alongside the originals. Also use `key="scan_fridge"` / `key="scan_meal"` for the scan actions and `key="recipe_generate"` for the recipe generation action.

Append `ui_polish.css` to the very end of `assets/style.css`.

## G. Data layout

- `profiles`: account display name and optional personal details / consent.
- `scans`: fridge/meal scan metadata, private photo path, structured Muse response, and user-confirmed corrections.
- `inventory_items`: the user's current fridge/pantry items.
- `meal_logs` + `meal_items`: saved meals and their confirmed food portions/calories.
- `recipe_generations` + `recipes`: every Muse recipe response, original ingredient snapshot, and individual saved recipes.
- `shopping_items`: shopping list and purchased state.
- `zan-private-images`: private object storage for uploaded photos.

Passwords are not copied into `profiles`. Supabase Auth handles them. Do not put a Supabase `service_role` key in `.env` or Streamlit secrets used by this app; the app uses the anon/publishable key with RLS.

## H. Important before real users

This is a hackathon-ready persistence foundation, not a completed privacy/compliance review. Health-related profile fields are opt-in and the schema stores the consent time and notice version. Before opening this to the public, add a clear privacy notice, retention/deletion controls (including deleting private storage objects and the Auth account), and review the lawful basis / Article 9 condition for any health-data processing. Keep the bucket private. The food photos and scan data are private account data and should not be exposed in public links.
