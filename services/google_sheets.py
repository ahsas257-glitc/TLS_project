from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


class GoogleSheetsConnectionError(RuntimeError):
    pass


def _get_secret_text(key: str) -> str:
    value = st.secrets.get(key, "")
    return str(value).strip()


@st.cache_resource(show_spinner=False)
def get_gspread_client() -> gspread.Client:
    try:
        credentials_info = dict(st.secrets["gcp_service_account"])
    except Exception as exc:
        raise GoogleSheetsConnectionError(
            "Google service account credentials are missing from Streamlit secrets."
        ) from exc

    try:
        credentials = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
        return gspread.authorize(credentials)
    except Exception as exc:
        raise GoogleSheetsConnectionError(
            f"Unable to authorize the Google Sheets client: {exc}"
        ) from exc


@st.cache_resource(show_spinner=False)
def get_workbook():
    client = get_gspread_client()
    spreadsheet_id = _get_secret_text("GOOGLE_SHEET_ID")
    spreadsheet_url = _get_secret_text("GOOGLE_SHEET_URL")
    sheet_name = _get_secret_text("GOOGLE_SHEET_NAME")

    if spreadsheet_id:
        return client.open_by_key(spreadsheet_id)
    if spreadsheet_url:
        return client.open_by_url(spreadsheet_url)
    if sheet_name:
        try:
            return client.open(sheet_name)
        except gspread.exceptions.APIError as exc:
            raise GoogleSheetsConnectionError(
                "Unable to open the spreadsheet by title. Set `GOOGLE_SHEET_ID` or "
                "`GOOGLE_SHEET_URL` in your secrets to avoid the Google Drive API requirement."
            ) from exc

    raise GoogleSheetsConnectionError(
        "Spreadsheet configuration is missing. Add `GOOGLE_SHEET_ID` or `GOOGLE_SHEET_URL` to your secrets."
    )


def get_worksheet(worksheet_name: str | None = None):
    try:
        workbook = get_workbook()
        if worksheet_name:
            return workbook.worksheet(worksheet_name)
        return workbook.sheet1
    except GoogleSheetsConnectionError:
        raise
    except gspread.exceptions.WorksheetNotFound as exc:
        raise GoogleSheetsConnectionError(
            f"The worksheet `{worksheet_name}` was not found in the target spreadsheet."
        ) from exc
    except gspread.exceptions.SpreadsheetNotFound as exc:
        raise GoogleSheetsConnectionError(
            "The target spreadsheet could not be found. Verify that the spreadsheet ID or URL is correct and shared with the service account."
        ) from exc
    except gspread.exceptions.APIError as exc:
        raise GoogleSheetsConnectionError(
            f"Google Sheets API error: {exc}"
        ) from exc
    except Exception as exc:
        raise GoogleSheetsConnectionError(
            f"Unexpected Google Sheets connection error: {exc}"
        ) from exc


@st.cache_data(ttl=120, show_spinner=False)
def load_records() -> pd.DataFrame:
    try:
        worksheet = get_worksheet()
        rows = worksheet.get_all_records()
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=180, show_spinner=False)
def load_worksheet_values(worksheet_name: str) -> list[list[str]]:
    try:
        worksheet = get_worksheet(worksheet_name)
        return worksheet.get_all_values()
    except Exception:
        return []


def append_record(record: dict[str, str], column_order: list[str]) -> None:
    worksheet = get_worksheet()
    row = [record.get(column, "") for column in column_order]
    worksheet.append_row(row)
    clear_google_sheets_caches()


@st.cache_data(ttl=180, show_spinner=False)
def load_worksheet_records(worksheet_name: str) -> pd.DataFrame:
    try:
        worksheet = get_worksheet(worksheet_name)
        rows = worksheet.get_all_records()
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=180, show_spinner=False)
def get_worksheet_headers(worksheet_name: str) -> list[str]:
    worksheet = get_worksheet(worksheet_name)
    values = worksheet.get_all_values()
    if not values:
        return []
    return values[0]


@st.cache_data(ttl=180, show_spinner=False)
def get_worksheet_column_values(worksheet_name: str, column_name: str) -> list[str]:
    worksheet = get_worksheet(worksheet_name)
    values = worksheet.get_all_values()
    if not values:
        return []

    headers = values[0]
    if column_name not in headers:
        return []

    column_index = headers.index(column_name)
    return [
        row[column_index].strip()
        for row in values[1:]
        if len(row) > column_index and str(row[column_index]).strip()
    ]


def append_dataframe_to_worksheet(dataframe: pd.DataFrame, worksheet_name: str) -> int:
    cleaned = dataframe.fillna("").astype(str)
    worksheet = get_worksheet(worksheet_name)
    existing_values = worksheet.get_all_values()

    if not existing_values:
        worksheet.append_row(cleaned.columns.tolist())
        worksheet.append_rows(cleaned.values.tolist())
        clear_google_sheets_caches()
        return len(cleaned)

    headers = existing_values[0]
    aligned = cleaned.reindex(columns=headers, fill_value="")
    worksheet.append_rows(aligned.values.tolist())
    clear_google_sheets_caches()
    return len(aligned)


def update_summary_timestamp(summary_worksheet_name: str = "Summary") -> None:
    worksheet = get_worksheet(summary_worksheet_name)
    now_afghanistan = datetime.now(ZoneInfo("Asia/Kabul"))
    date_value = now_afghanistan.strftime("%Y-%m-%d")
    time_value = now_afghanistan.strftime("%I:%M:%S %p")

    date_range = [["" for _ in range(2)] for _ in range(3)]
    time_range = [["" for _ in range(2)] for _ in range(3)]

    for row_index in range(3):
        for column_index in range(2):
            date_range[row_index][column_index] = date_value
            time_range[row_index][column_index] = time_value

    worksheet.update("L5:M7", date_range)
    worksheet.update("L8:M10", time_range)
    clear_google_sheets_caches()


def clear_google_sheets_caches() -> None:
    load_records.clear()
    load_worksheet_values.clear()
    load_worksheet_records.clear()
    get_worksheet_headers.clear()
    get_worksheet_column_values.clear()
