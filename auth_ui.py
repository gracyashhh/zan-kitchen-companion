"""Streamlit email/password authentication and optional Personal page for Zān."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

from zan_store import create_supabase_client

PRIVACY_NOTICE_VERSION = "2026-11-03"


def _save_authenticated_user(client: Any, response: Any) -> bool:
    user = getattr(response, "user", None)
    session = getattr(response, "session", None)
    if not user or not session:
        return False

    st.session_state["sb_client"] = client
    st.session_state["sb_user_id"] = str(user.id)
    st.session_state["sb_user_email"] = getattr(user, "email", "") or ""
    return True


def render_auth_gate() -> bool:
    """Render login/signup and return True only for an authenticated session."""
    if st.session_state.get("sb_client") and st.session_state.get("sb_user_id"):
        return True

    st.html(
        """
        <div class="page-intro auth-intro">
          <div class="eyebrow">WELCOME TO YOUR KITCHEN</div>
          <h1>Make more of <em>what you have.</em></h1>
          <p>Sign in to keep your fridge, meals and recipes saved to your account.</p>
        </div>
        """,
    )

    try:
        client = create_supabase_client()
    except Exception as exc:
        st.error(str(exc))
        st.info("Set up Supabase and add its URL and anon key to your .env file first.")
        return False

    login_tab, signup_tab = st.tabs(["Log in", "Create account"])

    with login_tab:
        with st.form("zan_login_form"):
            email = st.text_input("Email", placeholder="you@example.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button(
                "Log in", type="primary", width="stretch"
            )

        if submitted:
            if not email.strip() or not password:
                st.warning("Enter your email and password.")
            else:
                try:
                    response = client.auth.sign_in_with_password({
                        "email": email.strip(),
                        "password": password,
                    })
                    if _save_authenticated_user(client, response):
                        st.rerun()
                    st.error("Sign-in did not return an active session. Check your email confirmation.")
                except Exception as exc:
                    st.error(f"Couldn't log in: {exc}")

    with signup_tab:
        st.caption(
            "Photos you upload are sent to Muse Spark for food analysis and saved "
            "in your private Zān account. Your scan results, meal logs and saved "
            "recipes stay linked to your account so you can return to them."
        )
        with st.form("zan_signup_form"):
            email = st.text_input("Email", placeholder="you@example.com", key="signup_email")
            password = st.text_input(
                "Create a password", type="password", key="signup_password"
            )
            confirm = st.text_input(
                "Confirm password", type="password", key="signup_confirm"
            )
            submitted = st.form_submit_button(
                "Create account", type="primary", width="stretch"
            )

        if submitted:
            if not email.strip() or not password:
                st.warning("Enter an email and password.")
            elif len(password) < 8:
                st.warning("Use a password with at least 8 characters.")
            elif password != confirm:
                st.warning("The passwords don't match.")
            else:
                try:
                    response = client.auth.sign_up({
                        "email": email.strip(),
                        "password": password,
                    })
                    if _save_authenticated_user(client, response):
                        st.rerun()
                    else:
                        st.success(
                            "Account created. Check your email to confirm it, "
                            "then come back and log in."
                        )
                except Exception as exc:
                    st.error(f"Couldn't create your account: {exc}")

    st.caption("Passwords are managed by Supabase Auth. Zān does not store or read your password.")
    return False


def _save_personal_on_change(store: Any) -> None:
    """Save opted-in fields immediately when the user finishes an edit."""
    height = st.session_state.get("zan_personal_height")
    weight = st.session_state.get("zan_personal_weight")
    name = str(st.session_state.get("zan_personal_name") or "").strip()
    gender_choice = st.session_state.get("zan_personal_gender")
    gender = None if gender_choice == "Prefer not to say" else gender_choice

    has_measurements = height is not None or weight is not None
    current_time = datetime.now(timezone.utc).isoformat()

    try:
        store.save_profile({
            "display_name": name or None,
            "gender": gender,
            "height_cm": float(height) if height is not None else None,
            "weight_kg": float(weight) if weight is not None else None,
            "health_data_consent": has_measurements,
            "health_data_consent_at": current_time if has_measurements else None,
            "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        })
        st.session_state["zan_personal_status"] = "saved"
    except Exception as exc:
        st.session_state["zan_personal_status"] = f"error: {exc}"


def render_personal_page(store: Any) -> None:
    st.markdown(
        """
        <section class="page-intro zan-centred-intro">
          <div class="eyebrow">A LITTLE SPACE FOR YOU</div>
          <h1>Your space <em>♡</em></h1>
          <p>The details you choose to share, all in one place.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.caption(f"Signed in as {st.session_state.get('sb_user_email', '')}")
    profile = store.get_profile()
    user_id = st.session_state.get("sb_user_id")

    gender_options = ["Prefer not to say", "Woman", "Man", "Non-binary", "Another identity"]
    saved_gender = str(profile.get("gender") or "")
    if saved_gender not in gender_options:
        saved_gender = "Prefer not to say"
    defaults = {
        "zan_personal_name": profile.get("display_name") or "",
        "zan_personal_gender": saved_gender,
        "zan_personal_height": float(profile["height_cm"]) if profile.get("height_cm") is not None else None,
        "zan_personal_weight": float(profile["weight_kg"]) if profile.get("weight_kg") is not None else None,
    }
    new_login = st.session_state.get("_zan_profile_loaded_for") != user_id
    for key, value in defaults.items():
        # Streamlit can discard widget state when users visit another page.
        # Reload missing fields from the saved profile, never from a blank default.
        if new_login or key not in st.session_state:
            st.session_state[key] = value
    st.session_state["_zan_profile_loaded_for"] = user_id

    with st.container(border=True, key="zan_profile_fields"):
        st.text_input(
            "Name (optional)",
            key="zan_personal_name",
            placeholder="How should Zān greet you?",
            on_change=_save_personal_on_change,
            args=(store,),
        )

        st.selectbox(
            "Gender (optional)",
            ["Prefer not to say", "Woman", "Man", "Non-binary", "Another identity"],
            key="zan_personal_gender",
            on_change=_save_personal_on_change,
            args=(store,),
        )

        left, right = st.columns(2, gap="small")
        with left:
            st.number_input(
                "Height (cm)",
                min_value=50.0,
                max_value=260.0,
                step=0.5,
                value=None,
                format="%.1f",
                placeholder="Optional",
                key="zan_personal_height",
                on_change=_save_personal_on_change,
                args=(store,),
            )
        with right:
            st.number_input(
                "Weight (kg)",
                min_value=10.0,
                max_value=500.0,
                step=0.5,
                value=None,
                format="%.1f",
                placeholder="Optional",
                key="zan_personal_weight",
                on_change=_save_personal_on_change,
                args=(store,),
            )

        status = st.session_state.get("zan_personal_status", "")
        if status == "saved":
            st.caption("✓ Saved")
        elif status.startswith("error: "):
            st.error("Your changes weren't saved. Check your connection and try editing again.")

    height = st.session_state.get("zan_personal_height")
    weight = st.session_state.get("zan_personal_weight")
    if height is not None and weight is not None and height > 0:
        bmi = float(weight) / ((float(height) / 100) ** 2)
        st.metric("Your BMI", f"{bmi:.1f}")

    st.divider()
    if st.button("Log out", key="zan_logout", type="secondary", width="stretch"):
        try:
            st.session_state["sb_client"].auth.sign_out()
        finally:
            for key in (
                "sb_client", "sb_user_id", "sb_user_email",
                "sb_access_token", "sb_refresh_token",
                "_zan_data_loaded", "_zan_legacy_recipes_imported",
                "_zan_profile_loaded_for", "zan_personal_name",
                "zan_personal_gender", "zan_personal_height",
                "zan_personal_weight", "zan_personal_status",
                "_recipe_job", "_recipe_notice", "diary_recipe_name",
                "inventory", "recipes", "meals", "grocery_list",
                "detected_ingredients", "meal_scan_result",
                "fridge_scan_id", "meal_scan_id",
            ):
                st.session_state.pop(key, None)
        st.session_state["active_page"] = "home"
        st.rerun()
