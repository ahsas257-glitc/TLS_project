import re
from io import BytesIO

import pandas as pd
import streamlit as st

from services.google_sheets import (
    append_dataframe_to_worksheet,
    GoogleSheetsConnectionError,
    get_worksheet_column_values,
    update_summary_timestamp,
)
from services.ui_theme import apply_liquid_glass_theme, render_glass_section


TARGET_WORKSHEET = "QA_Log"
TARGET_COLUMNS = [
    "KEY",
    "Tool Name",
    "Province",
    "District",
    "Village",
    "PB_Name",
    "TPM-ID (ECE, TLS)",
    "Surveyor_Name",
    "Survey_Date",
]
SOURCE_COLUMN_CANDIDATES = {
    "KEY": ["KEY", "key", "_uuid", "uuid", "instanceid", "InstanceID", "instance_id"],
    "Province": ["Province", "province"],
    "District": ["District", "district"],
    "Village": ["Village", "village"],
    "PB_Name": ["PB_Name", "PB Name", "pb_name", "pbname", "PS_Name", "PS Name", "ps_name", "psname"],
    "TPM_TLS_ID": ["TPM_TLS_ID", "TPM TLS ID", "tpm_tls_id", "tpmtlsid"],
    "TPM_ECE_ID": ["TPM_ECE_ID", "TPM ECE ID", "tpm_ece_id", "tpmeceid"],
    "Surveyor_Name": ["Surveyor_Name", "Surveyor Name", "surveyor_name", "enumerator", "Enumerator", "username"],
    "starttime": ["starttime", "Start Time", "start_time", "submissiondate", "SubmissionDate"],
}


def to_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def read_uploaded_file(uploaded_file) -> pd.DataFrame:
    return read_uploaded_file_bytes(uploaded_file.name, uploaded_file.getvalue())


@st.cache_data(ttl=180, show_spinner=False)
def read_uploaded_file_bytes(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    file_name = file_name.lower()
    buffer = BytesIO(file_bytes)
    if file_name.endswith(".csv"):
        return pd.read_csv(buffer)
    if file_name.endswith(".xlsx") or file_name.endswith(".xls"):
        return pd.read_excel(buffer)
    raise ValueError("Only CSV and Excel files are supported.")


def normalize_column_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def resolve_column_name(dataframe: pd.DataFrame, logical_name: str) -> str | None:
    normalized_map = {
        normalize_column_name(column): column
        for column in dataframe.columns
    }

    for candidate in SOURCE_COLUMN_CANDIDATES.get(logical_name, [logical_name]):
        normalized_candidate = normalize_column_name(candidate)
        if normalized_candidate in normalized_map:
            return normalized_map[normalized_candidate]
    return None


def get_column_series(dataframe: pd.DataFrame, logical_name: str) -> pd.Series:
    column_name = resolve_column_name(dataframe, logical_name)
    if column_name is None:
        return pd.Series([""] * len(dataframe), index=dataframe.index, dtype="object")
    return dataframe[column_name]


def extract_tool_name(file_name: str) -> str:
    match = re.search(r"(Tool\s*\d+)", file_name, flags=re.IGNORECASE)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).title()
    return file_name.rsplit(".", 1)[0]


def build_tpm_id(series: pd.Series) -> str:
    parts = []
    for column_name in ["TPM_TLS_ID", "TPM_ECE_ID"]:
        value = to_text(series.get(column_name, ""))
        if value:
            parts.append(value)
    return " - ".join(parts)


def format_survey_date(value) -> str:
    if pd.isna(value) or str(value).strip() == "":
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value).strip()
    return parsed.strftime("%Y-%m-%d")


def transform_dataset(dataframe: pd.DataFrame, file_name: str) -> pd.DataFrame:
    transformed = pd.DataFrame()
    transformed["KEY"] = get_column_series(dataframe, "KEY").map(to_text)
    transformed["Tool Name"] = extract_tool_name(file_name)
    transformed["Province"] = get_column_series(dataframe, "Province").map(to_text)
    transformed["District"] = get_column_series(dataframe, "District").map(to_text)
    transformed["Village"] = get_column_series(dataframe, "Village").map(to_text)
    transformed["PB_Name"] = get_column_series(dataframe, "PB_Name").map(to_text)
    transformed["TPM_TLS_ID"] = get_column_series(dataframe, "TPM_TLS_ID").map(to_text)
    transformed["TPM_ECE_ID"] = get_column_series(dataframe, "TPM_ECE_ID").map(to_text)
    transformed["TPM-ID (ECE, TLS)"] = transformed.apply(build_tpm_id, axis=1)
    transformed["Surveyor_Name"] = get_column_series(dataframe, "Surveyor_Name").map(to_text)
    transformed["Survey_Date"] = get_column_series(dataframe, "starttime").apply(format_survey_date)
    return transformed[TARGET_COLUMNS]


def merge_tpm_values(left: str, right: str) -> str:
    values: list[str] = []
    for part in [left, right]:
        text = to_text(part)
        if not text:
            continue
        for item in [segment.strip() for segment in text.split(" - ")]:
            if item and item not in values:
                values.append(item)
    return " - ".join(values)


def merge_tool_names(left: str, right: str) -> str:
    values: list[str] = []
    for part in [left, right]:
        text = to_text(part)
        if not text:
            continue
        for item in [segment.strip() for segment in text.split(",")]:
            if item and item not in values:
                values.append(item)
    return ", ".join(values)


def consolidate_uploaded_rows(transformed_datasets: list[tuple[str, pd.DataFrame]]) -> pd.DataFrame:
    ordered_rows: list[dict[str, str]] = []
    key_index: dict[str, int] = {}

    for _, transformed in transformed_datasets:
        for _, row in transformed.iterrows():
            key = to_text(row.get("KEY", ""))
            if not key:
                continue

            row_data = {column: to_text(row.get(column, "")) for column in TARGET_COLUMNS}

            if key not in key_index:
                key_index[key] = len(ordered_rows)
                ordered_rows.append(row_data)
                continue

            existing = ordered_rows[key_index[key]]
            for column in TARGET_COLUMNS:
                incoming_value = row_data[column]
                existing_value = existing.get(column, "")

                if column == "KEY":
                    continue
                if column == "Tool Name":
                    existing[column] = merge_tool_names(existing_value, incoming_value)
                    continue
                if column == "TPM-ID (ECE, TLS)":
                    existing[column] = merge_tpm_values(existing_value, incoming_value)
                    continue
                if column == "Survey_Date":
                    existing[column] = existing_value or incoming_value
                    continue

                existing[column] = existing_value or incoming_value

    if not ordered_rows:
        return pd.DataFrame(columns=TARGET_COLUMNS)

    return pd.DataFrame(ordered_rows, columns=TARGET_COLUMNS)


apply_liquid_glass_theme(
    "Google Sheet Updater",
    "Import source files and append only new validated rows into QA_Log.",
    accent="#f59e0b",
)

render_glass_section(
    "Import Workflow",
    "Select source files and append only new keys to QA_Log.",
)

uploaded_files = st.file_uploader(
    "Select one or more files",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True,
)

if uploaded_files:
    transformed_datasets: list[tuple[str, pd.DataFrame]] = []
    processing_errors: list[str] = []

    for uploaded_file in uploaded_files:
        try:
            dataframe = read_uploaded_file(uploaded_file)
            transformed_datasets.append((uploaded_file.name, transform_dataset(dataframe, uploaded_file.name)))
        except Exception as exc:
            processing_errors.append(f"{uploaded_file.name}: {exc}")

    consolidated_rows = consolidate_uploaded_rows(transformed_datasets)

    if not consolidated_rows.empty:
        if st.button(f"Add Data To {TARGET_WORKSHEET}", type="primary"):
            if processing_errors:
                st.error("Some files could not be processed.")
                st.stop()

            try:
                existing_keys = {
                    key.strip()
                    for key in get_worksheet_column_values(TARGET_WORKSHEET, "KEY")
                    if key.strip()
                }
            except GoogleSheetsConnectionError as exc:
                st.error(str(exc))
                st.stop()

            rows_to_add = consolidated_rows[~consolidated_rows["KEY"].isin(existing_keys)].copy()
            total_rows = 0

            if not rows_to_add.empty:
                try:
                    added_rows = append_dataframe_to_worksheet(rows_to_add[TARGET_COLUMNS], TARGET_WORKSHEET)
                    update_summary_timestamp("Summary")
                except GoogleSheetsConnectionError as exc:
                    st.error(str(exc))
                    st.stop()
                total_rows = added_rows
            else:
                total_rows = 0

            if total_rows > 0:
                st.success("The data was added to Google Sheets successfully.")
            else:
                st.warning("No new data was added to Google Sheets.")
    elif processing_errors:
        st.error("The selected files could not be processed.")
else:
    st.info("Upload one or more Excel or CSV files to get started.")
