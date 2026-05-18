from __future__ import annotations

import html
import math
import re
import warnings
from itertools import combinations
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from services.ui_theme import apply_liquid_glass_theme, render_glass_section
from services.google_drive import (
    extract_drive_file_id,
    find_drive_file_id_by_keywords,
    get_drive_folder_id,
    read_drive_sheets,
    read_drive_sheets_by_name,
)

try:
    import streamlit.components.v1 as components
except ImportError:
    components = None

try:
    import folium
    from folium.plugins import Fullscreen, MeasureControl
except ImportError:
    folium = None
    Fullscreen = None
    MeasureControl = None

try:
    import pydeck as pdk
except ImportError:  # Streamlit can still render a standard map without pydeck imports here.
    pdk = None


XLSFORM_DRIVE_URLS = {
    "Tool 2": "https://docs.google.com/spreadsheets/d/1aVZlk87D3mAzX1xOal_dUck4g6PPMKsT/edit?usp=drive_link&ouid=118130531358947255257&rtpof=true&sd=true",
    "Tool 3": "https://docs.google.com/spreadsheets/d/1rRfvtePPii57vHUDuqVKquFPAZUb8vmT/edit?usp=drive_link&ouid=118130531358947255257&rtpof=true&sd=true",
    "Tool 5": "https://docs.google.com/spreadsheets/d/19k3U_Q7k37WTumJ2As6bFRTatzPzyyd9/edit?usp=drive_link&ouid=118130531358947255257&rtpof=true&sd=true",
}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
XLSFORM_LOCAL_PATHS = {
    "Tool 2": PROJECT_ROOT / "xls_forms" / "ECE Tool2 Classroom Observation.xlsx",
    "Tool 3": PROJECT_ROOT / "xls_forms" / "ECE_Tool3_Parent_Interview.xlsx",
    "Tool 5": PROJECT_ROOT / "xls_forms" / "TLS_Tool5_Classroom_Observation.xlsx",
}
XLSFORM_FOLDER_DEFAULT_ID = "1yYmD9rTmjudFCJri9SMNnfW3-qEHWcVI"
XLSFORM_FOLDER_KEYWORDS = {
    "Tool 2": ("tool2", "classroom", "observation", "form"),
    "Tool 3": ("tool3", "parent", "interview", "form"),
    "Tool 5": ("tool5", "classroom", "observation", "form"),
}
GOOGLE_DRIVE_DATASET_KEYS = [
    "Tool 2 ECE Classroom Observation.xlsx",
    "Tool 3 ECE Parent Interview.xlsx",
    "Tool 5 TLS Classroom Observation.xlsx",
]
DATASET_FOLDER_DEFAULT_ID = "1VFgsazs0OkRI5kmmrF1pXTr6RrPnu3hx"
STRUCTURAL_TYPES = {
    "begin",
    "end",
    "begin_group",
    "end_group",
    "begin_repeat",
    "end_repeat",
    "note",
    "calculate",
    "calculate_here",
    "audio",
    "image",
}
META_TYPES = {"start", "end", "deviceid", "subscriberid", "simserial", "phonenumber", "username"}
STATUS_COLUMN_HINTS = {"status", "qastatus", "qcstatus", "reviewstatus", "validationstatus"}
GPS_LATITUDE_CANDIDATES = ["GPS-Latitude", "GPS Latitude", "GPS_Latitude", "latitude", "lat", "Latitude"]
GPS_LONGITUDE_CANDIDATES = ["GPS-Longitude", "GPS Longitude", "GPS_Longitude", "longitude", "lon", "lng", "Longitude"]
GPS_ALTITUDE_CANDIDATES = ["GPS-Altitude", "GPS Altitude", "GPS_Altitude", "altitude", "Altitude"]
GPS_ACCURACY_CANDIDATES = ["GPS-Accuracy", "GPS Accuracy", "GPS_Accuracy", "accuracy", "Accuracy"]
GPS_POINT_CANDIDATES = ["GPS", "gps", "geopoint", "GeoPoint", "GPS Point", "GPS_Point"]
GPS_CONTEXT_CANDIDATES = {
    "GPS Time": ["Date_And_Time", "starttime", "SubmissionDate", "endtime"],
    "Visit Date": ["date_of_visit", "Survey_Date", "Date_And_Time", "SubmissionDate"],
    "Reviewer": ["QA_by", "QA by", "reviewer", "Reviewed_By", "checked_by", "Checker", "QC_by"],
    "Review Status": ["review_status", "QA_status", "QC_status", "Status"],
    "Region": ["Region", "region", "Zone", "zone"],
    "Province": ["Province", "province"],
    "District": ["District", "district"],
    "Village": ["Village", "Village_Community", "Village Community", "Qarya", "Community"],
    "Surveyor": ["Surveyor_Name", "Surveyor Name", "surveyor", "username", "Enumerator", "Enumerator_Name"],
    "Surveyor ID": ["Surveyor_Id", "Surveyor ID", "surveyor_id", "Enumerator_Id", "Enumerator ID"],
    "School": ["School_Name", "School Name", "school", "school_name", "ECD_Center_Name", "Center_Name"],
    "TPM_TLS_ID": ["TPM_TLS_ID", "TPM_ECE_ID"],
    "Class ID": ["Class_Code", "Class_ID", "class_id", "sample_ECE_ID", "TLS_SN", "Class_Name", "Class Name"],
    "Class Type": ["TLS_Classes", "TLS_Type", "Classroom_Infra", "Class_Shift"],
}
GPS_ACCURACY_COLORS = {
    "Excellent (<=10m)": [34, 197, 94, 205],
    "Good (<=25m)": [56, 189, 248, 205],
    "Review (<=50m)": [245, 158, 11, 210],
    "Weak (>50m)": [239, 68, 68, 215],
    "Unknown": [148, 163, 184, 175],
}
GPS_MAP_STYLES = {
    "Dark": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    "Satellite": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
}
LOW_VALUE_TEXT_MAX_UNIQUE = 30
MAX_AUTO_VISUALS = 18
CHART_FONT = "Manrope"
CHART_TEXT = "#dbe7ff"
CHART_MUTED = "#93a4c4"
CHART_GRID = "rgba(219, 231, 255, 0.12)"
CHART_HEIGHT = 360
PALETTE = ["#2563eb", "#22c55e", "#f97316", "#8b5cf6", "#0f766e", "#ef4444", "#38bdf8", "#f59e0b"]


def normalize_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def canonical_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if re.fullmatch(r"-?\d+\.0", text):
        return text[:-2]
    return text


def base_question_type(type_value: object) -> str:
    text = clean_text(type_value)
    if not text:
        return ""
    return text.split()[0].strip().lower()


def choice_list_name(type_value: object) -> str:
    text = clean_text(type_value)
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


@st.cache_data(ttl=900, show_spinner=False)
def load_all_schemas() -> dict[str, dict[str, Any]]:
    schemas = {}

    # Primary source: project-local xls_forms folder (Cloud-stable and matches local behavior).
    for tool_key, local_path in XLSFORM_LOCAL_PATHS.items():
        try:
            if not local_path.exists():
                continue
            sheets = pd.read_excel(local_path, sheet_name=None)
            survey = sheets.get("survey", pd.DataFrame()).fillna("")
            choices = sheets.get("choices", pd.DataFrame()).fillna("")
            settings = sheets.get("settings", pd.DataFrame()).fillna("")
            if survey.empty:
                continue

            fields: list[dict[str, Any]] = []
            for _, row in survey.iterrows():
                name = clean_text(row.get("name", ""))
                type_raw = clean_text(row.get("type", ""))
                base_type = base_question_type(type_raw)
                if not name or base_type in STRUCTURAL_TYPES:
                    continue
                label = clean_text(row.get("label:English", "")) or clean_text(row.get("label:Dari", "")) or name
                fields.append(
                    {
                        "name": name,
                        "name_key": normalize_key(name),
                        "type": base_type,
                        "type_raw": type_raw,
                        "choice_list": choice_list_name(type_raw),
                        "label": label,
                        "required": str(row.get("required", "")).strip().lower() in {"true", "yes", "1"},
                        "relevance": clean_text(row.get("relevance", "")),
                    }
                )

            choice_labels: dict[str, dict[str, str]] = {}
            if {"list_name", "value"}.issubset(choices.columns):
                for _, row in choices.iterrows():
                    list_name = clean_text(row.get("list_name", ""))
                    value = canonical_value(row.get("value", ""))
                    if not list_name or not value:
                        continue
                    label = clean_text(row.get("label:English", "")) or clean_text(row.get("label:Dari", "")) or value
                    choice_labels.setdefault(list_name, {})[value] = label

            form_title = ""
            form_id = ""
            if not settings.empty:
                form_title = clean_text(settings.iloc[0].get("form_title", ""))
                form_id = clean_text(settings.iloc[0].get("form_id", ""))

            schemas[tool_key] = {
                "tool_key": tool_key,
                "form_title": form_title or tool_key,
                "form_id": form_id,
                "fields": fields,
                "field_by_key": {field["name_key"]: field for field in fields},
                "choice_labels": choice_labels,
                "path": str(local_path),
            }
        except Exception:
            continue

    for tool_key, url in XLSFORM_DRIVE_URLS.items():
        if tool_key in schemas:
            continue
        try:
            file_id = extract_drive_file_id(url)
            if not file_id:
                continue
            sheets = read_drive_sheets(file_id)
            survey = sheets.get("survey", pd.DataFrame()).fillna("")
            choices = sheets.get("choices", pd.DataFrame()).fillna("")
            settings = sheets.get("settings", pd.DataFrame()).fillna("")
            if survey.empty:
                continue

            fields: list[dict[str, Any]] = []
            for _, row in survey.iterrows():
                name = clean_text(row.get("name", ""))
                type_raw = clean_text(row.get("type", ""))
                base_type = base_question_type(type_raw)
                if not name or base_type in STRUCTURAL_TYPES:
                    continue
                label = clean_text(row.get("label:English", "")) or clean_text(row.get("label:Dari", "")) or name
                fields.append(
                    {
                        "name": name,
                        "name_key": normalize_key(name),
                        "type": base_type,
                        "type_raw": type_raw,
                        "choice_list": choice_list_name(type_raw),
                        "label": label,
                        "required": str(row.get("required", "")).strip().lower() in {"true", "yes", "1"},
                        "relevance": clean_text(row.get("relevance", "")),
                    }
                )

            choice_labels: dict[str, dict[str, str]] = {}
            if {"list_name", "value"}.issubset(choices.columns):
                for _, row in choices.iterrows():
                    list_name = clean_text(row.get("list_name", ""))
                    value = canonical_value(row.get("value", ""))
                    if not list_name or not value:
                        continue
                    label = clean_text(row.get("label:English", "")) or clean_text(row.get("label:Dari", "")) or value
                    choice_labels.setdefault(list_name, {})[value] = label

            form_title = ""
            form_id = ""
            if not settings.empty:
                form_title = clean_text(settings.iloc[0].get("form_title", ""))
                form_id = clean_text(settings.iloc[0].get("form_id", ""))

            schemas[tool_key] = {
                "tool_key": tool_key,
                "form_title": form_title or tool_key,
                "form_id": form_id,
                "fields": fields,
                "field_by_key": {field["name_key"]: field for field in fields},
                "choice_labels": choice_labels,
                "path": f"gdrive://{file_id}",
            }
        except Exception:
            continue

    folder_id = str(st.secrets.get("GOOGLE_DRIVE_XLSFORM_FOLDER_ID", "")).strip() or get_drive_folder_id() or XLSFORM_FOLDER_DEFAULT_ID
    for tool_key, keywords in XLSFORM_FOLDER_KEYWORDS.items():
        if tool_key in schemas:
            continue
        try:
            file_id = find_drive_file_id_by_keywords(folder_id, keywords)
            if not file_id:
                continue
            sheets = read_drive_sheets(file_id)
            survey = sheets.get("survey", pd.DataFrame()).fillna("")
            choices = sheets.get("choices", pd.DataFrame()).fillna("")
            settings = sheets.get("settings", pd.DataFrame()).fillna("")
            if survey.empty:
                continue

            fields: list[dict[str, Any]] = []
            for _, row in survey.iterrows():
                name = clean_text(row.get("name", ""))
                type_raw = clean_text(row.get("type", ""))
                base_type = base_question_type(type_raw)
                if not name or base_type in STRUCTURAL_TYPES:
                    continue
                label = clean_text(row.get("label:English", "")) or clean_text(row.get("label:Dari", "")) or name
                fields.append(
                    {
                        "name": name,
                        "name_key": normalize_key(name),
                        "type": base_type,
                        "type_raw": type_raw,
                        "choice_list": choice_list_name(type_raw),
                        "label": label,
                        "required": str(row.get("required", "")).strip().lower() in {"true", "yes", "1"},
                        "relevance": clean_text(row.get("relevance", "")),
                    }
                )

            choice_labels: dict[str, dict[str, str]] = {}
            if {"list_name", "value"}.issubset(choices.columns):
                for _, row in choices.iterrows():
                    list_name = clean_text(row.get("list_name", ""))
                    value = canonical_value(row.get("value", ""))
                    if not list_name or not value:
                        continue
                    label = clean_text(row.get("label:English", "")) or clean_text(row.get("label:Dari", "")) or value
                    choice_labels.setdefault(list_name, {})[value] = label

            form_title = ""
            form_id = ""
            if not settings.empty:
                form_title = clean_text(settings.iloc[0].get("form_title", ""))
                form_id = clean_text(settings.iloc[0].get("form_id", ""))

            schemas[tool_key] = {
                "tool_key": tool_key,
                "form_title": form_title or tool_key,
                "form_id": form_id,
                "fields": fields,
                "field_by_key": {field["name_key"]: field for field in fields},
                "choice_labels": choice_labels,
                "path": f"gdrive://{file_id}",
            }
        except Exception:
            continue

    return schemas


def build_generic_schema(dataframe: pd.DataFrame, title: str = "Generic") -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for column in dataframe.columns:
        fields.append(
            {
                "name": str(column),
                "name_key": normalize_key(column),
                "type": infer_type(dataframe[column]),
                "type_raw": infer_type(dataframe[column]),
                "choice_list": "",
                "label": str(column),
                "required": False,
                "relevance": "",
            }
        )
    return {
        "tool_key": "Generic",
        "form_title": title,
        "form_id": "generic",
        "fields": fields,
        "field_by_key": {field["name_key"]: field for field in fields},
        "choice_labels": {},
        "path": "auto-generated",
    }


def default_sheet_name(sheets: dict[str, pd.DataFrame]) -> str:
    if "data" in sheets:
        return "data"
    if not sheets:
        return ""
    return max(sheets.keys(), key=lambda sheet_name: len(sheets[sheet_name].dropna(how="all")))


def prepare_dataset(dataframe: pd.DataFrame) -> pd.DataFrame:
    prepared = dataframe.copy().dropna(how="all")
    prepared.columns = [str(column).strip() for column in prepared.columns]
    prepared = prepared.loc[:, [column for column in prepared.columns if column and not column.lower().startswith("unnamed:")]]
    return remove_rejected_rows(prepared)


def remove_rejected_rows(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()
    rejected_mask = pd.Series(False, index=dataframe.index)
    for column in dataframe.columns:
        if not is_rejection_status_column(column):
            continue
        values = dataframe[column].fillna("").astype(str).str.strip().str.lower()
        rejected_mask = rejected_mask | values.str.contains("reject", na=False)
    return dataframe.loc[~rejected_mask].copy()


def is_rejection_status_column(column: str) -> bool:
    column_key = normalize_key(column)
    return column_key in STATUS_COLUMN_HINTS or column_key.endswith("status")


def detect_tool(dataframe: pd.DataFrame, file_name: str, schemas: dict[str, dict[str, Any]]) -> tuple[str | None, pd.DataFrame]:
    if not schemas:
        return "Generic", pd.DataFrame(
            [
                {
                    "Tool": "Generic",
                    "Form Title": "Auto schema (no XLSForm)",
                    "Matched Fields": len(dataframe.columns),
                    "Required Matched": 0,
                    "Schema Fields": len(dataframe.columns),
                    "Coverage %": 100.0 if len(dataframe.columns) else 0.0,
                    "Score": float(len(dataframe.columns)),
                }
            ]
        )
    column_keys = {normalize_key(column) for column in dataframe.columns}
    rows = []
    file_key = normalize_key(file_name)
    for tool_key, schema in schemas.items():
        field_keys = set(schema["field_by_key"].keys())
        matched = len(column_keys & field_keys)
        required_keys = {field["name_key"] for field in schema["fields"] if field["required"]}
        required_matched = len(column_keys & required_keys)
        hint_bonus = 8 if normalize_key(tool_key) in file_key or normalize_key(schema["form_id"]) in file_key else 0
        score = matched + (required_matched * 1.8) + hint_bonus
        coverage = round((matched / len(field_keys)) * 100, 1) if field_keys else 0
        rows.append(
            {
                "Tool": tool_key,
                "Form Title": schema["form_title"],
                "Matched Fields": matched,
                "Required Matched": required_matched,
                "Schema Fields": len(field_keys),
                "Coverage %": coverage,
                "Score": round(score, 1),
            }
        )
    scorecard = pd.DataFrame(rows).sort_values(["Score", "Matched Fields"], ascending=False)
    if scorecard.empty or float(scorecard.iloc[0]["Score"]) <= 0:
        return None, scorecard
    return str(scorecard.iloc[0]["Tool"]), scorecard


def schema_field_for_column(column: str, schema: dict[str, Any]) -> dict[str, Any] | None:
    return schema["field_by_key"].get(normalize_key(column))


def column_for_field(dataframe: pd.DataFrame, field: dict[str, Any]) -> str | None:
    lookup = {normalize_key(column): column for column in dataframe.columns}
    return lookup.get(field["name_key"])


def first_existing_column(dataframe: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {normalize_key(column): column for column in dataframe.columns}
    for candidate in candidates:
        column = lookup.get(normalize_key(candidate))
        if column:
            return column
    return None


def profile_columns(dataframe: pd.DataFrame, schema: dict[str, Any]) -> pd.DataFrame:
    rows = []
    total = len(dataframe)
    for column in dataframe.columns:
        field = schema_field_for_column(column, schema)
        series = dataframe[column]
        filled = int(series.fillna("").astype(str).str.strip().ne("").sum())
        unique = int(series.dropna().astype(str).str.strip().replace("", pd.NA).dropna().nunique())
        inferred = field["type"] if field else infer_type(series)
        rows.append(
            {
                "Column": column,
                "Question Label": field["label"] if field else column,
                "Type": inferred,
                "Required": bool(field["required"]) if field else False,
                "Covered by XLSForm": field is not None,
                "Filled": filled,
                "Missing": max(total - filled, 0),
                "Completeness %": round((filled / total) * 100, 1) if total else 0,
                "Unique Values": unique,
            }
        )
    return pd.DataFrame(rows)


def infer_type(series: pd.Series) -> str:
    if len(series) == 0:
        return "text"
    min_signal = min(3, max(1, len(series)))
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() >= max(min_signal, len(series) * 0.65):
        return "decimal"
    if not looks_datetime_like(series, min_signal):
        return "text"
    dates = parse_datetime_series(series)
    if dates.notna().sum() >= max(min_signal, len(series) * 0.65):
        return "date"
    return "text"


def looks_datetime_like(series: pd.Series, min_signal: int) -> bool:
    values = series.dropna().astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return False
    pattern = r"(?:\d{4}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|T\d{2}:\d{2}|^\d{4}-\d{2}-\d{2})"
    signal_count = int(values.str.contains(pattern, regex=True, na=False).sum())
    return signal_count >= max(min_signal, len(values) * 0.5)


def parse_datetime_series(series: pd.Series) -> pd.Series:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        try:
            return pd.to_datetime(series, errors="coerce", utc=True)
        except Exception:
            return pd.to_datetime(series.astype(str), errors="coerce", utc=True)


def map_choice_value(value: object, field: dict[str, Any] | None, schema: dict[str, Any]) -> str:
    text = canonical_value(value)
    if not text or not field:
        return text
    labels = schema["choice_labels"].get(field.get("choice_list", ""), {})
    return labels.get(text, text)


def count_single_choice(dataframe: pd.DataFrame, column: str, field: dict[str, Any] | None, schema: dict[str, Any], limit: int = 20) -> pd.DataFrame:
    values = dataframe[column].map(lambda value: map_choice_value(value, field, schema))
    values = values.astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return pd.DataFrame(columns=["Response", "Count"])
    counts = values.value_counts().head(limit).reset_index()
    counts.columns = ["Response", "Count"]
    return counts


def count_multiple_choice(dataframe: pd.DataFrame, column: str, field: dict[str, Any] | None, schema: dict[str, Any], limit: int = 30) -> pd.DataFrame:
    labels = schema["choice_labels"].get(field.get("choice_list", ""), {}) if field else {}
    parts: list[str] = []
    for value in dataframe[column].dropna().astype(str):
        for item in re.split(r"[\s,;]+", value.strip()):
            item = canonical_value(item)
            if item:
                parts.append(labels.get(item, item))
    if not parts:
        return pd.DataFrame(columns=["Response", "Count"])
    counts = pd.Series(parts).value_counts().head(limit).reset_index()
    counts.columns = ["Response", "Count"]
    return counts


def top_counts(dataframe: pd.DataFrame, column: str, limit: int = 15) -> pd.DataFrame:
    values = dataframe[column].fillna("").astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return pd.DataFrame(columns=[column, "Count"])
    counts = values.value_counts().head(limit).reset_index()
    counts.columns = [column, "Count"]
    return counts


def short_label(text: object, limit: int = 58) -> str:
    value = clean_text(text)
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def is_identifier_column(column: str) -> bool:
    key = normalize_key(column)
    identifier_tokens = ["id", "uuid", "key", "phone", "device", "sim", "subscriber", "pcode", "emis"]
    return any(token in key for token in identifier_tokens)


def is_media_or_audit_column(column: str) -> bool:
    key = normalize_key(column)
    return any(token in key for token in ["audio", "image", "photo", "file", "audit", "ta", "aa"])


def is_visualizable_profile_row(row: pd.Series) -> bool:
    column = str(row["Column"])
    column_type = str(row["Type"])
    filled = int(row["Filled"])
    unique_values = int(row["Unique Values"])
    if filled == 0 or unique_values <= 1:
        return False
    if is_media_or_audit_column(column):
        return False
    if is_identifier_column(column) and column_type not in {"select_one", "select_multiple"}:
        return False
    if column_type in {"text", "barcode"} and unique_values > LOW_VALUE_TEXT_MAX_UNIQUE:
        return False
    return True


def visualizable_columns(profile: pd.DataFrame) -> list[str]:
    if profile.empty:
        return []
    useful = profile[profile.apply(is_visualizable_profile_row, axis=1)].copy()
    useful["Priority"] = useful["Required"].astype(int) * 10 + useful["Covered by XLSForm"].astype(int) * 5 + (100 - useful["Completeness %"])
    useful = useful.sort_values(["Priority", "Completeness %"], ascending=[False, True])
    return useful["Column"].tolist()


def render_metric_card(title: str, value: str, subtitle: str, tone: str) -> None:
    st.markdown(
        f"""
        <div style="
            position:relative; overflow:hidden; height:166px; padding:17px 18px;
            border-radius:16px; border:1px solid rgba(226,232,240,0.18);
            background:linear-gradient(145deg,rgba(255,255,255,0.15),rgba(255,255,255,0.04)),linear-gradient(135deg,rgba(10,18,37,0.96),rgba(3,8,20,0.92));
            box-shadow:0 22px 58px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.18);
            backdrop-filter:blur(24px) saturate(150%); -webkit-backdrop-filter:blur(24px) saturate(150%);
            display:flex; flex-direction:column; justify-content:space-between;
        ">
            <div style="position:absolute; left:0; right:0; top:0; height:3px; background:linear-gradient(90deg,{tone},rgba(255,255,255,0.82),transparent);"></div>
            <div style="position:absolute; right:14px; top:14px; width:34px; height:34px; border-radius:11px; background:linear-gradient(145deg,{tone},rgba(255,255,255,0.10)); box-shadow:0 0 28px color-mix(in srgb,{tone} 42%,transparent);"></div>
            <div style="position:relative; z-index:1; max-width:calc(100% - 48px); color:#b9c8e7; font-size:0.72rem; letter-spacing:0.13em; text-transform:uppercase; font-weight:900;">{title}</div>
            <div style="position:relative; z-index:1; color:#f8fbff; font-size:clamp(1.75rem,2vw,2.3rem); line-height:1; font-weight:900; overflow-wrap:anywhere;">{value}</div>
            <div style="position:relative; z-index:1; padding-top:10px; border-top:1px solid rgba(226,232,240,0.12); color:#a9b8d6; font-size:0.78rem; line-height:1.35; font-weight:600;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def modernize_chart(chart: alt.TopLevelMixin) -> alt.TopLevelMixin:
    return (
        chart.properties(padding={"top": 18, "right": 16, "bottom": 12, "left": 16})
        .configure(background="transparent")
        .configure_view(strokeOpacity=0)
        .configure_title(font=CHART_FONT, fontSize=16, fontWeight=800, color=CHART_TEXT, anchor="start", offset=22, limit=560)
        .configure_axis(
            labelFont=CHART_FONT,
            titleFont=CHART_FONT,
            labelColor=CHART_MUTED,
            titleColor=CHART_MUTED,
            gridColor=CHART_GRID,
            domainColor="rgba(219,231,255,0.18)",
            tickColor="rgba(219,231,255,0.16)",
            labelFontSize=11,
            titleFontSize=12,
        )
        .configure_legend(
            labelFont=CHART_FONT,
            titleFont=CHART_FONT,
            labelColor=CHART_TEXT,
            titleColor=CHART_MUTED,
            orient="bottom",
            direction="horizontal",
            columns=3,
            symbolType="circle",
            symbolSize=90,
        )
    )


def render_bar_chart(dataframe: pd.DataFrame, category: str, title: str, color: str = "#38bdf8", value_column: str = "Count", height: int = CHART_HEIGHT) -> None:
    if dataframe.empty or category not in dataframe.columns or value_column not in dataframe.columns:
        st.info("No data is available for this chart.")
        return
    chart_data = dataframe[[category, value_column]].copy()
    chart_data.columns = ["Category", "Value"]
    chart_data["Value"] = pd.to_numeric(chart_data["Value"], errors="coerce").fillna(0)
    chart_data = chart_data[chart_data["Value"] > 0].head(20)
    if chart_data.empty:
        st.info("No data is available for this chart.")
        return
    max_value = float(chart_data["Value"].max())
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=8, cornerRadiusBottomRight=8, color=color, opacity=0.86)
        .encode(
            x=alt.X("Value:Q", title=value_column, scale=alt.Scale(domain=[0, max(max_value * 1.22, 1)])),
            y=alt.Y("Category:N", sort="-x", title=None),
            tooltip=[alt.Tooltip("Category:N", title=category), alt.Tooltip("Value:Q", title=value_column, format=",")],
        )
        .properties(height=height, title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def build_tool5_approved_tpm_duplicates(dataframe: pd.DataFrame) -> pd.DataFrame:
    tpm_column = first_existing_column(dataframe, ["TPM_TLS_ID", "TPM TLS ID", "TPM-ID (ECE, TLS)", "TPM_ID"])
    review_column = first_existing_column(dataframe, ["review_status", "Review Status", "QA_status", "QC_status", "Status"])
    if not tpm_column or not review_column or dataframe.empty:
        return pd.DataFrame(columns=["TPM_TLS_ID", "Count"])

    work = dataframe.copy()
    work[tpm_column] = work[tpm_column].fillna("").astype(str).str.strip()
    work[review_column] = work[review_column].fillna("").astype(str).str.strip().str.upper()
    work = work[(work[tpm_column] != "") & (work[review_column] == "APPROVED")]
    if work.empty:
        return pd.DataFrame(columns=["TPM_TLS_ID", "Count"])

    grouped = (
        work.groupby(tpm_column, as_index=False)
        .size()
        .rename(columns={tpm_column: "TPM_TLS_ID", "size": "Count"})
    )
    grouped = grouped[grouped["Count"] > 1].sort_values("Count", ascending=False).head(30)
    return grouped


def render_tool5_tpm_duplicate_chart(dataframe: pd.DataFrame) -> None:
    chart_data = build_tool5_approved_tpm_duplicates(dataframe)
    if chart_data.empty:
        st.info("No duplicated TPM TLS IDs were found where review_status is APPROVED.")
        return

    max_value = float(chart_data["Count"].max())
    base = (
        alt.Chart(chart_data)
        .encode(
            x=alt.X("Count:Q", title="Approved Duplicate Count", scale=alt.Scale(domain=[0, max(max_value * 1.15, 2)])),
            y=alt.Y("TPM_TLS_ID:N", title=None, sort="-x"),
            tooltip=["TPM_TLS_ID:N", alt.Tooltip("Count:Q", format=",")],
        )
    )
    bars = base.mark_bar(cornerRadiusTopRight=10, cornerRadiusBottomRight=10, color="#22c55e", opacity=0.9)
    glow = base.mark_bar(cornerRadiusTopRight=10, cornerRadiusBottomRight=10, color="#86efac", opacity=0.2, size=26)
    labels = base.mark_text(align="left", baseline="middle", dx=8, color=CHART_TEXT, font=CHART_FONT, fontSize=11, fontWeight=900).encode(
        text=alt.Text("Count:Q", format=",")
    )
    chart = alt.layer(glow, bars, labels).properties(
        height=min(max(len(chart_data) * 28, 320), 720),
        title="Tool 5 · Approved Duplicate TPM TLS IDs",
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def build_tool5_returnee_zone_province(dataframe: pd.DataFrame) -> pd.DataFrame:
    returnee_column = first_existing_column(
        dataframe,
        ["# of returnee students", "No of returnee students", "number of returnee students", "returnee_students"],
    )
    zone_column = first_existing_column(dataframe, ["Zone", "zone", "Region", "region"])
    province_column = first_existing_column(dataframe, ["Province", "province"])
    if not returnee_column or not zone_column or not province_column or dataframe.empty:
        return pd.DataFrame(columns=["Zone", "Province", "Returnee Students"])

    work = dataframe[[returnee_column, zone_column, province_column]].copy()
    work["Returnee Students"] = pd.to_numeric(work[returnee_column], errors="coerce").fillna(0)
    work["Zone"] = work[zone_column].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
    work["Province"] = work[province_column].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
    grouped = (
        work.groupby(["Zone", "Province"], as_index=False)["Returnee Students"]
        .sum()
        .sort_values("Returnee Students", ascending=False)
    )
    return grouped[grouped["Returnee Students"] > 0].head(40)


def build_tool5_returnee_climate(dataframe: pd.DataFrame) -> pd.DataFrame:
    returnee_column = first_existing_column(
        dataframe,
        ["# of returnee students", "No of returnee students", "number of returnee students", "returnee_students"],
    )
    climate_column = first_existing_column(dataframe, ["Climate", "climate"])
    if not returnee_column or not climate_column or dataframe.empty:
        return pd.DataFrame(columns=["Climate", "Returnee Students"])

    work = dataframe[[returnee_column, climate_column]].copy()
    work["Returnee Students"] = pd.to_numeric(work[returnee_column], errors="coerce").fillna(0)
    work["Climate"] = work[climate_column].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
    grouped = (
        work.groupby("Climate", as_index=False)["Returnee Students"]
        .sum()
        .sort_values("Returnee Students", ascending=False)
    )
    return grouped[grouped["Returnee Students"] > 0]


def render_tool5_returnee_zone_province_chart(dataframe: pd.DataFrame) -> None:
    chart_data = build_tool5_returnee_zone_province(dataframe)
    if chart_data.empty:
        st.info("No valid returnee-student values were found for Zone and Province.")
        return
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=9, cornerRadiusBottomRight=9, opacity=0.9)
        .encode(
            x=alt.X("Returnee Students:Q", title="Returnee Students"),
            y=alt.Y("Province:N", sort="-x", title=None),
            color=alt.Color("Zone:N", scale=alt.Scale(range=PALETTE), legend=alt.Legend(title="Zone")),
            tooltip=["Zone:N", "Province:N", alt.Tooltip("Returnee Students:Q", format=",")],
        )
        .properties(height=460, title="Tool 5 · Returnee Students by Zone and Province")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_tool5_returnee_climate_chart(dataframe: pd.DataFrame) -> None:
    chart_data = build_tool5_returnee_climate(dataframe)
    if chart_data.empty:
        st.info("No valid returnee-student values were found for Climate.")
        return
    chart = (
        alt.Chart(chart_data)
        .mark_arc(innerRadius=76, outerRadius=128, cornerRadius=6, padAngle=0.02)
        .encode(
            theta=alt.Theta("Returnee Students:Q"),
            color=alt.Color("Climate:N", scale=alt.Scale(range=PALETTE), legend=alt.Legend(title="Climate")),
            tooltip=["Climate:N", alt.Tooltip("Returnee Students:Q", format=",")],
        )
        .properties(height=460, title="Tool 5 · Returnee Students by Climate")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_donut_chart(dataframe: pd.DataFrame, category: str, title: str, colors: list[str] | None = None) -> None:
    if dataframe.empty or category not in dataframe.columns or "Count" not in dataframe.columns:
        st.info("No data is available for this chart.")
        return
    chart_data = dataframe[[category, "Count"]].copy()
    chart_data.columns = ["Category", "Count"]
    chart_data["Count"] = pd.to_numeric(chart_data["Count"], errors="coerce").fillna(0)
    chart_data = chart_data[chart_data["Count"] > 0]
    if chart_data.empty:
        st.info("No data is available for this chart.")
        return
    total = int(chart_data["Count"].sum())
    chart_data["Share"] = chart_data["Count"] / total if total else 0
    arc = (
        alt.Chart(chart_data)
        .mark_arc(innerRadius=68, outerRadius=112, cornerRadius=6, padAngle=0.025)
        .encode(
            theta=alt.Theta("Count:Q"),
            color=alt.Color("Category:N", scale=alt.Scale(range=colors or PALETTE), legend=alt.Legend(title=category)),
            tooltip=[alt.Tooltip("Category:N", title=category), alt.Tooltip("Count:Q", format=","), alt.Tooltip("Share:Q", format=".1%")],
        )
    )
    center = alt.Chart(pd.DataFrame({"Total": [f"{total:,}"]})).mark_text(font=CHART_FONT, fontSize=25, fontWeight=900, color=CHART_TEXT, dy=-4).encode(text="Total:N")
    chart = alt.layer(arc, center).properties(height=CHART_HEIGHT + 18, title=alt.TitleParams(text=title, anchor="start", offset=24), padding={"top": 22, "right": 18, "bottom": 16, "left": 18})
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_numeric_chart(dataframe: pd.DataFrame, column: str, title: str) -> None:
    values = pd.to_numeric(dataframe[column], errors="coerce").dropna()
    if values.empty:
        st.info("No numeric values are available for this chart.")
        return
    chart_data = pd.DataFrame({"Value": values})
    chart = (
        alt.Chart(chart_data)
        .mark_bar(color="#38bdf8", opacity=0.86)
        .encode(
            x=alt.X("Value:Q", bin=alt.Bin(maxbins=24), title=column),
            y=alt.Y("count():Q", title="Rows"),
            tooltip=[alt.Tooltip("count():Q", title="Rows")],
        )
        .properties(height=CHART_HEIGHT, title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_date_chart(dataframe: pd.DataFrame, column: str, title: str) -> None:
    dates = parse_datetime_series(dataframe[column]).dropna()
    if dates.empty:
        st.info("No date values are available for this chart.")
        return
    chart_data = pd.DataFrame({"Date": dates.dt.date.astype(str)})
    chart_data = chart_data.groupby("Date").size().reset_index(name="Count")
    chart = (
        alt.Chart(chart_data)
        .mark_line(point=True, color="#22c55e")
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Count:Q", title="Rows"),
            tooltip=["Date:T", alt.Tooltip("Count:Q", format=",")],
        )
        .properties(height=CHART_HEIGHT, title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_standards_matrix(dataframe: pd.DataFrame, schema: dict[str, Any], title: str = "Standards Compliance Matrix") -> None:
    rows: list[dict[str, Any]] = []
    for field in schema["fields"]:
        if field["type"] != "select_one":
            continue
        column = column_for_field(dataframe, field)
        if not column:
            continue
        labels = count_single_choice(dataframe, column, field, schema, limit=12)
        if labels.empty or int(labels["Count"].sum()) == 0:
            continue
        lowered = labels["Response"].astype(str).str.lower()
        if not lowered.str.contains("yes|no|don't|dont|dk|refuse|not", regex=True).any():
            continue
        total = int(labels["Count"].sum())
        for _, row in labels.iterrows():
            response = clean_text(row["Response"])
            count = int(row["Count"])
            rows.append(
                {
                    "Question": short_label(field["label"], 52),
                    "Response": response,
                    "Percent": round((count / total) * 100, 1) if total else 0,
                    "Count": count,
                }
            )
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("No standards matrix is available for this dataset.")
        return
    chart = (
        alt.Chart(chart_data)
        .mark_rect(cornerRadius=4)
        .encode(
            x=alt.X("Response:N", title=None),
            y=alt.Y("Question:N", sort="-x", title=None),
            color=alt.Color("Percent:Q", scale=alt.Scale(scheme="tealblues"), legend=alt.Legend(title="Share")),
            tooltip=["Question:N", "Response:N", alt.Tooltip("Count:Q", format=","), alt.Tooltip("Percent:Q", format=".1f")],
        )
        .properties(height=min(max(len(chart_data["Question"].unique()) * 24, 360), 760), title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_numeric_combo_chart(dataframe: pd.DataFrame, schema: dict[str, Any], title: str = "Numeric Indicators Overview") -> None:
    rows: list[dict[str, Any]] = []
    for field in schema["fields"]:
        if field["type"] not in {"integer", "decimal", "range"}:
            continue
        column = column_for_field(dataframe, field)
        if not column:
            continue
        values = pd.to_numeric(dataframe[column], errors="coerce").dropna()
        if values.empty or values.nunique() <= 1:
            continue
        rows.append(
            {
                "Indicator": short_label(field["label"], 50),
                "Average": round(float(values.mean()), 2),
                "Median": round(float(values.median()), 2),
                "Maximum": round(float(values.max()), 2),
            }
        )
    chart_data = pd.DataFrame(rows).sort_values("Average", ascending=False).head(20) if rows else pd.DataFrame()
    if chart_data.empty:
        st.info("No meaningful numeric indicators are available.")
        return
    bars = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=8, cornerRadiusBottomRight=8, color="#38bdf8", opacity=0.82)
        .encode(
            x=alt.X("Average:Q", title="Average"),
            y=alt.Y("Indicator:N", sort="-x", title=None),
            tooltip=["Indicator:N", "Average:Q", "Median:Q", "Maximum:Q"],
        )
    )
    median_points = (
        alt.Chart(chart_data)
        .mark_point(size=82, filled=True, color="#f97316", stroke="#f8fbff", strokeWidth=1)
        .encode(x="Median:Q", y=alt.Y("Indicator:N", sort="-x", title=None), tooltip=["Indicator:N", "Median:Q"])
    )
    chart = alt.layer(bars, median_points).properties(height=min(max(len(chart_data) * 28, 360), 640), title=title)
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def parse_gps_value(value: object) -> tuple[float | None, float | None, float | None, float | None]:
    text = clean_text(value)
    if not text:
        return None, None, None, None
    parts = re.split(r"[\s,]+", text)
    numbers: list[float] = []
    for part in parts:
        try:
            numbers.append(float(part))
        except ValueError:
            continue
    if len(numbers) < 2:
        return None, None, None, None
    lat, lon = numbers[0], numbers[1]
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None, None, None
    altitude = numbers[2] if len(numbers) > 2 else None
    accuracy = numbers[3] if len(numbers) > 3 else None
    return lat, lon, altitude, accuracy


def parse_numeric_series(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce")


def source_row_label(index_value: object) -> str:
    try:
        return str(int(index_value) + 2)
    except (TypeError, ValueError):
        return clean_text(index_value) or "Unknown"


def gps_accuracy_band(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "Unknown"
    if number <= 10:
        return "Excellent (<=10m)"
    if number <= 25:
        return "Good (<=25m)"
    if number <= 50:
        return "Review (<=50m)"
    return "Weak (>50m)"


def gps_accuracy_color(band: object) -> list[int]:
    return GPS_ACCURACY_COLORS.get(clean_text(band), GPS_ACCURACY_COLORS["Unknown"])


def meaningful_text(value: object) -> str:
    text = clean_text(value)
    if text.lower() in {"", "nan", "none", "null", "n/a", "na", "-", "unspecified"}:
        return ""
    return text


def gps_class_label(row: pd.Series) -> str:
    class_id = meaningful_text(row.get("Class ID", ""))
    tpm_id = meaningful_text(row.get("TPM_TLS_ID", ""))
    if class_id and tpm_id and class_id != tpm_id:
        return f"{class_id} | {tpm_id}"
    return class_id or tpm_id or clean_text(row.get("Point", "")) or "Class"


def gps_zoom_level(gps: pd.DataFrame) -> int:
    lat_span = float(gps["lat"].max() - gps["lat"].min())
    lon_span = float(gps["lon"].max() - gps["lon"].min())
    span = max(lat_span, lon_span)
    if span <= 0.01:
        return 13
    if span <= 0.05:
        return 11
    if span <= 0.2:
        return 9
    if span <= 1:
        return 7
    return 5


def add_gps_context(dataframe: pd.DataFrame, gps: pd.DataFrame) -> pd.DataFrame:
    enriched = gps.copy()
    for label, candidates in GPS_CONTEXT_CANDIDATES.items():
        column = first_existing_column(dataframe, candidates)
        if not column:
            enriched[label] = "N/A"
            continue
        values = dataframe.loc[enriched["_row"], column].fillna("").astype(str).str.strip().replace("", "N/A")
        enriched[label] = values.to_numpy()
    enriched["Display Class"] = enriched.apply(gps_class_label, axis=1)
    return enriched


def haversine_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    radius_km = 6371.0088
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def format_distance_label(distance_km: object) -> str:
    number = pd.to_numeric(pd.Series([distance_km]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "N/A"
    if number < 1:
        return f"{number * 1000:.0f} m"
    return f"{number:.2f} km"


def class_count(gps: pd.DataFrame) -> int:
    if gps.empty:
        return 0
    labels = gps["Display Class"].fillna("").astype(str).map(meaningful_text)
    labels = labels[labels != ""]
    return int(labels.nunique()) if not labels.empty else len(gps)


def build_pairwise_distances(gps: pd.DataFrame, max_points: int = 250) -> pd.DataFrame:
    columns = [
        "Class A",
        "Class B",
        "Point A",
        "Point B",
        "Distance (km)",
        "Distance (m)",
        "Province",
        "District",
        "Village A",
        "Village B",
    ]
    if len(gps) < 2:
        return pd.DataFrame(columns=columns)
    work = gps.head(max_points).reset_index(drop=True)
    rows: list[dict[str, Any]] = []
    for left_index, right_index in combinations(range(len(work)), 2):
        left = work.iloc[left_index]
        right = work.iloc[right_index]
        distance_km = haversine_km(float(left["lat"]), float(left["lon"]), float(right["lat"]), float(right["lon"]))
        rows.append(
            {
                "Class A": left["Display Class"],
                "Class B": right["Display Class"],
                "Point A": left["Point"],
                "Point B": right["Point"],
                "Distance (km)": round(distance_km, 3),
                "Distance (m)": round(distance_km * 1000, 1),
                "Walk Time (min)": round((distance_km / 4.5) * 60, 1),
                "Drive Time (min)": round((distance_km / 35) * 60, 1),
                "Province": left.get("Province", "N/A"),
                "District": left.get("District", "N/A"),
                "Village A": left.get("Village", "N/A"),
                "Village B": right.get("Village", "N/A"),
            }
        )
    return pd.DataFrame(rows).sort_values("Distance (km)") if rows else pd.DataFrame(columns=columns)


def build_nearest_neighbor_table(gps: pd.DataFrame) -> pd.DataFrame:
    pairwise = build_pairwise_distances(gps)
    if pairwise.empty:
        return pd.DataFrame(columns=["Point", "Class", "Nearest Point", "Nearest Class", "Nearest Distance (km)", "Nearest Distance (m)"])
    rows: list[dict[str, Any]] = []
    point_labels = pd.unique(pd.concat([pairwise["Point A"], pairwise["Point B"]], ignore_index=True))
    for point in point_labels:
        matches = pairwise[(pairwise["Point A"] == point) | (pairwise["Point B"] == point)].sort_values("Distance (km)")
        if matches.empty:
            continue
        nearest = matches.iloc[0]
        if nearest["Point A"] == point:
            class_label = nearest["Class A"]
            nearest_point = nearest["Point B"]
            nearest_class = nearest["Class B"]
        else:
            class_label = nearest["Class B"]
            nearest_point = nearest["Point A"]
            nearest_class = nearest["Class A"]
        rows.append(
            {
                "Point": point,
                "Class": class_label,
                "Nearest Point": nearest_point,
                "Nearest Class": nearest_class,
                "Nearest Distance (km)": nearest["Distance (km)"],
                "Nearest Distance (m)": nearest["Distance (m)"],
            }
        )
    return pd.DataFrame(rows).sort_values("Nearest Distance (km)") if rows else pd.DataFrame()


def distance_line_record(left: pd.Series, right: pd.Series, distance_km: object) -> dict[str, Any]:
    distance_value = float(distance_km)
    return {
        "start_lat": float(left["lat"]),
        "start_lon": float(left["lon"]),
        "end_lat": float(right["lat"]),
        "end_lon": float(right["lon"]),
        "mid_lat": (float(left["lat"]) + float(right["lat"])) / 2,
        "mid_lon": (float(left["lon"]) + float(right["lon"])) / 2,
        "Distance (km)": round(distance_value, 3),
        "Distance Label": format_distance_label(distance_value),
    }


def gps_point_option_label(row: pd.Series) -> str:
    place_parts = [meaningful_text(row.get(column, "")) for column in ["Province", "District", "Village"]]
    place = " / ".join(part for part in place_parts if part)
    class_label = short_label(row.get("Display Class", ""), 54)
    if place:
        return f"{row['Point']} | {class_label} | {place}"
    return f"{row['Point']} | {class_label}"


def build_selected_distance_line(gps: pd.DataFrame, point_a: str, point_b: str) -> pd.DataFrame:
    if point_a == point_b:
        return pd.DataFrame()
    indexed = gps.set_index("Point", drop=False)
    if point_a not in indexed.index or point_b not in indexed.index:
        return pd.DataFrame()
    left = indexed.loc[point_a]
    right = indexed.loc[point_b]
    distance_km = haversine_km(float(left["lat"]), float(left["lon"]), float(right["lat"]), float(right["lon"]))
    return pd.DataFrame([distance_line_record(left, right, distance_km)])


def render_gps_measure_controls(gps: pd.DataFrame, widget_key: str) -> pd.DataFrame:
    st.markdown("### Measure Distance")
    if len(gps) < 2:
        st.info("At least two GPS points are needed to measure distance.")
        return pd.DataFrame()
    point_options = gps["Point"].tolist()
    option_labels = {row["Point"]: gps_point_option_label(row) for _, row in gps.iterrows()}
    measure_cols = st.columns([1, 1, 0.7], gap="large")
    with measure_cols[0]:
        point_a = st.selectbox("From point", point_options, format_func=lambda value: option_labels.get(value, value), key=f"{widget_key}-measure-from")
    with measure_cols[1]:
        default_to = 1 if len(point_options) > 1 else 0
        point_b = st.selectbox("To point", point_options, index=default_to, format_func=lambda value: option_labels.get(value, value), key=f"{widget_key}-measure-to")
    line = build_selected_distance_line(gps, point_a, point_b)
    with measure_cols[2]:
        distance_label = line.iloc[0]["Distance Label"] if not line.empty else "Select two points"
        render_metric_card("Selected Distance", str(distance_label), "Shown directly on the map line.", "#38bdf8")
    if point_a == point_b:
        st.warning("Please select two different GPS points for distance measurement.")
    return line


def build_distance_lines(gps: pd.DataFrame, max_lines: int = 80, nearest_only: bool = True) -> pd.DataFrame:
    if len(gps) < 2:
        return pd.DataFrame()
    work = gps.set_index("Point", drop=False)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    if nearest_only:
        nearest = build_nearest_neighbor_table(gps)
        for _, row in nearest.iterrows():
            if row["Point"] not in work.index or row["Nearest Point"] not in work.index:
                continue
            pair_key = tuple(sorted([row["Point"], row["Nearest Point"]]))
            if pair_key in seen:
                continue
            seen.add(pair_key)
            rows.append(distance_line_record(work.loc[row["Point"]], work.loc[row["Nearest Point"]], row["Nearest Distance (km)"]))
            if len(rows) >= max_lines:
                break
        return pd.DataFrame(rows)

    pairwise = build_pairwise_distances(gps)
    if pairwise.empty:
        return pd.DataFrame()
    for _, row in pairwise.iterrows():
        pair_key = tuple(sorted([row["Point A"], row["Point B"]]))
        if pair_key in seen or row["Point A"] not in work.index or row["Point B"] not in work.index:
            continue
        seen.add(pair_key)
        left = work.loc[row["Point A"]]
        right = work.loc[row["Point B"]]
        rows.append(distance_line_record(left, right, row["Distance (km)"]))
        if len(rows) >= max_lines:
            break
    return pd.DataFrame(rows)


def build_group_distance_summary(gps: pd.DataFrame, group_column: str) -> pd.DataFrame:
    if group_column not in gps.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for group, group_data in gps.groupby(group_column, dropna=False):
        group_name = meaningful_text(group) or "N/A"
        pairwise = build_pairwise_distances(group_data)
        nearest = build_nearest_neighbor_table(group_data)
        rows.append(
            {
                group_column: group_name,
                "Classes Seen": class_count(group_data),
                "GPS Points": len(group_data),
                "Median Nearest Distance (km)": round(float(nearest["Nearest Distance (km)"].median()), 3) if not nearest.empty else None,
                "Maximum Class Distance (km)": round(float(pairwise["Distance (km)"].max()), 3) if not pairwise.empty else None,
            }
        )
    return pd.DataFrame(rows).sort_values(["Classes Seen", "GPS Points"], ascending=False)


def build_gps_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    output_columns = ["_row", "Point", "Source Row", "lat", "lon", "altitude", "accuracy", "Accuracy Band"]
    if dataframe.empty:
        return pd.DataFrame(columns=output_columns)

    lat_col = first_existing_column(dataframe, GPS_LATITUDE_CANDIDATES)
    lon_col = first_existing_column(dataframe, GPS_LONGITUDE_CANDIDATES)
    alt_col = first_existing_column(dataframe, GPS_ALTITUDE_CANDIDATES)
    acc_col = first_existing_column(dataframe, GPS_ACCURACY_CANDIDATES)
    gps_col = first_existing_column(dataframe, GPS_POINT_CANDIDATES)

    if lat_col and lon_col:
        gps = pd.DataFrame(
            {
                "_row": dataframe.index,
                "lat": parse_numeric_series(dataframe[lat_col]),
                "lon": parse_numeric_series(dataframe[lon_col]),
                "altitude": parse_numeric_series(dataframe[alt_col]) if alt_col else pd.NA,
                "accuracy": parse_numeric_series(dataframe[acc_col]) if acc_col else pd.NA,
            },
            index=dataframe.index,
        )
        gps = gps[gps["lat"].between(-90, 90) & gps["lon"].between(-180, 180)].copy()
    elif gps_col:
        rows = []
        for index, value in dataframe[gps_col].items():
            lat, lon, altitude, accuracy = parse_gps_value(value)
            if lat is None or lon is None:
                continue
            rows.append({"_row": index, "lat": lat, "lon": lon, "altitude": altitude, "accuracy": accuracy})
        gps = pd.DataFrame(rows)
    else:
        return pd.DataFrame(columns=output_columns)

    if gps.empty:
        return pd.DataFrame(columns=output_columns)

    gps = gps.reset_index(drop=True)
    gps["Point"] = [f"GPS-{index + 1:03d}" for index in range(len(gps))]
    gps["Source Row"] = gps["_row"].apply(source_row_label)
    gps["Accuracy Band"] = gps["accuracy"].apply(gps_accuracy_band)
    gps = add_gps_context(dataframe, gps)
    return gps


def folium_color_for_band(band: object) -> str:
    return {
        "Excellent (<=10m)": "#22c55e",
        "Good (<=25m)": "#38bdf8",
        "Review (<=50m)": "#f59e0b",
        "Weak (>50m)": "#ef4444",
        "Unknown": "#94a3b8",
    }.get(clean_text(band), "#94a3b8")


def folium_popup_html(row: pd.Series) -> str:
    details = [
        ("Point", row.get("Point", "")),
        ("Class", row.get("Display Class", "")),
        ("TPM_TLS_ID", row.get("TPM_TLS_ID", "")),
        ("Surveyor", row.get("Surveyor", "")),
        ("Surveyor ID", row.get("Surveyor ID", "")),
        ("Reviewer", row.get("Reviewer", "")),
        ("GPS Time", row.get("GPS Time", "")),
        ("Region", row.get("Region", "")),
        ("Province", row.get("Province", "")),
        ("District", row.get("District", "")),
        ("Village", row.get("Village", "")),
        ("Latitude", f"{float(row.get('lat', 0)):.6f}"),
        ("Longitude", f"{float(row.get('lon', 0)):.6f}"),
        ("Altitude", f"{pd.to_numeric(pd.Series([row.get('altitude')]), errors='coerce').iloc[0]:.1f} m" if pd.notna(pd.to_numeric(pd.Series([row.get("altitude")]), errors="coerce").iloc[0]) else "N/A"),
        ("Accuracy", f"{pd.to_numeric(pd.Series([row.get('accuracy')]), errors='coerce').iloc[0]:.1f} m" if pd.notna(pd.to_numeric(pd.Series([row.get("accuracy")]), errors="coerce").iloc[0]) else "N/A"),
    ]
    rows = "".join(
        f"<tr><td style='padding:3px 10px 3px 0;color:#64748b'>{html.escape(label)}</td><td style='padding:3px 0;color:#0f172a;font-weight:600'>{html.escape(clean_text(value) or 'N/A')}</td></tr>"
        for label, value in details
    )
    return f"<div style='font-family:Arial,sans-serif;font-size:12px;min-width:280px'><table>{rows}</table></div>"


def add_folium_tiles(map_object: Any, map_type: str) -> None:
    if folium is None:
        return
    if map_type == "Satellite":
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Tiles © Esri, Maxar, Earthstar Geographics, and the GIS User Community",
            name="Satellite",
            control=False,
        ).add_to(map_object)
        folium.TileLayer(
            tiles="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}",
            attr="Labels © Esri",
            name="Road Labels",
            overlay=True,
            control=False,
        ).add_to(map_object)
        folium.TileLayer(
            tiles="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
            attr="Places © Esri",
            name="Place Labels",
            overlay=True,
            control=False,
        ).add_to(map_object)
        return
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        attr="© OpenStreetMap contributors © CARTO",
        name="Dark",
        subdomains="abcd",
        control=False,
    ).add_to(map_object)


def render_folium_gps_map(gps: pd.DataFrame, map_type: str, line_data: pd.DataFrame | None = None) -> None:
    if folium is None or components is None:
        return
    center = [float(gps["lat"].median()), float(gps["lon"].median())]
    map_object = folium.Map(location=center, zoom_start=gps_zoom_level(gps), tiles=None, control_scale=True, prefer_canvas=True)
    add_folium_tiles(map_object, map_type)

    point_group = folium.FeatureGroup(name="GPS Points", show=True)
    for _, row in gps.iterrows():
        tooltip = f"{html.escape(clean_text(row.get('Point', '')))} | {html.escape(short_label(row.get('Display Class', ''), 44))}"
        folium.CircleMarker(
            location=[float(row["lat"]), float(row["lon"])],
            radius=6,
            color="#f8fbff",
            weight=1.4,
            fill=True,
            fill_color=folium_color_for_band(row.get("Accuracy Band", "")),
            fill_opacity=0.88,
            tooltip=tooltip,
            popup=folium.Popup(folium_popup_html(row), max_width=380),
        ).add_to(point_group)
    point_group.add_to(map_object)

    if line_data is not None and not line_data.empty:
        for _, line in line_data.iterrows():
            coordinates = [(float(line["start_lat"]), float(line["start_lon"])), (float(line["end_lat"]), float(line["end_lon"]))]
            label = clean_text(line.get("Distance Label", "")) or format_distance_label(line.get("Distance (km)", ""))
            folium.PolyLine(
                locations=coordinates,
                color="#38bdf8",
                weight=5,
                opacity=0.95,
                tooltip=f"Distance: {html.escape(label)}",
            ).add_to(map_object)
            folium.Marker(
                location=[float(line["mid_lat"]), float(line["mid_lon"])],
                icon=folium.DivIcon(
                    html=(
                        "<div style='background:#07111f;color:#f8fbff;border:1px solid rgba(56,189,248,.75);"
                        "border-radius:999px;padding:4px 9px;font-size:12px;font-weight:800;white-space:nowrap;"
                        "box-shadow:0 8px 18px rgba(0,0,0,.35)'>"
                        f"{html.escape(label)}</div>"
                    )
                ),
            ).add_to(map_object)

    if Fullscreen is not None:
        Fullscreen(position="topright").add_to(map_object)
    if MeasureControl is not None:
        MeasureControl(position="topleft", primary_length_unit="meters", secondary_length_unit="kilometers").add_to(map_object)

    bounds = [[float(gps["lat"].min()), float(gps["lon"].min())], [float(gps["lat"].max()), float(gps["lon"].max())]]
    if bounds[0] != bounds[1]:
        map_object.fit_bounds(bounds, padding=(28, 28))
    components.html(map_object._repr_html_(), height=690, scrolling=False)


def render_gps_map(gps: pd.DataFrame, map_mode: str = "Smart Points", map_style_name: str = "Dark", line_data: pd.DataFrame | None = None) -> None:
    map_points = gps.copy()
    map_points["latitude"] = map_points["lat"]
    map_points["longitude"] = map_points["lon"]
    if folium is not None and components is not None:
        render_folium_gps_map(gps, map_style_name, line_data)
        return
    if map_style_name == "Satellite":
        st.map(map_points[["latitude", "longitude"]], use_container_width=True)
        return
    if pdk is None:
        st.map(map_points[["latitude", "longitude"]], use_container_width=True)
        return

    deck_points = map_points.copy()
    deck_points["accuracy_number"] = pd.to_numeric(deck_points["accuracy"], errors="coerce")
    deck_points["map_radius"] = deck_points["accuracy_number"].clip(10, 450).fillna(45)
    deck_points["point_radius"] = (85 - deck_points["accuracy_number"].clip(0, 70)).clip(24, 78).fillna(44)
    deck_points["heat_weight"] = (80 - deck_points["accuracy_number"].clip(0, 75)).clip(8, 80).fillna(20)
    deck_points["quality_color"] = deck_points["Accuracy Band"].apply(gps_accuracy_color)
    deck_points["line_color"] = [[248, 251, 255, 235] for _ in range(len(deck_points))]
    deck_points["altitude_label"] = pd.to_numeric(deck_points["altitude"], errors="coerce").round(1).astype("string").fillna("N/A")
    deck_points["accuracy_label"] = pd.to_numeric(deck_points["accuracy"], errors="coerce").round(1).astype("string").fillna("N/A")
    deck_points["tooltip_class"] = deck_points["Display Class"].fillna("N/A").astype(str)
    deck_points["tooltip_tpm"] = deck_points["TPM_TLS_ID"].fillna("N/A").astype(str)
    deck_points["tooltip_surveyor"] = deck_points["Surveyor"].fillna("N/A").astype(str)
    deck_points["tooltip_surveyor_id"] = deck_points["Surveyor ID"].fillna("N/A").astype(str)
    deck_points["tooltip_reviewer"] = deck_points["Reviewer"].fillna("N/A").astype(str)
    deck_points["tooltip_time"] = deck_points["GPS Time"].fillna("N/A").astype(str)
    deck_points["tooltip_place"] = (
        deck_points["Province"].fillna("N/A").astype(str)
        + " / "
        + deck_points["District"].fillna("N/A").astype(str)
        + " / "
        + deck_points["Village"].fillna("N/A").astype(str)
    )

    point_layer = pdk.Layer(
        "ScatterplotLayer",
        data=deck_points,
        get_position="[longitude, latitude]",
        get_radius="point_radius",
        get_fill_color="quality_color",
        get_line_color="line_color",
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )
    label_layer = pdk.Layer(
        "TextLayer",
        data=deck_points,
        get_position="[longitude, latitude]",
        get_text="Point",
        get_size=12,
        get_color=[226, 232, 240, 230],
        get_alignment_baseline="'bottom'",
        get_pixel_offset=[0, -14],
        pickable=False,
    )

    layers: list[Any] = []
    pitch = 0
    if map_mode == "Heatmap":
        layers.extend(
            [
                pdk.Layer(
                    "HeatmapLayer",
                    data=deck_points,
                    get_position="[longitude, latitude]",
                    get_weight="heat_weight",
                    radius_pixels=72,
                    intensity=1.25,
                    threshold=0.03,
                    pickable=False,
                ),
                pdk.Layer(
                    "ScatterplotLayer",
                    data=deck_points,
                    get_position="[longitude, latitude]",
                    get_radius=18,
                    get_fill_color=[248, 251, 255, 150],
                    pickable=True,
                    auto_highlight=True,
                ),
            ]
        )
    elif map_mode == "3D Density":
        pitch = 48
        layers.append(
            pdk.Layer(
                "HexagonLayer",
                data=deck_points,
                get_position="[longitude, latitude]",
                radius=135,
                coverage=0.88,
                elevation_scale=38,
                elevation_range=[0, 3600],
                extruded=True,
                pickable=True,
                auto_highlight=True,
                color_range=[
                    [34, 197, 94, 120],
                    [56, 189, 248, 150],
                    [139, 92, 246, 180],
                    [245, 158, 11, 205],
                    [239, 68, 68, 225],
                ],
            )
        )
        layers.append(point_layer)
    elif map_mode == "Class Distance":
        if line_data is not None and not line_data.empty:
            layers.append(
                pdk.Layer(
                    "LineLayer",
                    data=line_data,
                    get_source_position="[start_lon, start_lat]",
                    get_target_position="[end_lon, end_lat]",
                    get_color=[56, 189, 248, 190],
                    get_width=2.5,
                    width_units="pixels",
                    pickable=False,
                )
            )
            layers.append(
                pdk.Layer(
                    "TextLayer",
                    data=line_data,
                    get_position="[mid_lon, mid_lat]",
                    get_text="Distance Label",
                    get_size=13,
                    get_color=[248, 251, 255, 245],
                    get_angle=0,
                    get_alignment_baseline="'center'",
                    background=True,
                    get_background_color=[7, 17, 31, 220],
                    background_padding=[4, 3],
                    pickable=False,
                )
            )
        layers.append(point_layer)
    elif map_mode == "Accuracy Radius":
        layers.extend(
            [
                pdk.Layer(
                    "ScatterplotLayer",
                    data=deck_points,
                    get_position="[longitude, latitude]",
                    get_radius="map_radius",
                    get_fill_color=[56, 189, 248, 44],
                    get_line_color="quality_color",
                    line_width_min_pixels=2,
                    pickable=True,
                    auto_highlight=True,
                ),
                pdk.Layer(
                    "ScatterplotLayer",
                    data=deck_points,
                    get_position="[longitude, latitude]",
                    get_radius=18,
                    get_fill_color="quality_color",
                    get_line_color=[248, 251, 255, 230],
                    line_width_min_pixels=1,
                    pickable=True,
                    auto_highlight=True,
                ),
            ]
        )
    else:
        layers.append(point_layer)

    if line_data is not None and not line_data.empty and map_mode != "Class Distance":
        layers.insert(
            0,
            pdk.Layer(
                "LineLayer",
                data=line_data,
                get_source_position="[start_lon, start_lat]",
                get_target_position="[end_lon, end_lat]",
                get_color=[56, 189, 248, 190],
                get_width=2.5,
                width_units="pixels",
                pickable=False,
            ),
        )
        layers.insert(
            1,
            pdk.Layer(
                "TextLayer",
                data=line_data,
                get_position="[mid_lon, mid_lat]",
                get_text="Distance Label",
                get_size=13,
                get_color=[248, 251, 255, 245],
                get_alignment_baseline="'center'",
                background=True,
                get_background_color=[7, 17, 31, 220],
                background_padding=[4, 3],
                pickable=False,
            ),
        )

    if len(deck_points) <= 300 and map_mode in {"Smart Points", "Accuracy Radius", "Class Distance"}:
        layers.append(label_layer)

    if not layers:
        layers = [
            pdk.Layer(
                "ScatterplotLayer",
                data=deck_points,
                get_position="[longitude, latitude]",
                get_radius=45,
                get_fill_color="quality_color",
                get_line_color=[248, 251, 255, 230],
                line_width_min_pixels=1,
                pickable=True,
            )
        ]

    tooltip = {
        "html": (
            "<b>{Point}</b><br/>"
            "Class: {tooltip_class}<br/>"
            "TPM_TLS_ID: {tooltip_tpm}<br/>"
            "Surveyor: {tooltip_surveyor}<br/>"
            "Surveyor ID: {tooltip_surveyor_id}<br/>"
            "Reviewer: {tooltip_reviewer}<br/>"
            "GPS Time: {tooltip_time}<br/>"
            "Place: {tooltip_place}<br/>"
            "Lat: {lat}<br/>Lon: {lon}<br/>"
            "Altitude: {altitude_label} m<br/>Accuracy: {accuracy_label} m<br/>"
            "Quality: {Accuracy Band}<br/>Row: {Source Row}"
        ),
        "style": {"backgroundColor": "#07111f", "color": "#f8fbff", "fontFamily": CHART_FONT},
    }
    view_state = pdk.ViewState(
        latitude=float(deck_points["latitude"].median()),
        longitude=float(deck_points["longitude"].median()),
        zoom=gps_zoom_level(deck_points),
        pitch=pitch,
        bearing=-10 if pitch else 0,
    )
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style=GPS_MAP_STYLES.get(map_style_name, GPS_MAP_STYLES["Dark"]),
    )
    try:
        st.pydeck_chart(deck, use_container_width=True, height=620)
    except TypeError:
        st.pydeck_chart(deck)
    except Exception:
        st.map(map_points[["latitude", "longitude"]], use_container_width=True)


def gps_filter_values(gps: pd.DataFrame, column: str, limit: int = 250, require_variation: bool = True) -> list[str]:
    if column not in gps.columns:
        return []
    values = gps[column].fillna("").astype(str).map(meaningful_text)
    values = values[values != ""]
    if values.empty or (require_variation and values.nunique() <= 1):
        return []
    return sorted(values.unique().tolist())[:limit]


def apply_gps_filters(gps: pd.DataFrame, widget_key: str) -> pd.DataFrame:
    filtered = gps.copy()
    st.markdown("### GPS Filters")
    region_col, province_col, district_col = st.columns(3, gap="large")

    with region_col:
        region_options = gps_filter_values(filtered, "Region", require_variation=False)
        selected_regions = st.multiselect("Region", region_options, key=f"{widget_key}-filter-region") if region_options else []
    if selected_regions:
        filtered = filtered[filtered["Region"].astype(str).isin(selected_regions)]

    with province_col:
        province_options = gps_filter_values(filtered, "Province", require_variation=False)
        selected_provinces = st.multiselect("Province", province_options, key=f"{widget_key}-filter-province") if province_options else []
    if selected_provinces:
        filtered = filtered[filtered["Province"].astype(str).isin(selected_provinces)]

    with district_col:
        district_options = gps_filter_values(filtered, "District", require_variation=False)
        selected_districts = st.multiselect("District", district_options, key=f"{widget_key}-filter-district") if district_options else []
    if selected_districts:
        filtered = filtered[filtered["District"].astype(str).isin(selected_districts)]
    return filtered


def select_distance_focus(gps: pd.DataFrame, widget_key: str) -> tuple[str | None, str | None, pd.DataFrame]:
    province = None
    district = None
    focus = gps.copy()
    st.markdown("### Distance Focus")
    focus_cols = st.columns(2, gap="large")
    province_options = gps_filter_values(gps, "Province", limit=500, require_variation=False)
    with focus_cols[0]:
        if province_options:
            province = st.selectbox("Province for class-distance analysis", province_options, key=f"{widget_key}-distance-province")
            focus = focus[focus["Province"].astype(str) == province]
        else:
            st.info("Province field is not available for distance focus.")
    district_options = gps_filter_values(focus, "District", limit=500, require_variation=False)
    with focus_cols[1]:
        if district_options:
            district = st.selectbox("District for class-distance analysis", district_options, key=f"{widget_key}-distance-district")
            focus = focus[focus["District"].astype(str) == district]
        else:
            st.info("District field is not available for distance focus.")
    return province, district, focus


def render_gps_distance_intelligence(gps: pd.DataFrame, province: str | None, district: str | None, district_gps: pd.DataFrame) -> None:
    st.markdown("### Class Distance Intelligence")
    province_gps = gps[gps["Province"].astype(str) == province] if province and "Province" in gps.columns else gps
    pairwise = build_pairwise_distances(district_gps)
    nearest = build_nearest_neighbor_table(district_gps)

    metric_cols = st.columns(4, gap="large")
    with metric_cols[0]:
        render_metric_card("Province Classes", f"{class_count(province_gps):,}", f"Classes observed in {province or 'selected province'}.", "#38bdf8")
    with metric_cols[1]:
        render_metric_card("District Classes", f"{class_count(district_gps):,}", f"Classes observed in {district or 'selected district'}.", "#22c55e")
    with metric_cols[2]:
        nearest_text = f"{nearest['Nearest Distance (km)'].median():.2f} km" if not nearest.empty else "N/A"
        render_metric_card("Median Nearest Gap", nearest_text, "Typical distance from each class to its nearest class.", "#8b5cf6")
    with metric_cols[3]:
        max_text = f"{pairwise['Distance (km)'].max():.2f} km" if not pairwise.empty else "N/A"
        render_metric_card("Maximum Gap", max_text, "Largest class-to-class distance in the selected district.", "#f97316")

    st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    left, right = st.columns(2, gap="large")
    with left:
        if "District" in province_gps.columns:
            district_summary = build_group_distance_summary(province_gps, "District")
            if not district_summary.empty:
                render_bar_chart(district_summary, "District", "Classes Observed by District", "#38bdf8", value_column="Classes Seen")
    with right:
        if not nearest.empty:
            nearest_chart_data = nearest.head(20).copy()
            nearest_chart_data["Class"] = nearest_chart_data["Class"].map(lambda value: short_label(value, 36))
            chart = (
                alt.Chart(nearest_chart_data)
                .mark_bar(cornerRadiusTopRight=7, cornerRadiusBottomRight=7, color="#8b5cf6", opacity=0.84)
                .encode(
                    x=alt.X("Nearest Distance (km):Q", title="Nearest class distance"),
                    y=alt.Y("Class:N", sort="x", title=None),
                    tooltip=["Point:N", "Class:N", "Nearest Point:N", "Nearest Class:N", alt.Tooltip("Nearest Distance (km):Q", format=".3f")],
                )
                .properties(height=CHART_HEIGHT, title="Nearest Class Distance")
            )
            st.altair_chart(modernize_chart(chart), use_container_width=True)

    if pairwise.empty:
        st.info("At least two GPS points are needed in the selected district to calculate class-to-class distances.")
        return

    st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    st.markdown("### Class-to-Class Distance Register")
    st.dataframe(pairwise.head(500), use_container_width=True, hide_index=True, height=420)


def render_gps_tracking(dataframe: pd.DataFrame, widget_key: str = "gps") -> None:
    raw_gps = build_gps_dataframe(dataframe)
    if raw_gps.empty:
        st.info("No valid GPS coordinates were found in this clean dataset.")
        return
    gps = apply_gps_filters(raw_gps, widget_key)
    if gps.empty:
        st.warning("No GPS points match the selected filters.")
        return

    accuracy_values = pd.to_numeric(gps["accuracy"], errors="coerce").dropna()
    altitude_values = pd.to_numeric(gps["altitude"], errors="coerce").dropna()
    coverage = (len(gps) / len(dataframe) * 100) if len(dataframe) else 0

    metric_cols = st.columns(4, gap="large")
    with metric_cols[0]:
        render_metric_card("GPS Points", f"{len(gps):,}", "Valid clean-data coordinates shown on the map.", "#38bdf8")
    with metric_cols[1]:
        render_metric_card("GPS Coverage", f"{coverage:.1f}%", "Share of clean rows with valid latitude and longitude.", "#22c55e")
    with metric_cols[2]:
        accuracy_text = f"{accuracy_values.median():.1f}m" if not accuracy_values.empty else "N/A"
        render_metric_card("Median Accuracy", accuracy_text, "Lower values indicate stronger GPS capture.", "#8b5cf6")
    with metric_cols[3]:
        altitude_text = f"{altitude_values.min():.0f} - {altitude_values.max():.0f}m" if not altitude_values.empty else "N/A"
        render_metric_card("Altitude Range", altitude_text, "Altitude span from GPS points where available.", "#f97316")

    st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    distance_line = render_gps_measure_controls(gps, widget_key)

    st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    map_header, map_type_col = st.columns([1.8, 1], gap="large")
    with map_header:
        st.markdown("### GPS Map")
    with map_type_col:
        map_style = st.radio("Map type", ["Dark", "Satellite"], horizontal=True, key=f"{widget_key}-map-style")
    render_gps_map(gps, "Smart Points", map_style, distance_line)

    st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    with st.expander("Distance analytics and registers", expanded=False):
        focus_province = gps["Province"].mode().iloc[0] if "Province" in gps.columns and not gps["Province"].mode().empty else None
        focus_district = gps["District"].mode().iloc[0] if "District" in gps.columns and not gps["District"].mode().empty else None
        render_gps_distance_intelligence(gps, focus_province, focus_district, gps)

    st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    with st.expander("GPS quality charts", expanded=False):
        map_left, map_right = st.columns([1.25, 1], gap="large")
    chart_tooltips: list[Any] = [
        "Point:N",
        "Display Class:N",
        "TPM_TLS_ID:N",
        "Surveyor:N",
        "Surveyor ID:N",
        "Reviewer:N",
        "GPS Time:N",
        alt.Tooltip("lat:Q", title="Latitude", format=".5f"),
        alt.Tooltip("lon:Q", title="Longitude", format=".5f"),
        alt.Tooltip("altitude:Q", title="Altitude", format=".1f"),
        alt.Tooltip("accuracy:Q", title="Accuracy", format=".1f"),
        "Source Row:N",
    ]
    for context_column in ["Region", "Province", "District", "Village", "School", "Class ID", "Class Type"]:
        if context_column in gps.columns:
            chart_tooltips.append(f"{context_column}:N")
    with map_left:
        scatter = (
            alt.Chart(gps)
            .mark_circle(size=115, opacity=0.84, stroke="#f8fbff", strokeWidth=0.8)
            .encode(
                x=alt.X("lon:Q", title="Longitude", scale=alt.Scale(zero=False)),
                y=alt.Y("lat:Q", title="Latitude", scale=alt.Scale(zero=False)),
                color=alt.Color(
                    "Accuracy Band:N",
                    scale=alt.Scale(
                        domain=["Excellent (<=10m)", "Good (<=25m)", "Review (<=50m)", "Weak (>50m)", "Unknown"],
                        range=["#22c55e", "#38bdf8", "#f59e0b", "#ef4444", "#94a3b8"],
                    ),
                    legend=alt.Legend(title=None),
                ),
                tooltip=chart_tooltips,
            )
            .properties(height=430, title="GPS Coordinate Scatter")
        )
        st.altair_chart(modernize_chart(scatter), use_container_width=True)
    with map_right:
        if not accuracy_values.empty:
            accuracy_mix = gps.groupby("Accuracy Band").size().reset_index(name="Count")
            render_donut_chart(accuracy_mix, "Accuracy Band", "GPS Accuracy Quality")
        elif not altitude_values.empty:
            altitude_chart = (
                alt.Chart(gps.dropna(subset=["altitude"]))
                .mark_bar(cornerRadiusTopLeft=7, cornerRadiusTopRight=7, color="#f97316", opacity=0.86)
                .encode(
                    x=alt.X("altitude:Q", bin=alt.Bin(maxbins=18), title="Altitude"),
                    y=alt.Y("count():Q", title="GPS Points"),
                    tooltip=[alt.Tooltip("altitude:Q", bin=True), alt.Tooltip("count():Q", title="GPS Points")],
                )
                .properties(height=430, title="GPS Altitude Distribution")
            )
            st.altair_chart(modernize_chart(altitude_chart), use_container_width=True)

    st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    detail_left, detail_right = st.columns(2, gap="large")
    group_column = next((column for column in ["Province", "District", "Surveyor"] if column in gps.columns and gps[column].nunique(dropna=True) > 1), None)
    with detail_left:
        if group_column:
            group_counts = gps[group_column].fillna("Unspecified").astype(str).str.strip().replace("", "Unspecified").value_counts().head(18).reset_index()
            group_counts.columns = [group_column, "Count"]
            render_bar_chart(group_counts, group_column, f"GPS Points by {group_column}", "#38bdf8")
    with detail_right:
        if not altitude_values.empty and not accuracy_values.empty:
            altitude_accuracy = gps.dropna(subset=["altitude", "accuracy"]).copy()
            if not altitude_accuracy.empty:
                combo = (
                    alt.Chart(altitude_accuracy)
                    .mark_circle(size=95, opacity=0.82, color="#8b5cf6", stroke="#f8fbff", strokeWidth=0.6)
                    .encode(
                        x=alt.X("altitude:Q", title="Altitude"),
                        y=alt.Y("accuracy:Q", title="Accuracy (m)"),
                        tooltip=chart_tooltips,
                    )
                    .properties(height=CHART_HEIGHT, title="Altitude vs GPS Accuracy")
                )
                st.altair_chart(modernize_chart(combo), use_container_width=True)

    st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    st.markdown("### GPS Point Register")
    table = gps.copy()
    table["Latitude"] = table["lat"].round(6)
    table["Longitude"] = table["lon"].round(6)
    table["Altitude (m)"] = pd.to_numeric(table["altitude"], errors="coerce").round(1)
    table["Accuracy (m)"] = pd.to_numeric(table["accuracy"], errors="coerce").round(1)
    display_columns = ["Point", "Source Row", "Latitude", "Longitude", "Altitude (m)", "Accuracy (m)", "Accuracy Band"]
    display_columns.extend(
        [
            column
            for column in ["GPS Time", "Visit Date", "Reviewer", "Region", "Province", "District", "Village", "Surveyor", "Surveyor ID", "TPM_TLS_ID", "Class ID", "Class Type", "School"]
            if column in table.columns
        ]
    )
    st.dataframe(table[display_columns], use_container_width=True, hide_index=True, height=420)


def render_submission_timeline(dataframe: pd.DataFrame) -> None:
    date_column = first_existing_column(dataframe, ["SubmissionDate", "starttime", "Date_And_Time", "Survey_Date"])
    if not date_column:
        st.info("No submission date column is available for a timeline.")
        return
    dates = parse_datetime_series(dataframe[date_column]).dropna()
    if dates.empty:
        st.info("No valid submission dates are available.")
        return
    work = pd.DataFrame({"Date": dates.dt.date.astype(str)}, index=dates.index)
    province_column = first_existing_column(dataframe, ["Province", "Region"])
    if province_column:
        work["Group"] = dataframe.loc[work.index, province_column].fillna("Unspecified").astype(str).str.strip().replace("", "Unspecified")
    else:
        work["Group"] = "Submissions"
    grouped = work.groupby(["Date", "Group"]).size().reset_index(name="Count")
    chart = (
        alt.Chart(grouped)
        .mark_area(interpolate="monotone", opacity=0.72, line=True)
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Count:Q", stack="zero", title="Rows"),
            color=alt.Color("Group:N", scale=alt.Scale(range=PALETTE), legend=alt.Legend(title=None)),
            tooltip=["Date:T", "Group:N", alt.Tooltip("Count:Q", format=",")],
        )
        .properties(height=CHART_HEIGHT, title="Submission Timeline by Geography")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_category_heatmap(dataframe: pd.DataFrame, row_candidates: list[str], column_candidates: list[str], title: str) -> None:
    row_column = first_existing_column(dataframe, row_candidates)
    column_column = first_existing_column(dataframe, column_candidates)
    if not row_column or not column_column or row_column == column_column:
        st.info(f"No valid fields are available for `{title}`.")
        return
    work = dataframe[[row_column, column_column]].copy()
    work[row_column] = work[row_column].fillna("").astype(str).str.strip()
    work[column_column] = work[column_column].fillna("").astype(str).str.strip()
    work = work[(work[row_column] != "") & (work[column_column] != "")]
    if work.empty:
        st.info(f"No valid records are available for `{title}`.")
        return
    top_rows = work[row_column].value_counts().head(16).index
    top_cols = work[column_column].value_counts().head(16).index
    work = work[work[row_column].isin(top_rows) & work[column_column].isin(top_cols)]
    chart_data = work.groupby([row_column, column_column]).size().reset_index(name="Count")
    chart = (
        alt.Chart(chart_data)
        .mark_rect(cornerRadius=4)
        .encode(
            x=alt.X(f"{column_column}:N", title=None, axis=alt.Axis(labelAngle=-28)),
            y=alt.Y(f"{row_column}:N", title=None),
            color=alt.Color("Count:Q", scale=alt.Scale(scheme="viridis"), legend=alt.Legend(title="Rows")),
            tooltip=[row_column, column_column, alt.Tooltip("Count:Q", format=",")],
        )
        .properties(height=440, title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def build_row_completeness(dataframe: pd.DataFrame, schema: dict[str, Any]) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame({"Row Completeness %": pd.Series(dtype=float)}, index=dataframe.index)
    required_columns = [
        column
        for field in schema["fields"]
        if field["required"]
        for column in [column_for_field(dataframe, field)]
        if column
    ]
    if not required_columns:
        required_columns = dataframe.columns.tolist()
    if not required_columns:
        return pd.DataFrame(columns=["Row Completeness %"])
    filled_matrix = dataframe[required_columns].fillna("").astype(str).apply(lambda column: column.str.strip().ne(""))
    completeness = filled_matrix.mean(axis=1) * 100
    return pd.DataFrame({"Row Completeness %": completeness.round(1)}, index=dataframe.index)


def render_completeness_by_group(dataframe: pd.DataFrame, schema: dict[str, Any]) -> None:
    group_column = first_existing_column(dataframe, ["Province", "District", "Surveyor_Name", "username"])
    if not group_column:
        st.info("No grouping field is available for completeness by group.")
        return
    completeness = build_row_completeness(dataframe, schema)
    if completeness.empty:
        st.info("No completeness signal is available.")
        return
    work = pd.DataFrame(
        {
            "Group": dataframe[group_column].fillna("").astype(str).str.strip().replace("", "Unspecified"),
            "Row Completeness %": completeness["Row Completeness %"],
        }
    )
    chart_data = work.groupby("Group").agg(**{"Average Completeness %": ("Row Completeness %", "mean"), "Rows": ("Row Completeness %", "size")}).reset_index()
    chart_data = chart_data.sort_values(["Average Completeness %", "Rows"], ascending=[True, False]).head(18)
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=8, cornerRadiusBottomRight=8, color="#22c55e", opacity=0.84)
        .encode(
            x=alt.X("Average Completeness %:Q", title="Average required completeness", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("Group:N", sort="x", title=None),
            tooltip=["Group:N", alt.Tooltip("Average Completeness %:Q", format=".1f"), alt.Tooltip("Rows:Q", format=",")],
        )
        .properties(height=430, title=f"Required Completeness by {group_column}")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_numeric_correlation_heatmap(dataframe: pd.DataFrame, schema: dict[str, Any]) -> None:
    numeric_columns: list[str] = []
    for field in schema["fields"]:
        if field["type"] not in {"integer", "decimal", "range"}:
            continue
        column = column_for_field(dataframe, field)
        if column and pd.to_numeric(dataframe[column], errors="coerce").nunique(dropna=True) > 1:
            numeric_columns.append(column)
    numeric_columns = numeric_columns[:16]
    if len(numeric_columns) < 3 or len(dataframe) < 3:
        st.info("Not enough numeric variation is available for a correlation heatmap.")
        return
    numeric = dataframe[numeric_columns].apply(pd.to_numeric, errors="coerce")
    corr = numeric.corr().round(2).reset_index().melt(id_vars="index", var_name="Column B", value_name="Correlation").rename(columns={"index": "Column A"})
    corr = corr.dropna()
    if corr.empty:
        st.info("No numeric correlations are available.")
        return
    chart = (
        alt.Chart(corr)
        .mark_rect(cornerRadius=4)
        .encode(
            x=alt.X("Column B:N", title=None, axis=alt.Axis(labelAngle=-35)),
            y=alt.Y("Column A:N", title=None),
            color=alt.Color("Correlation:Q", scale=alt.Scale(domain=[-1, 0, 1], range=["#ef4444", "#0f172a", "#22c55e"]), legend=alt.Legend(title="r")),
            tooltip=["Column A:N", "Column B:N", alt.Tooltip("Correlation:Q", format=".2f")],
        )
        .properties(height=520, title="Numeric Correlation Heatmap")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_gender_pair_chart(dataframe: pd.DataFrame) -> None:
    rows: list[dict[str, Any]] = []
    lookup = {normalize_key(column): column for column in dataframe.columns}
    for column in dataframe.columns:
        key = normalize_key(column)
        if not key.endswith("male"):
            continue
        female_key = key[: -len("male")] + "female"
        female_column = lookup.get(female_key)
        if not female_column:
            continue
        label = re.sub(r"[_-]+", " ", column[:-4]).strip().title() or column
        male_total = pd.to_numeric(dataframe[column], errors="coerce").fillna(0).sum()
        female_total = pd.to_numeric(dataframe[female_column], errors="coerce").fillna(0).sum()
        if male_total == 0 and female_total == 0:
            continue
        rows.extend(
            [
                {"Indicator": label, "Gender": "Male", "Total": male_total},
                {"Indicator": label, "Gender": "Female", "Total": female_total},
            ]
        )
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("No male/female paired indicators are available.")
        return
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=7, cornerRadiusTopRight=7)
        .encode(
            x=alt.X("Indicator:N", title=None, axis=alt.Axis(labelAngle=-24)),
            y=alt.Y("Total:Q", title="Total"),
            color=alt.Color("Gender:N", scale=alt.Scale(domain=["Male", "Female"], range=["#2563eb", "#f97316"]), legend=alt.Legend(title=None)),
            tooltip=["Indicator:N", "Gender:N", alt.Tooltip("Total:Q", format=",")],
        )
        .properties(height=420, title="Gender-Paired Numeric Indicators")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_multi_select_signal_mix(dataframe: pd.DataFrame, schema: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    for field in schema["fields"]:
        if field["type"] != "select_multiple":
            continue
        column = column_for_field(dataframe, field)
        if not column:
            continue
        counts = count_multiple_choice(dataframe, column, field, schema, limit=8)
        for _, row in counts.iterrows():
            rows.append({"Question": short_label(field["label"], 40), "Response": row["Response"], "Count": int(row["Count"])})
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("No select-multiple signals are available.")
        return
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=7, cornerRadiusBottomRight=7)
        .encode(
            x=alt.X("Count:Q", title="Selections"),
            y=alt.Y("Response:N", sort="-x", title=None),
            color=alt.Color("Question:N", scale=alt.Scale(range=PALETTE), legend=alt.Legend(title=None)),
            tooltip=["Question:N", "Response:N", alt.Tooltip("Count:Q", format=",")],
        )
        .properties(height=480, title="Multi-Select Response Signals")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_column_visual(dataframe: pd.DataFrame, column: str, schema: dict[str, Any]) -> None:
    field = schema_field_for_column(column, schema)
    column_type = field["type"] if field else infer_type(dataframe[column])
    label = field["label"] if field else column
    values = dataframe[column].fillna("").astype(str).str.strip()
    filled = values[values != ""]
    if filled.empty or filled.nunique() <= 1:
        return
    if is_media_or_audit_column(column) or (is_identifier_column(column) and column_type not in {"select_one", "select_multiple"}):
        return
    if column_type in {"text", "barcode"} and filled.nunique() > LOW_VALUE_TEXT_MAX_UNIQUE:
        return
    if column_type == "select_multiple":
        render_bar_chart(count_multiple_choice(dataframe, column, field, schema), "Response", label, "#8b5cf6")
    elif column_type == "select_one":
        counts = count_single_choice(dataframe, column, field, schema)
        if len(counts) <= 8:
            render_donut_chart(counts, "Response", label)
        else:
            render_bar_chart(counts, "Response", label, "#2563eb")
    elif column_type in {"integer", "decimal", "range"}:
        render_numeric_chart(dataframe, column, label)
    elif column_type in {"date", "datetime", "start", "end"}:
        render_date_chart(dataframe, column, label)
    else:
        counts = top_counts(dataframe, column, 20)
        render_bar_chart(counts, column, label, "#0f766e")


def required_completeness(profile: pd.DataFrame) -> pd.DataFrame:
    required = profile[profile["Required"]].copy()
    if required.empty:
        return profile.sort_values("Completeness %").head(20)
    return required.sort_values("Completeness %").head(30)


def build_quality_diagnostics(dataframe: pd.DataFrame, profile: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if profile.empty:
        return pd.DataFrame(columns=["Signal", "Column", "Value"])

    for _, row in profile.iterrows():
        column = str(row["Column"])
        missing = int(row["Missing"])
        completeness = float(row["Completeness %"])
        unique_values = int(row["Unique Values"])
        if missing > 0:
            rows.append({"Signal": "Missing values", "Column": column, "Value": missing})
        if unique_values <= 1 and len(dataframe) > 1:
            rows.append({"Signal": "Constant field", "Column": column, "Value": unique_values})
        if completeness < 100 and bool(row["Required"]):
            rows.append({"Signal": "Required incomplete", "Column": column, "Value": round(100 - completeness, 1)})

    key_column = first_existing_column(dataframe, ["KEY", "_uuid", "uuid", "instanceid", "InstanceID"])
    if key_column:
        duplicate_count = int(dataframe[key_column].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().duplicated().sum())
        if duplicate_count:
            rows.append({"Signal": "Duplicate key", "Column": key_column, "Value": duplicate_count})

    return pd.DataFrame(rows, columns=["Signal", "Column", "Value"])


def build_missingness_matrix(profile: pd.DataFrame) -> pd.DataFrame:
    if profile.empty:
        return pd.DataFrame(columns=["Column", "Metric", "Percent"])
    work = profile[["Column", "Completeness %"]].copy()
    work["Missing %"] = 100 - pd.to_numeric(work["Completeness %"], errors="coerce").fillna(0)
    return work.sort_values("Missing %", ascending=False).head(30).melt(
        id_vars=["Column"],
        value_vars=["Completeness %", "Missing %"],
        var_name="Metric",
        value_name="Percent",
    )


def render_missingness_chart(profile: pd.DataFrame) -> None:
    chart_data = build_missingness_matrix(profile)
    if chart_data.empty:
        st.info("No missingness profile is available.")
        return
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=7, cornerRadiusBottomRight=7)
        .encode(
            x=alt.X("Percent:Q", title="Percent", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("Column:N", sort="-x", title=None),
            color=alt.Color("Metric:N", scale=alt.Scale(domain=["Completeness %", "Missing %"], range=["#22c55e", "#ef4444"]), legend=alt.Legend(title=None)),
            tooltip=["Column:N", "Metric:N", alt.Tooltip("Percent:Q", format=".1f")],
        )
        .properties(height=520, title="Completeness and Missingness by Column")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_clean_rejected_stack(summary: pd.DataFrame) -> None:
    if summary.empty or not {"Dataset", "Rows", "Rejected Excluded"}.issubset(summary.columns):
        st.info("No clean/rejected summary is available.")
        return
    chart_data = summary[["Dataset", "Rows", "Rejected Excluded"]].rename(columns={"Rows": "Clean Rows"})
    chart_data = chart_data.melt(id_vars=["Dataset"], value_vars=["Clean Rows", "Rejected Excluded"], var_name="Metric", value_name="Rows")
    chart_data = chart_data[chart_data["Rows"] > 0]
    if chart_data.empty:
        st.info("No clean/rejected row mix is available.")
        return
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=7, cornerRadiusTopRight=7)
        .encode(
            x=alt.X("Dataset:N", title=None, axis=alt.Axis(labelAngle=-22)),
            y=alt.Y("Rows:Q", title="Rows"),
            color=alt.Color("Metric:N", scale=alt.Scale(domain=["Clean Rows", "Rejected Excluded"], range=["#22c55e", "#ef4444"]), legend=alt.Legend(title=None)),
            tooltip=["Dataset:N", "Metric:N", alt.Tooltip("Rows:Q", format=",")],
        )
        .properties(height=390, title="Clean Data vs Rejected Exclusions")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_coverage_bubble(summary: pd.DataFrame) -> None:
    if summary.empty or not {"Rows", "Schema Coverage %", "Columns", "Detected Tool"}.issubset(summary.columns):
        st.info("No detection coverage summary is available.")
        return
    chart_data = summary.copy()
    chart_data["Rows"] = pd.to_numeric(chart_data["Rows"], errors="coerce").fillna(0)
    chart_data["Schema Coverage %"] = pd.to_numeric(chart_data["Schema Coverage %"], errors="coerce").fillna(0)
    chart_data["Columns"] = pd.to_numeric(chart_data["Columns"], errors="coerce").fillna(0)
    chart = (
        alt.Chart(chart_data)
        .mark_circle(opacity=0.82, stroke="#f8fbff", strokeWidth=0.8)
        .encode(
            x=alt.X("Rows:Q", title="Clean rows"),
            y=alt.Y("Schema Coverage %:Q", title="Schema coverage", scale=alt.Scale(domain=[0, 100])),
            size=alt.Size("Columns:Q", title="Columns", scale=alt.Scale(range=[160, 1800])),
            color=alt.Color("Detected Tool:N", scale=alt.Scale(range=PALETTE), legend=alt.Legend(title=None)),
            tooltip=["Dataset:N", "Detected Tool:N", alt.Tooltip("Rows:Q", format=","), alt.Tooltip("Rejected Excluded:Q", format=","), alt.Tooltip("Schema Coverage %:Q", format=".1f")],
        )
        .properties(height=390, title="Dataset Detection Quality Map")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def build_dataset_summary_row(source_name: str, sheet_name: str, dataframe: pd.DataFrame, schemas: dict[str, dict[str, Any]], raw_rows: int | None = None) -> dict[str, Any]:
    detected_tool, scorecard = detect_tool(dataframe, source_name, schemas)
    matched = 0
    coverage = 0.0
    form_title = ""
    if detected_tool:
        best_row = scorecard.iloc[0]
        matched = int(best_row["Matched Fields"])
        coverage = float(best_row["Coverage %"])
        form_title = str(best_row["Form Title"])
    return {
        "Dataset": source_name,
        "Sheet": sheet_name,
        "Detected Tool": detected_tool or "Unknown",
        "Form Title": form_title,
        "Raw Rows": raw_rows if raw_rows is not None else len(dataframe),
        "Rows": len(dataframe),
        "Rejected Excluded": max((raw_rows if raw_rows is not None else len(dataframe)) - len(dataframe), 0),
        "Columns": len(dataframe.columns),
        "Matched Fields": matched,
        "Schema Coverage %": coverage,
    }


def render_dataset_analysis(source_name: str, sheet_name: str, dataset: pd.DataFrame, schemas: dict[str, dict[str, Any]], widget_key: str, raw_rows: int | None = None) -> None:
    if not schemas:
        schemas = {"Generic": build_generic_schema(dataset, "Auto schema (no XLSForm)")}

    detected_tool, detection_scorecard = detect_tool(dataset, source_name, schemas)
    if detected_tool is None:
        st.error(f"`{source_name}` could not be matched to Tool 2, Tool 3, or Tool 5.")
        st.dataframe(detection_scorecard, use_container_width=True, hide_index=True)
        return

    tool_keys = list(schemas.keys())
    selected_tool = st.selectbox(
        "Detected tool",
        tool_keys,
        index=tool_keys.index(detected_tool),
        key=f"{widget_key}-tool",
    )
    schema = schemas[selected_tool]
    filtered = dataset.copy()
    rejected_excluded = max((raw_rows if raw_rows is not None else len(dataset)) - len(dataset), 0)

    filter_columns = [
        first_existing_column(dataset, ["Region"]),
        first_existing_column(dataset, ["Province"]),
        first_existing_column(dataset, ["District"]),
        first_existing_column(dataset, ["Surveyor_Name", "Surveyor Name", "username"]),
        first_existing_column(dataset, ["TPM_ECE_ID", "TPM_TLS_ID"]),
    ]
    filter_columns = [column for column in dict.fromkeys(filter_columns) if column]
    filter_controls = st.columns(min(max(len(filter_columns), 1), 5), gap="large")
    for index, column in enumerate(filter_columns[:5]):
        values = sorted([value for value in dataset[column].fillna("").astype(str).str.strip().unique().tolist() if value])
        if not values:
            continue
        selected = filter_controls[index].multiselect(column, values, default=[], key=f"{widget_key}-filter-{normalize_key(column)}")
        if selected:
            filtered = filtered[filtered[column].astype(str).str.strip().isin(selected)]

    profile = profile_columns(filtered, schema)
    matched_columns = int(profile["Covered by XLSForm"].sum()) if not profile.empty else 0
    required_profile = profile[profile["Required"]]
    required_complete = round(required_profile["Completeness %"].mean(), 1) if not required_profile.empty else 0
    schema_coverage = round((matched_columns / len(schema["fields"])) * 100, 1) if schema["fields"] else 0
    missing_cells = int(profile["Missing"].sum()) if not profile.empty else 0

    metric_cols = st.columns(4, gap="large")
    with metric_cols[0]:
        render_metric_card("Detected Tool", selected_tool, schema["form_title"], "#38bdf8")
    with metric_cols[1]:
        render_metric_card("Clean Rows", f"{len(filtered):,}", f"Rejected excluded: {rejected_excluded:,}. Sheet: {sheet_name}.", "#22c55e")
    with metric_cols[2]:
        render_metric_card("Schema Coverage", f"{schema_coverage:.1f}%", f"{matched_columns:,} columns matched XLSForm fields.", "#8b5cf6")
    with metric_cols[3]:
        render_metric_card("Missing Cells", f"{missing_cells:,}", f"Required completeness average: {required_complete:.1f}%.", "#f97316")

    st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    tabs = st.tabs(["Executive View", "Insight Lab", "Smart Visuals", "All Columns", "Data Quality", "Tool Schema"])

    with tabs[0]:
        if selected_tool == "Tool 5":
            render_tool5_tpm_duplicate_chart(filtered)
            tool5_left, tool5_right = st.columns(2, gap="large")
            with tool5_left:
                render_tool5_returnee_zone_province_chart(filtered)
            with tool5_right:
                render_tool5_returnee_climate_chart(filtered)
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        overview_left, overview_right = st.columns(2, gap="large")
        with overview_left:
            if selected_tool != "Tool 5":
                render_bar_chart(required_completeness(profile), "Column", "Required Field Completeness", "#22c55e", value_column="Completeness %")
        with overview_right:
            type_mix = profile.groupby("Type").size().reset_index(name="Count").sort_values("Count", ascending=False)
            render_donut_chart(type_mix, "Type", "Column Type Mix")

        st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
        geo_left, geo_right = st.columns(2, gap="large")
        province_col = first_existing_column(filtered, ["Province"])
        district_col = first_existing_column(filtered, ["District"])
        surveyor_col = first_existing_column(filtered, ["Surveyor_Name", "Surveyor Name", "username"])
        with geo_left:
            if province_col:
                render_bar_chart(top_counts(filtered, province_col, 15), province_col, "Rows by Province", "#2563eb")
            elif surveyor_col:
                render_bar_chart(top_counts(filtered, surveyor_col, 15), surveyor_col, "Rows by Surveyor", "#8b5cf6")
            else:
                st.info("No province or surveyor column was found.")
        with geo_right:
            if district_col:
                render_bar_chart(top_counts(filtered, district_col, 15), district_col, "Rows by District", "#f97316")
            else:
                st.info("District column was not found.")

        st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
        smart_column_set = set(visualizable_columns(profile))
        priority_fields = []
        for field in schema["fields"]:
            column = column_for_field(filtered, field)
            if field["type"] in {"select_one", "select_multiple", "integer", "decimal", "date"} and column in smart_column_set:
                priority_fields.append(field)
        for offset in range(0, min(len(priority_fields), 8), 2):
            left, right = st.columns(2, gap="large")
            with left:
                column = column_for_field(filtered, priority_fields[offset])
                if column:
                    render_column_visual(filtered, column, schema)
            if offset + 1 < min(len(priority_fields), 8):
                with right:
                    column = column_for_field(filtered, priority_fields[offset + 1])
                    if column:
                        render_column_visual(filtered, column, schema)

        st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
        combo_left, combo_right = st.columns(2, gap="large")
        with combo_left:
            render_standards_matrix(filtered, schema)
        with combo_right:
            render_numeric_combo_chart(filtered, schema)

    with tabs[1]:
        lab_top_left, lab_top_right = st.columns(2, gap="large")
        with lab_top_left:
            render_submission_timeline(filtered)
        with lab_top_right:
            render_completeness_by_group(filtered, schema)

        st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
        lab_mid_left, lab_mid_right = st.columns(2, gap="large")
        with lab_mid_left:
            render_category_heatmap(
                filtered,
                ["Province", "Region", "District"],
                ["Surveyor_Name", "username", "District"],
                "Field Activity Heatmap",
            )
        with lab_mid_right:
            render_multi_select_signal_mix(filtered, schema)

        st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
        lab_bottom_left, lab_bottom_right = st.columns(2, gap="large")
        with lab_bottom_left:
            render_numeric_correlation_heatmap(filtered, schema)
        with lab_bottom_right:
            render_gender_pair_chart(filtered)

    with tabs[2]:
        smart_columns = visualizable_columns(profile)
        scope = st.radio(
            "Visualization scope",
            ["All meaningful columns", "Important first", "Manual selection"],
            horizontal=True,
            key=f"{widget_key}-scope",
        )
        if scope == "All meaningful columns":
            selected_columns = smart_columns
        elif scope == "Important first":
            selected_columns = smart_columns[:MAX_AUTO_VISUALS]
        else:
            selected_columns = st.multiselect("Columns to visualize", smart_columns, default=smart_columns[:MAX_AUTO_VISUALS], key=f"{widget_key}-columns")

        if not selected_columns:
            st.info("No meaningful columns are available for smart visualization after filtering.")
        for offset in range(0, len(selected_columns), 2):
            left, right = st.columns(2, gap="large")
            with left:
                render_column_visual(filtered, selected_columns[offset], schema)
            if offset + 1 < len(selected_columns):
                with right:
                    render_column_visual(filtered, selected_columns[offset + 1], schema)

    with tabs[3]:
        st.markdown("### Complete Column Coverage")
        st.dataframe(profile, use_container_width=True, hide_index=True, height=520)
        st.markdown("### Source Data Preview")
        st.dataframe(filtered.head(250), use_container_width=True, hide_index=True, height=360)
        missing_schema_columns = [
            field["name"]
            for field in schema["fields"]
            if field["name_key"] not in {normalize_key(column) for column in filtered.columns}
        ]
        if missing_schema_columns:
            st.markdown("### XLSForm Fields Not Found In Dataset")
            st.dataframe(pd.DataFrame({"Missing XLSForm Field": missing_schema_columns}), use_container_width=True, hide_index=True, height=260)

    with tabs[4]:
        quality_diagnostics = build_quality_diagnostics(filtered, profile)
        quality_left, quality_right = st.columns(2, gap="large")
        with quality_left:
            render_missingness_chart(profile)
        with quality_right:
            if quality_diagnostics.empty:
                st.info("No missing, constant, duplicate, or required-field issues were detected.")
            else:
                signal_mix = quality_diagnostics.groupby("Signal").size().reset_index(name="Count")
                render_donut_chart(signal_mix, "Signal", "Data Quality Signals")

        st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
        st.markdown("### Data Quality Detail")
        if quality_diagnostics.empty:
            st.info("No data quality diagnostics are available.")
        else:
            st.dataframe(quality_diagnostics, use_container_width=True, hide_index=True, height=420)

        unmatched_columns = profile[~profile["Covered by XLSForm"]].copy()
        if not unmatched_columns.empty:
            st.markdown("### Dataset Columns Not Matched To XLSForm")
            st.dataframe(
                unmatched_columns[["Column", "Type", "Filled", "Missing", "Completeness %", "Unique Values"]],
                use_container_width=True,
                hide_index=True,
                height=300,
            )

    with tabs[5]:
        st.markdown("### Tool Detection Scorecard")
        st.dataframe(detection_scorecard, use_container_width=True, hide_index=True)
        st.markdown("### XLSForm Question Dictionary")
        dictionary = pd.DataFrame(schema["fields"])[["name", "label", "type", "type_raw", "choice_list", "required", "relevance"]]
        st.dataframe(dictionary, use_container_width=True, hide_index=True, height=560)


apply_liquid_glass_theme(
    "Data Visualization Studio",
    "The dashboard auto-loads datasets and XLSForm schemas from Google Drive and builds complete chart coverage for every column.",
    accent="#38bdf8",
    compact_hero=True,
)

schemas = load_all_schemas()
if not schemas:
    st.error(
        "XLSForm schemas could not be loaded from Google Drive. "
        "Please verify Google Drive API, file sharing permissions, and the configured file links."
    )
    st.stop()

render_glass_section(
    "Dataset Source",
    "Datasets and XLSForm schemas are loaded automatically from Google Drive.",
)

dataset_records: list[dict[str, Any]] = []
processing_errors: list[str] = []

for dataset_key in GOOGLE_DRIVE_DATASET_KEYS:
    try:
        dataset_folder_id = str(st.secrets.get("GOOGLE_DRIVE_DATASET_FOLDER_ID", "")).strip() or get_drive_folder_id() or DATASET_FOLDER_DEFAULT_ID
        sheets = read_drive_sheets_by_name(dataset_key, dataset_folder_id)
        source_file_name = dataset_key
        sheet_name = default_sheet_name(sheets)
        raw_dataframe = sheets[sheet_name].copy().dropna(how="all")
        dataset_records.append(
            {
                "source_name": source_file_name,
                "display_name": dataset_key.rsplit(".", 1)[0],
                "sheet_name": sheet_name,
                "raw_rows": len(raw_dataframe),
                "dataframe": prepare_dataset(raw_dataframe),
            }
        )
    except Exception as exc:
        processing_errors.append(f"{dataset_key}: {exc}")

if processing_errors:
    st.warning("Some datasets could not be processed: " + " | ".join(processing_errors))

if not dataset_records:
    schema_rows = [
        {
            "Tool": tool_key,
            "Form Title": schema["form_title"],
            "Form ID": schema["form_id"],
            "Fields": len(schema["fields"]),
            "Choice Lists": len(schema["choice_labels"]),
        }
        for tool_key, schema in schemas.items()
    ]
    st.error("No datasets were loaded from Google Drive. Check folder access, file names, and service-account permissions.")
    st.dataframe(pd.DataFrame(schema_rows), use_container_width=True, hide_index=True)
    st.stop()

summary_rows = [
    build_dataset_summary_row(record["source_name"], record["sheet_name"], record["dataframe"], schemas, record.get("raw_rows"))
    for record in dataset_records
]
summary = pd.DataFrame(summary_rows)

portfolio_metrics = st.columns(4, gap="large")
with portfolio_metrics[0]:
    render_metric_card("Datasets", f"{len(dataset_records):,}", "Loaded datasets ready for analysis.", "#38bdf8")
with portfolio_metrics[1]:
    render_metric_card("Clean Rows", f"{int(summary['Rows'].sum()):,}", "Rejected rows are excluded from visualization.", "#22c55e")
with portfolio_metrics[2]:
    render_metric_card("Rejected Excluded", f"{int(summary['Rejected Excluded'].sum()):,}", "Rows removed before charts and analysis.", "#8b5cf6")
with portfolio_metrics[3]:
    render_metric_card("Avg Coverage", f"{float(summary['Schema Coverage %'].mean()):.1f}%", "Average XLSForm schema match.", "#f97316")

st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)

tab_labels = ["All Datasets"] + [record["display_name"] for record in dataset_records]
dataset_tabs = st.tabs(tab_labels)

with dataset_tabs[0]:
    left, right = st.columns(2, gap="large")
    with left:
        render_bar_chart(summary.rename(columns={"Rows": "Count"}), "Dataset", "Rows by Dataset", "#38bdf8")
    with right:
        tool_mix = summary.groupby("Detected Tool")["Rows"].sum().reset_index(name="Count")
        render_donut_chart(tool_mix, "Detected Tool", "Detected Tool Mix")

    st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    portfolio_left, portfolio_right = st.columns(2, gap="large")
    with portfolio_left:
        render_clean_rejected_stack(summary)
    with portfolio_right:
        render_coverage_bubble(summary)

    st.markdown("<div style='height: 34px;'></div>", unsafe_allow_html=True)
    st.markdown("### Dataset Detection Summary")
    st.dataframe(summary, use_container_width=True, hide_index=True, height=300)

for index, record in enumerate(dataset_records, start=1):
    with dataset_tabs[index]:
        render_glass_section(
            record["display_name"],
            f"Source file: {record['source_name']} | Sheet: {record['sheet_name']}",
        )
        render_dataset_analysis(
            record["source_name"],
            record["sheet_name"],
            record["dataframe"],
            schemas,
            f"dataset-{index}",
            record.get("raw_rows"),
        )
