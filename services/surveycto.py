from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from pathlib import Path
from functools import lru_cache

import requests
import streamlit as st
import json
try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None

try:
    from streamlit_js_eval import streamlit_js_eval as _streamlit_js_eval
except Exception:
    _streamlit_js_eval = None

SURVEYCTO_SERVER = "act4performance"
BASE_URL = f"https://{SURVEYCTO_SERVER}.surveycto.com"
LOGIN_PAGE_URL = f"{BASE_URL}/index.html"

_SS_USER = "scto_username"
_SS_OK = "scto_logged_in"
_SS_TEST_URL = "scto_test_attachment_url"
_SS_PASS_LEGACY = "scto_password"
ENABLE_BROWSER_STORAGE_ENV = "WASH_ENABLE_BROWSER_STORAGE"
AUTH_FINGERPRINT_KEY = "tool6_auth_fingerprint"
DEFAULT_REVIEW_STATUS = "approved|pending"


def _get_secret_text(key: str) -> str:
    # 1) Streamlit secrets (when app runs via streamlit)
    try:
        value = str(st.secrets.get(key, "")).strip()
        if value:
            return value
        # Some deployments store keys under nested sections.
        secrets_map: Dict[str, Any]
        if hasattr(st.secrets, "to_dict"):
            secrets_map = st.secrets.to_dict()  # type: ignore[assignment]
        else:
            secrets_map = dict(st.secrets)
        nested = _find_key_recursively(secrets_map, key)
        if nested is not None and str(nested).strip():
            return str(nested).strip()
    except Exception:
        pass
    # 2) Environment variables
    value = str(os.getenv(key, "")).strip()
    if value:
        return value
    # 3) Local .streamlit/secrets.toml (for CLI/testing contexts)
    secrets_map = _load_local_secrets_toml()
    raw = secrets_map.get(key, "")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    nested = _find_key_recursively(secrets_map, key)
    return str(nested).strip() if nested is not None else ""


def _find_key_recursively(data: Any, wanted_key: str) -> Any:
    if isinstance(data, dict):
        if wanted_key in data:
            return data.get(wanted_key)
        for value in data.values():
            found = _find_key_recursively(value, wanted_key)
            if found is not None:
                return found
    return None


@lru_cache(maxsize=1)
def _load_local_secrets_toml() -> Dict[str, Any]:
    candidates = [
        Path.cwd() / ".streamlit" / "secrets.toml",
        Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml",
    ]
    for path in candidates:
        try:
            if path.exists():
                content = path.read_text(encoding="utf-8")
                if tomllib is not None:
                    return tomllib.loads(content)
                # Minimal fallback parser for top-level KEY = "VALUE" pairs.
                parsed: Dict[str, Any] = {}
                for raw_line in content.splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#") or line.startswith("["):
                        continue
                    if "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key:
                        parsed[key] = value
                return parsed
        except Exception:
            continue
    return {}


def _credentials_from_secrets() -> Tuple[str, str]:
    username = _get_secret_text("SURVEYCTO_USERNAME") or _get_secret_text("SCTO_USERNAME")
    password = _get_secret_text("SURVEYCTO_PASSWORD") or _get_secret_text("SCTO_PASSWORD")
    return username, password


def _resolve_auth_credentials() -> Tuple[str, str]:
    username = str(st.session_state.get("scto_username", "")).strip()
    password = str(st.session_state.get("scto_password", "")).strip()
    if username and password:
        return username, password
    return _credentials_from_secrets()


def _browser_storage_enabled() -> bool:
    v = os.getenv(ENABLE_BROWSER_STORAGE_ENV, "")
    return bool(_streamlit_js_eval) and str(v).strip().lower() in {"1", "true", "yes", "on"}


def _ss_get(key: str) -> str:
    if not _browser_storage_enabled():
        return ""
    v = _streamlit_js_eval(
        js_expressions=f"sessionStorage.getItem('{key}')",
        key=f"ss_get_{key}",
        want_output=True,
    )
    if v in (None, "null"):
        return ""
    return str(v)


def _ss_set(key: str, value: str) -> None:
    if not _browser_storage_enabled():
        return
    value = (value or "").replace("\\", "\\\\").replace("'", "\\'")
    _streamlit_js_eval(
        js_expressions=f"sessionStorage.setItem('{key}', '{value}')",
        key=f"ss_set_{key}",
        want_output=False,
    )


def _ss_remove(key: str) -> None:
    if not _browser_storage_enabled():
        return
    _streamlit_js_eval(
        js_expressions=f"sessionStorage.removeItem('{key}')",
        key=f"ss_rm_{key}",
        want_output=False,
    )


def _set_auth_fingerprint(username: str, logged_in: bool) -> None:
    if logged_in and username:
        st.session_state[AUTH_FINGERPRINT_KEY] = f"{username.strip().lower()}|1"
    else:
        st.session_state[AUTH_FINGERPRINT_KEY] = ""


def load_auth_state() -> None:
    username_secret, password_secret = _credentials_from_secrets()
    if username_secret and password_secret:
        st.session_state["scto_username"] = username_secret
        st.session_state["scto_password"] = password_secret
        st.session_state["scto_logged_in"] = True
        st.session_state["scto_test_attachment_url"] = ""
        _set_auth_fingerprint(username_secret, True)
        return

    if not st.session_state.get("_scto_legacy_password_key_cleared"):
        _ss_remove(_SS_PASS_LEGACY)
        st.session_state["_scto_legacy_password_key_cleared"] = True

    if "scto_username" not in st.session_state:
        st.session_state["scto_username"] = _ss_get(_SS_USER)
    if "scto_password" not in st.session_state:
        st.session_state["scto_password"] = ""
    if "scto_logged_in" not in st.session_state:
        st.session_state["scto_logged_in"] = (_ss_get(_SS_OK) == "1")
    if "scto_test_attachment_url" not in st.session_state:
        st.session_state["scto_test_attachment_url"] = _ss_get(_SS_TEST_URL)

    if st.session_state.get("scto_logged_in") and not st.session_state.get("scto_password"):
        st.session_state["scto_logged_in"] = False

    _set_auth_fingerprint(st.session_state.get("scto_username", ""), is_logged_in())


def persist_auth_state(username: str, password: str, logged_in: bool, test_attachment_url: str = "") -> None:
    st.session_state["scto_username"] = username or ""
    st.session_state["scto_password"] = password or ""
    st.session_state["scto_logged_in"] = bool(logged_in)
    st.session_state["scto_test_attachment_url"] = test_attachment_url or ""

    _ss_set(_SS_USER, username or "")
    _ss_set(_SS_OK, "1" if logged_in else "0")
    _ss_set(_SS_TEST_URL, test_attachment_url or "")
    _set_auth_fingerprint(username or "", bool(logged_in and password))
    if logged_in and username and password:
        st.session_state["scto_auth_source"] = "home_or_shared"


def clear_auth_state() -> None:
    st.session_state["scto_username"] = ""
    st.session_state["scto_password"] = ""
    st.session_state["scto_logged_in"] = False
    st.session_state["scto_test_attachment_url"] = ""

    _ss_remove(_SS_USER)
    _ss_remove(_SS_OK)
    _ss_remove(_SS_TEST_URL)
    _ss_remove(_SS_PASS_LEGACY)
    _set_auth_fingerprint("", False)
    st.session_state.pop("scto_auth_source", None)


def is_logged_in() -> bool:
    username, password = _resolve_auth_credentials()
    return bool(username and password)


def scto_url_to_path(full_url: str) -> str:
    p = urlparse(full_url)
    path = (p.path or "").lstrip("/")
    if p.query:
        path = f"{path}?{p.query}"
    return path


def is_scto_server_url(url: str) -> bool:
    try:
        host = (urlparse(url).netloc or "").lower()
        return host == f"{SURVEYCTO_SERVER}.surveycto.com"
    except Exception:
        return False


def _probe_credentials(username: str, password: str) -> Tuple[bool, int, str]:
    endpoints = ["/api/v2/forms/ids", "/api/v2/groups", "/api/v2/teams"]
    last_status = 0
    last_msg = ""
    for ep in endpoints:
        try:
            r = requests.get(f"{BASE_URL}{ep}", auth=(username, password), timeout=20, allow_redirects=True)
        except requests.RequestException as e:
            last_status = 0
            last_msg = str(e)
            continue

        status = int(r.status_code)
        body = (r.text or "").strip()
        if len(body) > 220:
            body = body[:220] + "..."

        if status == 200:
            return True, status, "OK"
        if status == 403:
            return True, status, "Authenticated (limited API permissions)."
        if status == 401:
            return False, status, "Invalid username or password."

        last_status = status
        last_msg = body or f"HTTP {status}"
        if status in (404, 429, 500, 502, 503, 504):
            continue
        return False, status, last_msg

    if last_status:
        return False, last_status, last_msg or f"HTTP {last_status}"
    return False, 0, f"Could not reach SurveyCTO server ({last_msg or 'network error'})."


def surveycto_login_ui(*, in_sidebar: bool = True, attachment_test_url: str = "") -> bool:
    _ = (in_sidebar, attachment_test_url)
    load_auth_state()
    return is_logged_in()


def surveycto_request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    data: Any = None,
    json: Any = None,
    timeout: int = 30,
) -> requests.Response:
    load_auth_state()
    if not is_logged_in():
        raise RuntimeError("SurveyCTO credentials are missing. Set SURVEYCTO_USERNAME and SURVEYCTO_PASSWORD in secrets.")

    username, password = _resolve_auth_credentials()
    url = BASE_URL.rstrip("/") + "/" + path.lstrip("/")

    r = requests.request(
        method.upper(),
        url,
        auth=(username, password),
        params=params,
        data=data,
        json=json,
        timeout=timeout,
        allow_redirects=True,
    )

    if r.status_code == 401:
        msg = ""
        try:
            payload = r.json()
            msg = str(payload.get("error", {}).get("message", "")).strip()
        except Exception:
            msg = (r.text or "").strip()
        if "failed login attempts" in msg.lower():
            raise RuntimeError("SurveyCTO rejected login due to too many failed attempts. Wait about 10 minutes and retry.")
        raise RuntimeError(f"SurveyCTO authentication failed (401). {msg}".strip())
    return r


def _extract_submissions_from_json(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "submissions", "rows"):
            v = payload.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


@st.cache_data(show_spinner=False, ttl=300)
def fetch_form_submissions_wide_json(form_id: str, username: str, auth_fingerprint: str) -> List[Dict[str, Any]]:
    _ = (username, auth_fingerprint)
    fid = str(form_id or "").strip()
    if not fid:
        return []

    candidate_paths = [
        f"/api/v2/forms/data/wide/json/{fid}",
        f"/api/v2/forms/data/json/{fid}",
    ]
    env_since = os.getenv("WASH_SURVEYCTO_DATE_SINCE", "").strip()
    date_candidates = [env_since, "1704067200", "1672531200", "0"]
    review_status = os.getenv("WASH_SURVEYCTO_REVIEW_STATUS", DEFAULT_REVIEW_STATUS).strip() or DEFAULT_REVIEW_STATUS

    seen_dates = set()
    last_status = 0
    last_msg = ""
    auth_error = ""
    for path in candidate_paths:
        for date_value in date_candidates:
            if not date_value or date_value in seen_dates:
                continue
            seen_dates.add(date_value)
            r = None
            for attempt in range(3):
                try:
                    r = surveycto_request("GET", path, params={"date": date_value, "r": review_status}, timeout=45)
                except Exception as exc:
                    auth_error = str(exc)
                    r = None
                    break
                if r.status_code == 417 and attempt < 2:
                    time.sleep(1.1 * (attempt + 1))
                    continue
                break
            if r is None:
                continue
            if r.status_code != 200:
                last_status = int(r.status_code or 0)
                body = (r.text or "").strip()
                if len(body) > 220:
                    body = body[:220] + "..."
                last_msg = body or f"HTTP {last_status}"
                continue
            try:
                data = r.json()
            except Exception:
                continue
            rows = _extract_submissions_from_json(data)
            if rows:
                return rows

    if last_status == 417:
        raise RuntimeError(
            "SurveyCTO API rate limit (HTTP 417): pull is temporarily throttled. "
            "Please retry shortly or set WASH_SURVEYCTO_DATE_SINCE to a recent Unix timestamp."
        )
    if auth_error:
        raise RuntimeError(auth_error)
    if last_status:
        raise RuntimeError(f"SurveyCTO API returned HTTP {last_status}: {last_msg}")
    return []


def fetch_form_dataframe(form_id: str) -> "pd.DataFrame":
    import pandas as pd

    load_auth_state()
    if not is_logged_in():
        raise RuntimeError("SurveyCTO credentials are missing. Add SURVEYCTO_USERNAME and SURVEYCTO_PASSWORD to Streamlit Cloud secrets.")
    username = st.session_state.get("scto_username", "").strip()
    auth_fp = st.session_state.get(AUTH_FINGERPRINT_KEY, "")
    rows = fetch_form_submissions_wide_json(form_id, username, auth_fp)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).fillna("")


def get_submission_by_field(*, form_id: str, field_name: str, field_value: str) -> Optional[Dict[str, Any]]:
    load_auth_state()
    if not is_logged_in():
        return None

    username = st.session_state.get("scto_username", "").strip()
    auth_fp = st.session_state.get(AUTH_FINGERPRINT_KEY, "")
    rows = fetch_form_submissions_wide_json(form_id, username, auth_fp)
    if not rows:
        return None

    k = str(field_name or "").strip()
    v = str(field_value or "").strip()
    if not k or not v:
        return None

    matches = [r for r in rows if str(r.get(k, "")).strip() == v]
    if not matches:
        return None

    for sort_key in ("SubmissionDate", "submissiondate", "starttime"):
        if any(sort_key in m for m in matches):
            matches.sort(key=lambda x: str(x.get(sort_key, "")), reverse=True)
            break

    return matches[0]


def list_field_values_for_form(*, form_id: str, field_name: str) -> List[str]:
    load_auth_state()
    if not is_logged_in():
        return []

    username = st.session_state.get("scto_username", "").strip()
    auth_fp = st.session_state.get(AUTH_FINGERPRINT_KEY, "")
    rows = fetch_form_submissions_wide_json(form_id, username, auth_fp)
    if not rows:
        return []

    key = str(field_name or "").strip()
    if not key:
        return []

    key_candidates = [key]
    if key.lower() == "tpm_id":
        key_candidates.extend(["TPM_ID", "tpm_id", "TPMID", "tpmid"])

    for k in key_candidates:
        values = sorted(
            {
                str(r.get(k, "")).strip()
                for r in rows
                if isinstance(r, dict) and str(r.get(k, "")).strip()
            }
        )
        if values:
            return values
    return []
