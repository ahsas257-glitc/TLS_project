from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd
import requests
import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


class GoogleDriveConnectionError(RuntimeError):
    pass


@st.cache_resource(show_spinner=False)
def get_drive_credentials() -> Credentials:
    credentials_info = None
    for key in ["gdrive_service_account", "gcp_service_account"]:
        try:
            credentials_info = dict(st.secrets[key])
            if credentials_info:
                break
        except Exception:
            continue
    if not credentials_info:
        raise GoogleDriveConnectionError(
            "Google service account credentials are missing from Streamlit secrets. Add `gdrive_service_account` or `gcp_service_account`."
        )

    try:
        credentials = Credentials.from_service_account_info(credentials_info, scopes=[DRIVE_SCOPE])
        credentials.refresh(Request())
        return credentials
    except Exception as exc:
        raise GoogleDriveConnectionError(f"Unable to authorize Google Drive client: {exc}") from exc


def _load_dataset_id_mapping() -> dict[str, str]:
    raw = st.secrets.get("GOOGLE_DRIVE_DATASET_IDS", {})
    if isinstance(raw, dict):
        return {str(key).strip(): str(value).strip() for key, value in raw.items() if str(value).strip()}
    text = str(raw).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return {str(key).strip(): str(value).strip() for key, value in parsed.items() if str(value).strip()}
    except Exception:
        return {}
    return {}


def get_drive_dataset_id(dataset_name: str) -> str:
    return _load_dataset_id_mapping().get(dataset_name, "").strip()


def _extract_folder_id(folder_value: str) -> str:
    value = str(folder_value).strip()
    if not value:
        return ""
    if "/folders/" in value:
        try:
            after = value.split("/folders/", 1)[1]
            return after.split("?", 1)[0].split("/", 1)[0].strip()
        except Exception:
            return ""
    if value.startswith("http"):
        parsed = urlparse(value)
        query = parse_qs(parsed.query)
        if "id" in query and query["id"]:
            return str(query["id"][0]).strip()
    return value


def get_drive_folder_id() -> str:
    folder_value = st.secrets.get("GOOGLE_DRIVE_FOLDER_ID", "")
    if not str(folder_value).strip():
        folder_value = st.secrets.get("GOOGLE_DRIVE_FOLDER_URL", "")
    return _extract_folder_id(str(folder_value))


def extract_drive_file_id(file_value: str) -> str:
    value = str(file_value).strip()
    if not value:
        return ""
    if "/d/" in value:
        try:
            after = value.split("/d/", 1)[1]
            return after.split("/", 1)[0].split("?", 1)[0].strip()
        except Exception:
            return ""
    if "id=" in value:
        try:
            parsed = urlparse(value)
            query = parse_qs(parsed.query)
            if "id" in query and query["id"]:
                return str(query["id"][0]).strip()
        except Exception:
            return ""
    return value


def _authorized_get(url: str, params: dict[str, Any] | None = None) -> requests.Response:
    credentials = get_drive_credentials()
    token = credentials.token
    response = requests.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=45,
    )
    return response


@st.cache_data(ttl=1800, show_spinner=False)
def read_drive_file_bytes(file_id: str) -> bytes:
    if not file_id.strip():
        raise GoogleDriveConnectionError("Google Drive file ID is empty.")
    response = _authorized_get(f"https://www.googleapis.com/drive/v3/files/{file_id}", params={"alt": "media"})
    if response.status_code != 200:
        raise GoogleDriveConnectionError(f"Unable to download Google Drive file: {response.status_code} {response.text}")
    return response.content


@st.cache_data(ttl=1800, show_spinner=False)
def read_drive_file_name(file_id: str) -> str:
    response = _authorized_get(f"https://www.googleapis.com/drive/v3/files/{file_id}", params={"fields": "name"})
    if response.status_code != 200:
        return f"{file_id}.xlsx"
    try:
        payload = response.json()
        return str(payload.get("name", "")).strip() or f"{file_id}.xlsx"
    except Exception:
        return f"{file_id}.xlsx"


@st.cache_data(ttl=1800, show_spinner=False)
def list_drive_folder_files(folder_id: str) -> list[dict[str, str]]:
    if not folder_id.strip():
        return []
    query = f"'{folder_id}' in parents and trashed=false"
    response = _authorized_get(
        "https://www.googleapis.com/drive/v3/files",
        params={
            "q": query,
            "fields": "files(id,name,mimeType)",
            "pageSize": 200,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        },
    )
    if response.status_code != 200:
        raise GoogleDriveConnectionError(f"Unable to list Google Drive folder files: {response.status_code} {response.text}")
    payload = response.json()
    files = payload.get("files", [])
    result: list[dict[str, str]] = []
    for item in files:
        file_id = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        if file_id and name:
            result.append({"id": file_id, "name": name, "mimeType": str(item.get("mimeType", "")).strip()})
    return result


@st.cache_data(ttl=1800, show_spinner=False)
def find_drive_file_id_by_name(file_name: str, folder_id: str) -> str:
    wanted = str(file_name).strip().lower()
    if not wanted or not folder_id.strip():
        return ""
    for item in list_drive_folder_files(folder_id):
        if str(item.get("name", "")).strip().lower() == wanted:
            return str(item.get("id", "")).strip()
    return ""


@st.cache_data(ttl=1800, show_spinner=False)
def find_drive_file_id_by_keywords(folder_id: str, keywords: tuple[str, ...]) -> str:
    if not folder_id.strip() or not keywords:
        return ""
    lowered_keywords = [str(keyword).strip().lower() for keyword in keywords if str(keyword).strip()]
    if not lowered_keywords:
        return ""
    for item in list_drive_folder_files(folder_id):
        name = str(item.get("name", "")).strip().lower()
        if name and all(keyword in name for keyword in lowered_keywords):
            return str(item.get("id", "")).strip()
    return ""


def read_drive_sheets(file_id: str) -> dict[str, pd.DataFrame]:
    content = read_drive_file_bytes(file_id)
    name = read_drive_file_name(file_id).lower()
    buffer = BytesIO(content)
    if name.endswith(".csv"):
        return {"CSV": pd.read_csv(buffer)}
    return {str(sheet_name): frame for sheet_name, frame in pd.read_excel(buffer, sheet_name=None).items()}


def read_drive_sheets_by_name(file_name: str, folder_id: str) -> dict[str, pd.DataFrame]:
    file_id = find_drive_file_id_by_name(file_name, folder_id)
    if not file_id:
        raise GoogleDriveConnectionError(f"File `{file_name}` was not found in the configured Google Drive folder.")
    return read_drive_sheets(file_id)
