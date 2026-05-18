from __future__ import annotations

import html
import json
import math
import re
from itertools import combinations
from io import BytesIO
from numbers import Real
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from services.ui_theme import apply_liquid_glass_theme, render_glass_section

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


LOCAL_DATASET_PATHS = {
    "Tool 2 ECE Classroom Observation": Path(r"C:\Users\LENOVO\Desktop\TLS\Tool 2 ECE Classroom Observation.xlsx"),
    "Tool 3 ECE Parent Interview": Path(r"C:\Users\LENOVO\Desktop\TLS\Tool 3 ECE Parent Interview.xlsx"),
    "Tool 5 TLS Classroom Observation": Path(r"C:\Users\LENOVO\Desktop\TLS\Tool 5 TLS Classroom Observation.xlsx"),
}
STATUS_COLUMN_HINTS = {"status", "qastatus", "qcstatus", "reviewstatus", "validationstatus"}
GPS_LATITUDE_CANDIDATES = ["GPS-Latitude", "GPS Latitude", "GPS_Latitude", "latitude", "lat", "Latitude"]
GPS_LONGITUDE_CANDIDATES = ["GPS-Longitude", "GPS Longitude", "GPS_Longitude", "longitude", "lon", "lng", "Longitude"]
GPS_ALTITUDE_CANDIDATES = ["GPS-Altitude", "GPS Altitude", "GPS_Altitude", "altitude", "Altitude"]
GPS_ACCURACY_CANDIDATES = ["GPS-Accuracy", "GPS Accuracy", "GPS_Accuracy", "accuracy", "Accuracy"]
GPS_POINT_CANDIDATES = ["GPS", "gps", "geopoint", "GeoPoint", "GPS Point", "GPS_Point"]
GPS_CONTEXT_CANDIDATES = {
    "GPS Time": ["Date_And_Time", "starttime", "SubmissionDate", "endtime"],
    "Start Time": ["starttime", "start_time", "Start_Time"],
    "End Time": ["endtime", "end_time", "End_Time"],
    "Submission Time": ["SubmissionDate", "submission_date", "submit_time"],
    "Visit Date": ["date_of_visit", "Survey_Date", "Date_And_Time", "SubmissionDate"],
    "Reviewer": ["QA_by", "QA by", "reviewer", "Reviewed_By", "checked_by", "Checker", "QC_by"],
    "Review Status": ["review_status", "QA_status", "QC_status", "Status"],
    "Region": ["Region", "region", "Zone", "zone"],
    "Province": ["Province", "province"],
    "District": ["District", "district"],
    "Village": ["Village", "Village_Community", "Village Community", "Qarya", "Community"],
    "Surveyor": ["Surveyor_Name", "Surveyor Name", "surveyor", "username", "Enumerator", "Enumerator_Name"],
    "Surveyor ID": ["Surveyor_Id", "Surveyor ID", "surveyor_id", "Enumerator_Id", "Enumerator ID"],
    "TPM ID": ["TPM_TLS_ID", "TPM_ECE_ID"],
    "Class ID": ["Class_Code", "Class_ID", "class_id", "sample_ECE_ID", "TLS_SN", "Class_Name", "Class Name"],
    "Class Type": ["TLS_Classes", "TLS_Type", "Classroom_Infra", "Class_Shift"],
}
ACCURACY_COLORS = {
    "Excellent (<=10m)": "#22c55e",
    "Good (<=25m)": "#38bdf8",
    "Review (<=50m)": "#f59e0b",
    "Weak (>50m)": "#ef4444",
    "Unknown": "#94a3b8",
}
CHART_FONT = "Manrope"
CHART_TEXT = "#dbe7ff"
CHART_MUTED = "#93a4c4"
CHART_GRID = "rgba(219, 231, 255, 0.12)"
CHART_HEIGHT = 340
PALETTE = ["#38bdf8", "#22c55e", "#f97316", "#8b5cf6", "#f59e0b", "#ef4444", "#0f766e", "#2563eb"]


def normalize_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def meaningful_text(value: object) -> str:
    text = clean_text(value)
    if text.lower() in {"", "nan", "none", "null", "n/a", "na", "-", "unspecified"}:
        return ""
    return text


def short_label(value: object, limit: int = 58) -> str:
    text = clean_text(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def first_existing_column(dataframe: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {normalize_key(column): column for column in dataframe.columns}
    for candidate in candidates:
        column = lookup.get(normalize_key(candidate))
        if column:
            return column
    return None


def parse_numeric_series(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce")


def parse_datetime_series(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.strip()
    text = text.str.replace(r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2})-(\d{1,2})(?::(\d{1,2}))?$", r"\1 \2:\3:\4", regex=True)
    text = text.str.replace(r":$", ":00", regex=True)
    text = text.replace({"": pd.NA, "nan": pd.NA, "NaT": pd.NA, "None": pd.NA})
    return pd.to_datetime(text, errors="coerce")


def first_valid_datetime(*series_list: pd.Series) -> pd.Series:
    if not series_list:
        return pd.Series(dtype="datetime64[ns]")
    result = pd.Series(pd.NaT, index=series_list[0].index, dtype="datetime64[ns]")
    for series in series_list:
        parsed = parse_datetime_series(series)
        result = result.fillna(parsed)
    return result


def format_minutes(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "N/A"
    if number < 1:
        return f"{number * 60:.0f} sec"
    if number < 60:
        return f"{number:.1f} min"
    return f"{number / 60:.1f} hr"


def source_row_label(index_value: object) -> str:
    try:
        return str(int(index_value) + 2)
    except (TypeError, ValueError):
        return clean_text(index_value) or "Unknown"


def is_rejection_status_column(column: str) -> bool:
    column_key = normalize_key(column)
    return column_key in STATUS_COLUMN_HINTS or column_key.endswith("status")


def standardize_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    prepared = dataframe.copy().dropna(how="all")
    prepared.columns = [str(column).strip() for column in prepared.columns]
    prepared = prepared.loc[:, [column for column in prepared.columns if column and not column.lower().startswith("unnamed:")]]
    return prepared


def split_clean_rejected(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    prepared = standardize_dataframe(dataframe)
    if prepared.empty:
        return prepared, 0
    rejected_mask = pd.Series(False, index=prepared.index)
    for column in prepared.columns:
        if not is_rejection_status_column(column):
            continue
        values = prepared[column].fillna("").astype(str).str.strip().str.lower()
        rejected_mask = rejected_mask | values.str.contains("reject|rej", regex=True, na=False)
    return prepared.loc[~rejected_mask].copy(), int(rejected_mask.sum())


def default_sheet_name(sheets: dict[str, pd.DataFrame]) -> str:
    if "data" in sheets:
        return "data"
    if not sheets:
        return ""
    return max(sheets.keys(), key=lambda sheet_name: len(sheets[sheet_name].dropna(how="all")))


def read_uploaded_sheets(uploaded_file) -> dict[str, pd.DataFrame]:
    file_name = uploaded_file.name.lower()
    buffer = BytesIO(uploaded_file.getvalue())
    if file_name.endswith(".csv"):
        return {"CSV": pd.read_csv(buffer)}
    if file_name.endswith(".xlsx") or file_name.endswith(".xls"):
        return {str(name): frame for name, frame in pd.read_excel(buffer, sheet_name=None).items()}
    raise ValueError("Only CSV, XLS, and XLSX files are supported.")


@st.cache_data(ttl=300, show_spinner=False)
def read_local_sheets(path_text: str) -> dict[str, pd.DataFrame]:
    path = Path(path_text)
    if path.suffix.lower() == ".csv":
        return {"CSV": pd.read_csv(path)}
    return {str(name): frame for name, frame in pd.read_excel(path, sheet_name=None).items()}


def parse_gps_value(value: object) -> tuple[float | None, float | None, float | None, float | None]:
    text = clean_text(value)
    if not text:
        return None, None, None, None
    numbers: list[float] = []
    for part in re.split(r"[\s,]+", text):
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


def accuracy_band(value: object) -> str:
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


def class_label(row: pd.Series) -> str:
    class_id = meaningful_text(row.get("Class ID", ""))
    tpm_id = meaningful_text(row.get("TPM ID", ""))
    if class_id and tpm_id and class_id != tpm_id:
        return f"{class_id} | {tpm_id}"
    return class_id or tpm_id or "Class"


def build_gps_dataframe(dataframe: pd.DataFrame, dataset_name: str, source_file: str) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame()
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
            if lat is not None and lon is not None:
                rows.append({"_row": index, "lat": lat, "lon": lon, "altitude": altitude, "accuracy": accuracy})
        gps = pd.DataFrame(rows)
    else:
        return pd.DataFrame()

    if gps.empty:
        return pd.DataFrame()
    gps = gps.reset_index(drop=True)
    gps["Dataset"] = dataset_name
    gps["Source File"] = source_file
    gps["Source Row"] = gps["_row"].apply(source_row_label)
    gps["Accuracy Band"] = gps["accuracy"].apply(accuracy_band)

    for label, candidates in GPS_CONTEXT_CANDIDATES.items():
        column = first_existing_column(dataframe, candidates)
        if column:
            gps[label] = dataframe.loc[gps["_row"], column].fillna("").astype(str).str.strip().replace("", "N/A").to_numpy()
        else:
            gps[label] = "N/A"
    gps["Display Class"] = gps.apply(class_label, axis=1)
    gps["GPS Timestamp"] = first_valid_datetime(gps["GPS Time"], gps["Start Time"], gps["Submission Time"])
    gps["Start Timestamp"] = parse_datetime_series(gps["Start Time"])
    gps["End Timestamp"] = parse_datetime_series(gps["End Time"])
    gps["Submission Timestamp"] = parse_datetime_series(gps["Submission Time"])
    duration = (gps["End Timestamp"] - gps["Start Timestamp"]).dt.total_seconds() / 60
    gps["Form Duration (min)"] = duration.where((duration >= 0) & (duration <= 24 * 60))
    gps["Form Duration"] = gps["Form Duration (min)"].apply(format_minutes)
    return gps


def load_dataset_records(uploaded_files, use_local_datasets: bool) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []

    if use_local_datasets:
        for display_name, path in LOCAL_DATASET_PATHS.items():
            if not path.exists():
                continue
            try:
                sheets = read_local_sheets(str(path))
                sheet_name = default_sheet_name(sheets)
                clean, rejected = split_clean_rejected(sheets[sheet_name])
                gps = build_gps_dataframe(clean, display_name, path.name)
                records.append(
                    {
                        "Dataset": display_name,
                        "Source File": path.name,
                        "Sheet": sheet_name,
                        "Clean Rows": len(clean),
                        "Rejected Excluded": rejected,
                        "GPS": gps,
                    }
                )
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")

    for uploaded_file in uploaded_files or []:
        try:
            sheets = read_uploaded_sheets(uploaded_file)
            sheet_name = default_sheet_name(sheets)
            clean, rejected = split_clean_rejected(sheets[sheet_name])
            display_name = uploaded_file.name.rsplit(".", 1)[0]
            gps = build_gps_dataframe(clean, display_name, uploaded_file.name)
            records.append(
                {
                    "Dataset": display_name,
                    "Source File": uploaded_file.name,
                    "Sheet": sheet_name,
                    "Clean Rows": len(clean),
                    "Rejected Excluded": rejected,
                    "GPS": gps,
                }
            )
        except Exception as exc:
            errors.append(f"{uploaded_file.name}: {exc}")
    return records, errors


def combine_gps(records: list[dict[str, Any]]) -> pd.DataFrame:
    frames = [record["GPS"] for record in records if isinstance(record.get("GPS"), pd.DataFrame) and not record["GPS"].empty]
    if not frames:
        return pd.DataFrame()
    gps = pd.concat(frames, ignore_index=True)
    gps["Point"] = [f"GPS-{index + 1:03d}" for index in range(len(gps))]
    return gps


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


def time_difference_minutes(left_time: object, right_time: object) -> float | None:
    if pd.isna(left_time) or pd.isna(right_time):
        return None
    return abs((pd.Timestamp(right_time) - pd.Timestamp(left_time)).total_seconds()) / 60


def build_distance_line(gps: pd.DataFrame, point_a: str, point_b: str) -> pd.DataFrame:
    if point_a == point_b or gps.empty:
        return pd.DataFrame()
    indexed = gps.set_index("Point", drop=False)
    if point_a not in indexed.index or point_b not in indexed.index:
        return pd.DataFrame()
    left = indexed.loc[point_a]
    right = indexed.loc[point_b]
    distance_km = haversine_km(float(left["lat"]), float(left["lon"]), float(right["lat"]), float(right["lon"]))
    time_gap = time_difference_minutes(left.get("GPS Timestamp"), right.get("GPS Timestamp"))
    return pd.DataFrame(
        [
            {
                "start_lat": float(left["lat"]),
                "start_lon": float(left["lon"]),
                "end_lat": float(right["lat"]),
                "end_lon": float(right["lon"]),
                "mid_lat": (float(left["lat"]) + float(right["lat"])) / 2,
                "mid_lon": (float(left["lon"]) + float(right["lon"])) / 2,
                "Distance (km)": round(distance_km, 3),
                "Distance (m)": round(distance_km * 1000, 1),
                "Distance Label": format_distance_label(distance_km),
                "Time Difference (min)": round(time_gap, 1) if time_gap is not None else None,
                "Time Difference": format_minutes(time_gap) if time_gap is not None else "N/A",
                "From": left["Display Class"],
                "To": right["Display Class"],
            }
        ]
    )


def build_pairwise_distances(gps: pd.DataFrame, max_points: int = 260) -> pd.DataFrame:
    if len(gps) < 2:
        return pd.DataFrame()
    work = gps.head(max_points).reset_index(drop=True)
    rows: list[dict[str, Any]] = []
    for left_index, right_index in combinations(range(len(work)), 2):
        left = work.iloc[left_index]
        right = work.iloc[right_index]
        distance_km = haversine_km(float(left["lat"]), float(left["lon"]), float(right["lat"]), float(right["lon"]))
        time_gap = time_difference_minutes(left.get("GPS Timestamp"), right.get("GPS Timestamp"))
        accuracy_a = pd.to_numeric(pd.Series([left.get("accuracy")]), errors="coerce").iloc[0]
        accuracy_b = pd.to_numeric(pd.Series([right.get("accuracy")]), errors="coerce").iloc[0]
        average_accuracy = pd.Series([accuracy_a, accuracy_b]).dropna().mean()
        rows.append(
            {
                "Point A": left["Point"],
                "Point B": right["Point"],
                "Class A": left["Display Class"],
                "Class B": right["Display Class"],
                "Surveyor A": left.get("Surveyor", "N/A"),
                "Surveyor B": right.get("Surveyor", "N/A"),
                "Distance (km)": round(distance_km, 3),
                "Distance (m)": round(distance_km * 1000, 1),
                "Distance": format_distance_label(distance_km),
                "Time A": left.get("GPS Timestamp"),
                "Time B": right.get("GPS Timestamp"),
                "Time Difference (min)": round(time_gap, 1) if time_gap is not None else None,
                "Time Difference": format_minutes(time_gap) if time_gap is not None else "N/A",
                "Accuracy A (m)": round(float(accuracy_a), 1) if pd.notna(accuracy_a) else None,
                "Accuracy B (m)": round(float(accuracy_b), 1) if pd.notna(accuracy_b) else None,
                "Average Accuracy (m)": round(float(average_accuracy), 1) if pd.notna(average_accuracy) else None,
                "Province": left.get("Province", "N/A"),
                "District": left.get("District", "N/A"),
            }
        )
    return pd.DataFrame(rows).sort_values("Distance (km)") if rows else pd.DataFrame()


def build_nearest_table(gps: pd.DataFrame) -> pd.DataFrame:
    pairwise = build_pairwise_distances(gps)
    if pairwise.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for point in pd.unique(pd.concat([pairwise["Point A"], pairwise["Point B"]], ignore_index=True)):
        matches = pairwise[(pairwise["Point A"] == point) | (pairwise["Point B"] == point)].sort_values("Distance (km)")
        if matches.empty:
            continue
        nearest = matches.iloc[0]
        if nearest["Point A"] == point:
            rows.append(
                {
                    "Point": point,
                    "Class": nearest["Class A"],
                    "Nearest Point": nearest["Point B"],
                    "Nearest Class": nearest["Class B"],
                    "Nearest Distance (km)": nearest["Distance (km)"],
                    "Nearest Distance (m)": nearest["Distance (m)"],
                    "Time Difference (min)": nearest.get("Time Difference (min)"),
                    "Time Difference": nearest.get("Time Difference"),
                }
            )
        else:
            rows.append(
                {
                    "Point": point,
                    "Class": nearest["Class B"],
                    "Nearest Point": nearest["Point A"],
                    "Nearest Class": nearest["Class A"],
                    "Nearest Distance (km)": nearest["Distance (km)"],
                    "Nearest Distance (m)": nearest["Distance (m)"],
                    "Time Difference (min)": nearest.get("Time Difference (min)"),
                    "Time Difference": nearest.get("Time Difference"),
                }
            )
    return pd.DataFrame(rows).sort_values("Nearest Distance (km)") if rows else pd.DataFrame()


def movement_signal(distance_km: float, gap_minutes: float | None, accuracy: object) -> str:
    accuracy_number = pd.to_numeric(pd.Series([accuracy]), errors="coerce").iloc[0]
    if pd.notna(accuracy_number) and accuracy_number > 50:
        return "Weak GPS Accuracy"
    if gap_minutes is None:
        return "Missing Time"
    if gap_minutes < 3 and distance_km > 0.5:
        return "Very Fast Move"
    speed = distance_km / (gap_minutes / 60) if gap_minutes > 0 else None
    if speed is not None and speed > 80:
        return "Review Speed"
    return "OK"


def build_surveyor_movement_table(gps: pd.DataFrame) -> pd.DataFrame:
    if gps.empty or "Surveyor" not in gps.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    work = gps.copy()
    work["_survey_order_time"] = work["GPS Timestamp"]
    for surveyor, group in work.groupby("Surveyor", dropna=False):
        surveyor_name = meaningful_text(surveyor) or "N/A"
        group = group.sort_values(["_survey_order_time", "Point"], na_position="last").reset_index(drop=True)
        if len(group) < 2:
            continue
        for index in range(1, len(group)):
            previous = group.iloc[index - 1]
            current = group.iloc[index]
            distance_km = haversine_km(float(previous["lat"]), float(previous["lon"]), float(current["lat"]), float(current["lon"]))
            gap_minutes = None
            if pd.notna(previous.get("GPS Timestamp")) and pd.notna(current.get("GPS Timestamp")):
                gap_minutes = (pd.Timestamp(current["GPS Timestamp"]) - pd.Timestamp(previous["GPS Timestamp"])).total_seconds() / 60
            speed = distance_km / (gap_minutes / 60) if gap_minutes and gap_minutes > 0 else None
            rows.append(
                {
                    "Surveyor": surveyor_name,
                    "From Point": previous["Point"],
                    "To Point": current["Point"],
                    "From Class": previous["Display Class"],
                    "To Class": current["Display Class"],
                    "From Time": previous.get("GPS Timestamp"),
                    "To Time": current.get("GPS Timestamp"),
                    "Travel Time (min)": round(gap_minutes, 1) if gap_minutes is not None else None,
                    "Travel Time": format_minutes(gap_minutes) if gap_minutes is not None else "N/A",
                    "Travel Distance (km)": round(distance_km, 3),
                    "Travel Distance": format_distance_label(distance_km),
                    "Approx Speed (km/h)": round(speed, 1) if speed is not None else None,
                    "Form Duration (min)": current.get("Form Duration (min)"),
                    "Current Accuracy (m)": pd.to_numeric(pd.Series([current.get("accuracy")]), errors="coerce").iloc[0],
                    "Region": current.get("Region", "N/A"),
                    "Province": current.get("Province", "N/A"),
                    "District": current.get("District", "N/A"),
                    "Signal": movement_signal(distance_km, gap_minutes, current.get("accuracy")),
                }
            )
    return pd.DataFrame(rows)


def build_group_summary(gps: pd.DataFrame, group_column: str) -> pd.DataFrame:
    if group_column not in gps.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for group, group_data in gps.groupby(group_column, dropna=False):
        nearest = build_nearest_table(group_data)
        rows.append(
            {
                group_column: meaningful_text(group) or "N/A",
                "GPS Points": len(group_data),
                "Classes Seen": int(group_data["Display Class"].nunique()),
                "Median Accuracy (m)": round(float(pd.to_numeric(group_data["accuracy"], errors="coerce").median()), 1)
                if pd.to_numeric(group_data["accuracy"], errors="coerce").notna().any()
                else None,
                "Median Nearest Distance (km)": round(float(nearest["Nearest Distance (km)"].median()), 3) if not nearest.empty else None,
            }
        )
    return pd.DataFrame(rows).sort_values(["GPS Points", "Classes Seen"], ascending=False)


def build_quality_flags(gps: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    weak = gps[pd.to_numeric(gps["accuracy"], errors="coerce") > 50]
    for _, row in weak.iterrows():
        rows.append({"Signal": "Weak GPS Accuracy", "Point": row["Point"], "Class": row["Display Class"], "Detail": f"{row['accuracy']} m"})
    duplicates = gps.groupby(["lat", "lon"]).filter(lambda group: len(group) > 1)
    for _, row in duplicates.iterrows():
        rows.append({"Signal": "Duplicate Coordinates", "Point": row["Point"], "Class": row["Display Class"], "Detail": f"{row['lat']:.6f}, {row['lon']:.6f}"})
    missing_place = gps[(gps["Province"].map(meaningful_text) == "") | (gps["District"].map(meaningful_text) == "")]
    for _, row in missing_place.iterrows():
        rows.append({"Signal": "Missing Province/District", "Point": row["Point"], "Class": row["Display Class"], "Detail": row["Dataset"]})
    duration = pd.to_numeric(gps["Form Duration (min)"], errors="coerce")
    very_short = gps[duration < 5]
    for _, row in very_short.iterrows():
        rows.append({"Signal": "Very Short Form", "Point": row["Point"], "Class": row["Display Class"], "Detail": row["Form Duration"]})
    very_long = gps[duration > 180]
    for _, row in very_long.iterrows():
        rows.append({"Signal": "Long Form Duration", "Point": row["Point"], "Class": row["Display Class"], "Detail": row["Form Duration"]})
    return pd.DataFrame(rows)


def filter_values(gps: pd.DataFrame, column: str, require_variation: bool = False) -> list[str]:
    if column not in gps.columns:
        return []
    values = gps[column].fillna("").astype(str).map(meaningful_text)
    values = values[values != ""]
    if values.empty or (require_variation and values.nunique() <= 1):
        return []
    return sorted(values.unique().tolist())


def apply_gps_filters(gps: pd.DataFrame) -> pd.DataFrame:
    filtered = gps.copy()
    region_col, province_col, district_col = st.columns(3, gap="large")
    with region_col:
        regions = filter_values(filtered, "Region")
        selected_regions = st.multiselect("Region", regions, key="gps-track-region") if regions else []
    if selected_regions:
        filtered = filtered[filtered["Region"].astype(str).isin(selected_regions)]
    with province_col:
        provinces = filter_values(filtered, "Province")
        selected_provinces = st.multiselect("Province", provinces, key="gps-track-province") if provinces else []
    if selected_provinces:
        filtered = filtered[filtered["Province"].astype(str).isin(selected_provinces)]
    with district_col:
        districts = filter_values(filtered, "District")
        selected_districts = st.multiselect("District", districts, key="gps-track-district") if districts else []
    if selected_districts:
        filtered = filtered[filtered["District"].astype(str).isin(selected_districts)]
    return filtered


def gps_zoom_level(gps: pd.DataFrame) -> int:
    span = max(float(gps["lat"].max() - gps["lat"].min()), float(gps["lon"].max() - gps["lon"].min()))
    if span <= 0.01:
        return 14
    if span <= 0.05:
        return 12
    if span <= 0.2:
        return 10
    if span <= 1:
        return 8
    return 6


def folium_popup_html(row: pd.Series) -> str:
    details = [
        ("Point", row.get("Point", "")),
        ("Class", row.get("Display Class", "")),
        ("TPM ID", row.get("TPM ID", "")),
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
        ("Altitude", f"{pd.to_numeric(pd.Series([row.get('altitude')]), errors='coerce').iloc[0]:.1f} m" if pd.notna(pd.to_numeric(pd.Series([row.get('altitude')]), errors='coerce').iloc[0]) else "N/A"),
        ("Accuracy", f"{pd.to_numeric(pd.Series([row.get('accuracy')]), errors='coerce').iloc[0]:.1f} m" if pd.notna(pd.to_numeric(pd.Series([row.get('accuracy')]), errors='coerce').iloc[0]) else "N/A"),
    ]
    rows = "".join(
        f"<tr><td style='padding:3px 10px 3px 0;color:#64748b'>{html.escape(label)}</td><td style='padding:3px 0;color:#0f172a;font-weight:700'>{html.escape(clean_text(value) or 'N/A')}</td></tr>"
        for label, value in details
    )
    return f"<div style='font-family:Arial,sans-serif;font-size:12px;min-width:290px'><table>{rows}</table></div>"


def safe_json_value(value: object) -> object:
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except TypeError:
            pass
    if isinstance(value, Real) and not isinstance(value, bool):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return ""
        return round(number, 6)
    return value


def number_label(value: object, suffix: str = "", digits: int = 1) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "N/A"
    return f"{number:.{digits}f}{suffix}"


def build_map_point_payload(gps: pd.DataFrame) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for _, row in gps.iterrows():
        payload.append(
            {
                "point": clean_text(row.get("Point", "")),
                "dataset": clean_text(row.get("Dataset", "")),
                "sourceFile": clean_text(row.get("Source File", "")),
                "sourceRow": clean_text(row.get("Source Row", "")),
                "className": clean_text(row.get("Display Class", "")),
                "classId": clean_text(row.get("Class ID", "")),
                "classType": clean_text(row.get("Class Type", "")),
                "tpmId": clean_text(row.get("TPM ID", "")),
                "surveyor": clean_text(row.get("Surveyor", "")),
                "surveyorId": clean_text(row.get("Surveyor ID", "")),
                "reviewer": clean_text(row.get("Reviewer", "")),
                "reviewStatus": clean_text(row.get("Review Status", "")),
                "region": clean_text(row.get("Region", "")),
                "province": clean_text(row.get("Province", "")),
                "district": clean_text(row.get("District", "")),
                "village": clean_text(row.get("Village", "")),
                "gpsTime": clean_text(row.get("GPS Time", "")),
                "timestamp": safe_json_value(row.get("GPS Timestamp", "")),
                "startTime": safe_json_value(row.get("Start Timestamp", "")),
                "endTime": safe_json_value(row.get("End Timestamp", "")),
                "submissionTime": clean_text(row.get("Submission Time", "")),
                "submissionTimestamp": safe_json_value(row.get("Submission Timestamp", "")),
                "formDuration": clean_text(row.get("Form Duration", "")),
                "visitDate": clean_text(row.get("Visit Date", "")),
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "altitude": number_label(row.get("altitude"), " m", 1),
                "accuracy": number_label(row.get("accuracy"), " m", 1),
                "accuracyValue": safe_json_value(pd.to_numeric(pd.Series([row.get("accuracy")]), errors="coerce").iloc[0]),
                "accuracyBand": clean_text(row.get("Accuracy Band", "")),
                "color": ACCURACY_COLORS.get(row.get("Accuracy Band", ""), "#94a3b8"),
            }
        )
    return payload


def build_map_line_payload(distance_line: pd.DataFrame) -> dict[str, Any] | None:
    if distance_line.empty:
        return None
    line = distance_line.iloc[0]
    return {
        "startLat": safe_json_value(line.get("start_lat")),
        "startLon": safe_json_value(line.get("start_lon")),
        "endLat": safe_json_value(line.get("end_lat")),
        "endLon": safe_json_value(line.get("end_lon")),
        "midLat": safe_json_value(line.get("mid_lat")),
        "midLon": safe_json_value(line.get("mid_lon")),
        "distanceLabel": clean_text(line.get("Distance Label", "")),
        "timeLabel": clean_text(line.get("Time Difference", "")),
    }


def inject_interactive_map_script(map_object: Any, gps: pd.DataFrame, distance_line: pd.DataFrame) -> None:
    if folium is None:
        return
    map_name = map_object.get_name()
    points_json = json.dumps(build_map_point_payload(gps), ensure_ascii=False)
    line_json = json.dumps(build_map_line_payload(distance_line), ensure_ascii=False)
    script = f"""
    <style>
      .gps-full-tooltip {{
        background: rgba(250,246,235,.96);
        border: 1px solid rgba(94,79,58,.28);
        border-radius: 5px;
        box-shadow: 0 8px 20px rgba(0,0,0,.34);
        color: #3d3528;
        padding: 8px 10px;
      }}
      .gps-full-tooltip::before {{ display:none; }}
      .gps-hover-card {{
        min-width: 245px;
        max-width: 340px;
        font-family: Arial, sans-serif;
        font-size: 12px;
        line-height: 1.28;
      }}
      .gps-hover-card .head {{
        color: #40382c;
        padding: 0 0 2px;
        font-weight: 800;
      }}
      .gps-hover-card .line {{ color:#3d3528; margin-top:1px; }}
      .gps-hover-card .muted {{ color:#625847; }}
      .gps-popup-card {{
        min-width: 330px;
        max-width: 430px;
        font-family: Arial, sans-serif;
        font-size: 12px;
        line-height: 1.25;
      }}
      .gps-popup-card .head {{
        background: #07111f;
        color: #f8fbff;
        padding: 10px 12px;
        border-radius: 8px 8px 0 0;
        font-weight: 800;
      }}
      .gps-popup-card .sub {{ color: #bfdbfe; font-size: 11px; margin-top: 3px; }}
      .gps-popup-card table {{ width: 100%; border-collapse: collapse; }}
      .gps-popup-card td {{ padding: 4px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }}
      .gps-popup-card td:first-child {{ color: #64748b; width: 118px; }}
      .gps-popup-card td:last-child {{ color: #0f172a; font-weight: 700; }}
      .gps-map-panel {{
        background: rgba(7,17,31,.93);
        color: #f8fbff;
        border: 1px solid rgba(56,189,248,.35);
        border-radius: 14px;
        box-shadow: 0 18px 46px rgba(0,0,0,.35);
        padding: 11px 12px;
        width: 285px;
        font-family: Arial, sans-serif;
        font-size: 12px;
      }}
      .gps-map-panel b {{ color: #93c5fd; }}
      .gps-map-panel .hint {{ color: #9fb0cf; margin-top: 6px; line-height: 1.35; }}
      .gps-distance-pill {{
        background:#07111f;
        color:#f8fbff;
        border:1px solid rgba(56,189,248,.78);
        border-radius:999px;
        padding:5px 10px;
        font-size:12px;
        font-weight:800;
        white-space:nowrap;
        box-shadow:0 8px 18px rgba(0,0,0,.35);
      }}
    </style>
    <script>
    (function() {{
      const map = {map_name};
      const points = {points_json};
      const initialLine = {line_json};
      const markers = [];
      let origin = null;
      let liveLine = null;
      let liveLabel = null;
      let fixedLine = null;
      let fixedLabel = null;

      function esc(value) {{
        return String(value ?? "N/A").replace(/[&<>"']/g, function(ch) {{
          return ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\\"":"&quot;","'":"&#039;"}})[ch];
        }});
      }}
      function row(label, value) {{
        const shown = value === undefined || value === null || String(value).trim() === "" ? "N/A" : value;
        return `<tr><td>${{esc(label)}}</td><td>${{esc(shown)}}</td></tr>`;
      }}
      function placeLine(p) {{
        return [p.village, p.district, p.province].filter((item) => item && String(item).trim() && String(item).trim() !== "N/A").join(", ");
      }}
      function compactTooltipHtml(p) {{
        const classText = p.className && p.className !== "N/A" ? p.className : p.point;
        const place = placeLine(p) || `${{p.province || "Unknown"}}, Afghanistan`;
        return `<div class="gps-hover-card">
          <div class="head">${{esc(classText)}} — ${{esc(place)}}</div>
          <div class="line"><span class="muted">TPM/Class:</span> ${{esc(p.tpmId || p.classId || "N/A")}}</div>
          <div class="line"><span class="muted">Surveyor:</span> ${{esc(p.surveyor || p.surveyorId || "N/A")}}</div>
          <div class="line"><span class="muted">GPS:</span> ${{esc(Number(p.lat).toFixed(6))}}, ${{esc(Number(p.lon).toFixed(6))}}</div>
          <div class="line"><span class="muted">Accuracy:</span> ${{esc(p.accuracy)}} | <span class="muted">Time:</span> ${{esc(p.gpsTime || p.timestamp || "N/A")}}</div>
        </div>`;
      }}
      function popupHtml(p) {{
        return `<div class="gps-popup-card">
          <div class="head">${{esc(p.point)}} | ${{esc(p.className)}}<div class="sub">${{esc(p.province)}} / ${{esc(p.district)}} / ${{esc(p.village)}}</div></div>
          <table>
            ${{row("Dataset", p.dataset)}}
            ${{row("Source File", p.sourceFile)}}
            ${{row("Source Row", p.sourceRow)}}
            ${{row("TPM ID", p.tpmId)}}
            ${{row("Class ID", p.classId)}}
            ${{row("Class Type", p.classType)}}
            ${{row("Surveyor", p.surveyor)}}
            ${{row("Surveyor ID", p.surveyorId)}}
            ${{row("Reviewer", p.reviewer)}}
            ${{row("Review Status", p.reviewStatus)}}
            ${{row("Visit Date", p.visitDate)}}
            ${{row("GPS Time", p.gpsTime)}}
            ${{row("Start Time", p.startTime)}}
            ${{row("End Time", p.endTime)}}
            ${{row("Submission Time", p.submissionTime)}}
            ${{row("Form Duration", p.formDuration)}}
            ${{row("Region", p.region)}}
            ${{row("Province", p.province)}}
            ${{row("District", p.district)}}
            ${{row("Village", p.village)}}
            ${{row("Latitude", Number(p.lat).toFixed(6))}}
            ${{row("Longitude", Number(p.lon).toFixed(6))}}
            ${{row("Altitude", p.altitude)}}
            ${{row("Accuracy", p.accuracy)}}
            ${{row("Accuracy Band", p.accuracyBand)}}
          </table>
        </div>`;
      }}
      function haversineKm(a, b) {{
        const R = 6371.0088;
        const toRad = (d) => d * Math.PI / 180;
        const dLat = toRad(b.lat - a.lat);
        const dLon = toRad(b.lon - a.lon);
        const lat1 = toRad(a.lat);
        const lat2 = toRad(b.lat);
        const h = Math.sin(dLat/2)**2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon/2)**2;
        return 2 * R * Math.atan2(Math.sqrt(h), Math.sqrt(1-h));
      }}
      function distanceLabel(km) {{
        return km < 1 ? `${{Math.round(km * 1000)}} m` : `${{km.toFixed(2)}} km`;
      }}
      function timeGap(a, b) {{
        if (!a.timestamp || !b.timestamp) return "N/A";
        const ta = new Date(a.timestamp).getTime();
        const tb = new Date(b.timestamp).getTime();
        if (!Number.isFinite(ta) || !Number.isFinite(tb)) return "N/A";
        const minutes = Math.abs(tb - ta) / 60000;
        if (minutes < 1) return `${{Math.round(minutes * 60)}} sec`;
        if (minutes < 60) return `${{minutes.toFixed(1)}} min`;
        return `${{(minutes / 60).toFixed(1)}} hr`;
      }}
      function midpoint(a, b) {{
        return [(a.lat + b.lat) / 2, (a.lon + b.lon) / 2];
      }}
      function clearLayer(layer) {{
        if (layer) map.removeLayer(layer);
        return null;
      }}
      function labelMarker(latlng, text) {{
        return L.marker(latlng, {{
          interactive: false,
          icon: L.divIcon({{ className: "", html: `<div class="gps-distance-pill">${{esc(text)}}</div>` }})
        }}).addTo(map);
      }}
      function draw(a, b, temporary) {{
        const km = haversineKm(a, b);
        const label = `${{distanceLabel(km)}} | ${{timeGap(a, b)}}`;
        if (temporary) {{
          liveLine = clearLayer(liveLine);
          liveLabel = clearLayer(liveLabel);
          liveLine = L.polyline([[a.lat, a.lon], [b.lat, b.lon]], {{color:"#22c55e", weight:4, opacity:.92, dashArray:"8 7"}}).addTo(map);
          liveLabel = labelMarker(midpoint(a, b), label);
        }} else {{
          fixedLine = clearLayer(fixedLine);
          fixedLabel = clearLayer(fixedLabel);
          fixedLine = L.polyline([[a.lat, a.lon], [b.lat, b.lon]], {{color:"#38bdf8", weight:5, opacity:.96}}).addTo(map);
          fixedLabel = labelMarker(midpoint(a, b), label);
        }}
        panel.update(b, label, temporary);
      }}
      const panel = L.control({{position:"bottomleft"}});
      panel.onAdd = function() {{
        this._div = L.DomUtil.create("div", "gps-map-panel");
        this.update();
        L.DomEvent.disableClickPropagation(this._div);
        return this._div;
      }};
      panel.update = function(point, measure, temporary) {{
        const originText = origin ? `<b>Selected:</b> ${{esc(origin.point)}}<br>` : "<b>Selected:</b> none<br>";
        const targetText = point ? `<b>${{temporary ? "Hover distance" : "Measured distance"}}:</b> ${{esc(measure)}}<br><b>Target:</b> ${{esc(point.point)}}` : "";
        this._div.innerHTML = `${{originText}}${{targetText}}<div class="hint">Measure on the map: click the first GPS point, then move the pointer over another point to see live distance. Click the second point to lock the line. Double-click the map to clear.</div>`;
      }};
      panel.addTo(map);
      map.on("dblclick", function() {{
        origin = null;
        liveLine = clearLayer(liveLine);
        liveLabel = clearLayer(liveLabel);
        fixedLine = clearLayer(fixedLine);
        fixedLabel = clearLayer(fixedLabel);
        markers.forEach((entry) => entry.marker.setStyle({{radius:10, color:"rgba(248,250,252,.42)", weight:1.4, fillOpacity:.82}}));
        panel.update();
      }});
      points.forEach((p) => {{
        const marker = L.circleMarker([p.lat, p.lon], {{
          radius: 10,
          color: "rgba(248,250,252,.42)",
          weight: 1.4,
          fill: true,
          fillColor: p.color || "#ef4444",
          fillOpacity: .82
        }}).addTo(map);
        marker.bindTooltip(compactTooltipHtml(p), {{sticky:true, direction:"top", className:"gps-full-tooltip", opacity:.98, offset:[0,-8]}});
        marker.bindPopup(popupHtml(p), {{maxWidth:440}});
        marker.on("mouseover", function() {{
          marker.setStyle({{radius:14, color:"#f8fafc", weight:3.2, fillOpacity:.92}});
          if (origin && origin.point !== p.point) draw(origin, p, true);
          else panel.update(p);
        }});
        marker.on("mouseout", function() {{
          if (!origin || origin.point !== p.point) marker.setStyle({{radius:10, color:"rgba(248,250,252,.42)", weight:1.4, fillOpacity:.82}});
          liveLine = clearLayer(liveLine);
          liveLabel = clearLayer(liveLabel);
        }});
        marker.on("click", function() {{
          if (!origin || origin.point === p.point) {{
            origin = p;
            markers.forEach((entry) => entry.marker.setStyle({{radius:10, color:"rgba(248,250,252,.42)", weight:1.4, fillOpacity:.82}}));
            marker.setStyle({{radius:15, color:"#f8fafc", weight:3.6, fillOpacity:.94}});
            panel.update(p);
          }} else {{
            draw(origin, p, false);
            origin = p;
            markers.forEach((entry) => entry.marker.setStyle({{radius:10, color:"rgba(248,250,252,.42)", weight:1.4, fillOpacity:.82}}));
            marker.setStyle({{radius:15, color:"#f8fafc", weight:3.6, fillOpacity:.94}});
          }}
        }});
        markers.push({{point:p, marker}});
      }});
      if (
        initialLine &&
        Number.isFinite(Number(initialLine.startLat)) &&
        Number.isFinite(Number(initialLine.startLon)) &&
        Number.isFinite(Number(initialLine.endLat)) &&
        Number.isFinite(Number(initialLine.endLon))
      ) {{
        const a = {{lat:Number(initialLine.startLat), lon:Number(initialLine.startLon), point:"Selected A", timestamp:""}};
        const b = {{lat:Number(initialLine.endLat), lon:Number(initialLine.endLon), point:"Selected B", timestamp:""}};
        fixedLine = L.polyline([[a.lat, a.lon], [b.lat, b.lon]], {{color:"#38bdf8", weight:5, opacity:.96}}).addTo(map);
        fixedLabel = labelMarker([Number(initialLine.midLat), Number(initialLine.midLon)], `${{initialLine.distanceLabel || ""}} | ${{initialLine.timeLabel || "N/A"}}`);
      }}
    }})();
    </script>
    """
    map_object.get_root().html.add_child(folium.Element(script))


def add_map_tiles(map_object: Any, map_type: str) -> None:
    if folium is None:
        return
    if map_type == "Satellite":
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Tiles (c) Esri, Maxar, Earthstar Geographics, and the GIS User Community",
            name="Satellite",
            control=False,
        ).add_to(map_object)
        folium.TileLayer(
            tiles="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}",
            attr="Labels (c) Esri",
            name="Road Labels",
            overlay=True,
            control=False,
        ).add_to(map_object)
        folium.TileLayer(
            tiles="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
            attr="Places (c) Esri",
            name="Place Labels",
            overlay=True,
            control=False,
        ).add_to(map_object)
    else:
        folium.TileLayer(
            tiles="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
            attr="(c) OpenStreetMap contributors (c) CARTO",
            name="Dark",
            subdomains="abcd",
            control=False,
        ).add_to(map_object)


def render_gps_map(gps: pd.DataFrame, map_type: str, distance_line: pd.DataFrame) -> None:
    map_data = gps.copy()
    map_data["latitude"] = map_data["lat"]
    map_data["longitude"] = map_data["lon"]
    if folium is None or components is None:
        st.map(map_data[["latitude", "longitude"]], use_container_width=True)
        return

    map_object = folium.Map(
        location=[float(gps["lat"].median()), float(gps["lon"].median())],
        zoom_start=gps_zoom_level(gps),
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )
    add_map_tiles(map_object, map_type)
    inject_interactive_map_script(map_object, gps, distance_line)

    if Fullscreen is not None:
        Fullscreen(position="topright").add_to(map_object)
    if MeasureControl is not None:
        MeasureControl(position="topleft", primary_length_unit="meters", secondary_length_unit="kilometers").add_to(map_object)
    bounds = [[float(gps["lat"].min()), float(gps["lon"].min())], [float(gps["lat"].max()), float(gps["lon"].max())]]
    if bounds[0] != bounds[1]:
        map_object.fit_bounds(bounds, padding=(30, 30))
    components.html(map_object._repr_html_(), height=720, scrolling=False)


def modernize_chart(chart: alt.TopLevelMixin) -> alt.TopLevelMixin:
    return (
        chart.properties(padding={"top": 18, "right": 16, "bottom": 12, "left": 16})
        .configure(background="transparent")
        .configure_view(strokeOpacity=0)
        .configure_title(font=CHART_FONT, fontSize=16, fontWeight=800, color=CHART_TEXT, anchor="start", offset=20)
        .configure_axis(labelFont=CHART_FONT, titleFont=CHART_FONT, labelColor=CHART_MUTED, titleColor=CHART_MUTED, gridColor=CHART_GRID, domainColor=CHART_GRID)
        .configure_legend(labelFont=CHART_FONT, titleFont=CHART_FONT, labelColor=CHART_MUTED, titleColor=CHART_MUTED, orient="bottom")
    )


def render_metric_card(title: str, value: str, subtitle: str, tone: str) -> None:
    st.markdown(
        f"""
        <div style="
            position:relative; overflow:hidden; min-height:82px; padding:10px 12px;
            border-radius:10px; border:1px solid rgba(226,232,240,0.13);
            background:linear-gradient(145deg,rgba(255,255,255,0.10),rgba(255,255,255,0.035)),rgba(7,17,31,0.78);
            box-shadow:0 12px 28px rgba(0,0,0,0.20), inset 0 1px 0 rgba(255,255,255,0.12);">
            <div style="position:absolute; inset:auto -30px -44px auto; width:90px; height:90px; border-radius:50%; background:{tone}; filter:blur(12px); opacity:.17;"></div>
            <div style="position:relative; z-index:1; color:#a9b8d6; font-size:.66rem; font-weight:800; text-transform:uppercase; letter-spacing:.07em;">{html.escape(title)}</div>
            <div style="position:relative; z-index:1; margin-top:.32rem; color:#f8fbff; font-size:1.22rem; line-height:1; font-weight:900;">{html.escape(value)}</div>
            <div style="position:relative; z-index:1; margin-top:.32rem; color:#9fb0cf; font-size:.70rem; line-height:1.25;">{html.escape(subtitle)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_bar_chart(dataframe: pd.DataFrame, category: str, value: str, title: str, color: str = "#38bdf8") -> None:
    if dataframe.empty or category not in dataframe.columns or value not in dataframe.columns:
        st.info("No data is available for this chart.")
        return
    chart_data = dataframe[[category, value]].copy().head(22)
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=7, cornerRadiusBottomRight=7, color=color, opacity=0.86)
        .encode(x=alt.X(f"{value}:Q", title=None), y=alt.Y(f"{category}:N", sort="-x", title=None), tooltip=[category, alt.Tooltip(f"{value}:Q", format=",")])
        .properties(height=CHART_HEIGHT, title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_donut(dataframe: pd.DataFrame, category: str, value: str, title: str) -> None:
    if dataframe.empty:
        st.info("No data is available for this chart.")
        return
    chart = (
        alt.Chart(dataframe)
        .mark_arc(innerRadius=82, outerRadius=132, stroke="#07111f", strokeWidth=2)
        .encode(theta=alt.Theta(f"{value}:Q"), color=alt.Color(f"{category}:N", scale=alt.Scale(range=PALETTE), legend=alt.Legend(title=None)), tooltip=[category, alt.Tooltip(f"{value}:Q", format=",")])
        .properties(height=CHART_HEIGHT, title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_time_space_intelligence(gps: pd.DataFrame) -> None:
    pairwise = build_pairwise_distances(gps)
    movements = build_surveyor_movement_table(gps)
    duration_table = gps[
        [
            "Point",
            "Display Class",
            "Surveyor",
            "Region",
            "Province",
            "District",
            "Start Timestamp",
            "End Timestamp",
            "Form Duration (min)",
            "Form Duration",
            "accuracy",
        ]
    ].copy()
    duration_table["Accuracy (m)"] = pd.to_numeric(duration_table["accuracy"], errors="coerce").round(1)
    duration_table = duration_table.drop(columns=["accuracy"]).sort_values("Form Duration (min)", ascending=False, na_position="last")

    tabs = st.tabs(["Every Point", "Surveyor Movement", "Form Timing", "Quality"])
    with tabs[0]:
        st.markdown("### Distance and Time Between Every GPS Point")
        if pairwise.empty:
            st.info("At least two GPS points are required.")
        else:
            view_columns = [
                "Point A",
                "Point B",
                "Class A",
                "Class B",
                "Surveyor A",
                "Surveyor B",
                "Distance",
                "Distance (m)",
                "Time Difference",
                "Time Difference (min)",
                "Accuracy A (m)",
                "Accuracy B (m)",
                "Average Accuracy (m)",
                "Province",
                "District",
            ]
            st.dataframe(pairwise[[column for column in view_columns if column in pairwise.columns]].head(8000), use_container_width=True, hide_index=True, height=460)
            st.download_button(
                "Download every-point distance table",
                pairwise.to_csv(index=False).encode("utf-8-sig"),
                file_name="gps_every_point_distance_time.csv",
                mime="text/csv",
            )

    with tabs[1]:
        st.markdown("### Same-Surveyor Movement From One Point to Next")
        if movements.empty:
            st.info("No same-surveyor movement sequence is available.")
        else:
            movement_summary = (
                movements.groupby("Surveyor")
                .agg(
                    Moves=("To Point", "count"),
                    **{
                        "Total Distance (km)": ("Travel Distance (km)", "sum"),
                        "Median Travel Time (min)": ("Travel Time (min)", "median"),
                        "Median Speed (km/h)": ("Approx Speed (km/h)", "median"),
                    },
                )
                .reset_index()
                .sort_values("Total Distance (km)", ascending=False)
            )
            top_left, top_right = st.columns(2, gap="large")
            with top_left:
                render_bar_chart(movement_summary, "Surveyor", "Total Distance (km)", "Surveyor Travel Distance")
            with top_right:
                signal_mix = movements.groupby("Signal").size().reset_index(name="Count")
                render_donut(signal_mix, "Signal", "Count", "Movement QA Signals")
            st.dataframe(movements, use_container_width=True, hide_index=True, height=420)
            st.download_button(
                "Download surveyor movement table",
                movements.to_csv(index=False).encode("utf-8-sig"),
                file_name="gps_surveyor_movement.csv",
                mime="text/csv",
            )

    with tabs[2]:
        st.markdown("### Form Completion Time")
        duration_values = pd.to_numeric(duration_table["Form Duration (min)"], errors="coerce").dropna()
        if duration_values.empty:
            st.info("No valid start/end time is available to calculate form duration.")
        else:
            duration_summary = (
                duration_table.dropna(subset=["Form Duration (min)"])
                .groupby("Surveyor")
                .agg(Forms=("Point", "count"), **{"Median Form Duration (min)": ("Form Duration (min)", "median")})
                .reset_index()
                .sort_values("Median Form Duration (min)", ascending=False)
            )
            render_bar_chart(duration_summary, "Surveyor", "Median Form Duration (min)", "Median Form Duration by Surveyor", "#22c55e")
            st.dataframe(duration_table, use_container_width=True, hide_index=True, height=420)
            st.download_button(
                "Download form duration table",
                duration_table.to_csv(index=False).encode("utf-8-sig"),
                file_name="gps_form_duration.csv",
                mime="text/csv",
            )

    with tabs[3]:
        st.markdown("### Accuracy and Movement Quality")
        flags = build_quality_flags(gps)
        if not movements.empty:
            movement_flags = movements[movements["Signal"] != "OK"].copy()
            if not movement_flags.empty:
                movement_flags = movement_flags.rename(columns={"From Point": "Point", "To Class": "Class"})
                movement_flags["Detail"] = movement_flags["Travel Distance"] + " / " + movement_flags["Travel Time"]
                movement_flags = movement_flags[["Signal", "Point", "Class", "Detail"]]
                flags = pd.concat([flags, movement_flags], ignore_index=True) if not flags.empty else movement_flags
        if flags.empty:
            st.info("No weak accuracy, duplicate coordinate, missing geography, or movement risk flags were found.")
        else:
            flag_mix = flags.groupby("Signal").size().reset_index(name="Count")
            render_donut(flag_mix, "Signal", "Count", "GPS QA Flag Mix")
            st.dataframe(flags, use_container_width=True, hide_index=True, height=360)


def render_gps_dashboard(gps: pd.DataFrame, records: list[dict[str, Any]]) -> None:
    filtered = apply_gps_filters(gps)
    if filtered.empty:
        st.warning("No GPS points match the selected Region, Province, and District filters.")
        return

    accuracy_values = pd.to_numeric(filtered["accuracy"], errors="coerce").dropna()
    weak_count = int((pd.to_numeric(filtered["accuracy"], errors="coerce") > 50).sum())
    duration_values = pd.to_numeric(filtered["Form Duration (min)"], errors="coerce").dropna()
    movement_table = build_surveyor_movement_table(filtered)
    travel_gaps = pd.to_numeric(movement_table["Travel Time (min)"], errors="coerce").dropna() if not movement_table.empty else pd.Series(dtype=float)
    metric_cols = st.columns(5, gap="small")
    with metric_cols[0]:
        render_metric_card("GPS Points", f"{len(filtered):,}", "Clean GPS points.", "#38bdf8")
    with metric_cols[1]:
        median_accuracy = f"{accuracy_values.median():.1f}m" if not accuracy_values.empty else "N/A"
        render_metric_card("Median Accuracy", median_accuracy, "GPS precision.", "#22c55e")
    with metric_cols[2]:
        render_metric_card("Weak Accuracy", f"{weak_count:,}", ">50m accuracy.", "#f97316")
    with metric_cols[3]:
        duration_label = format_minutes(duration_values.median()) if not duration_values.empty else "N/A"
        render_metric_card("Median Form Time", duration_label, "Start to end.", "#8b5cf6")
    with metric_cols[4]:
        travel_label = format_minutes(travel_gaps.median()) if not travel_gaps.empty else "N/A"
        render_metric_card("Median Move Gap", travel_label, "Same surveyor.", "#0f766e")

    st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)
    map_label, map_type_col = st.columns([1.5, 0.7], gap="large")
    with map_label:
        render_glass_section("GPS Track Map", "Point-to-point distance is measured directly inside the map: click one GPS point, then move the pointer over another point.")
    with map_type_col:
        map_type = st.radio("Map type", ["Dark", "Satellite"], horizontal=True, key="gps-track-map-type")
    render_gps_map(filtered, map_type, pd.DataFrame())

    st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)
    with st.expander("Time, distance, accuracy, and surveyor movement intelligence", expanded=True):
        render_time_space_intelligence(filtered)

    st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)
    with st.expander("GPS Point Register", expanded=False):
        table = filtered.copy()
        table["Latitude"] = table["lat"].round(6)
        table["Longitude"] = table["lon"].round(6)
        table["Altitude (m)"] = pd.to_numeric(table["altitude"], errors="coerce").round(1)
        table["Accuracy (m)"] = pd.to_numeric(table["accuracy"], errors="coerce").round(1)
        columns = [
            "Point",
            "Dataset",
            "Source Row",
            "Latitude",
            "Longitude",
            "Altitude (m)",
            "Accuracy (m)",
            "Accuracy Band",
            "GPS Time",
            "Start Timestamp",
            "End Timestamp",
            "Form Duration",
            "Form Duration (min)",
            "Reviewer",
            "Region",
            "Province",
            "District",
            "Village",
            "Surveyor",
            "Surveyor ID",
            "TPM ID",
            "Class ID",
            "Class Type",
        ]
        st.dataframe(table[[column for column in columns if column in table.columns]], use_container_width=True, hide_index=True, height=460)


apply_liquid_glass_theme(
    "GPS Track",
    "A standalone smart GIS workspace for clean GPS points, satellite mapping, point-to-point distance measurement, and field quality intelligence.",
    accent="#38bdf8",
    eyebrow_label="GPS Track",
    compact_hero=True,
)

uploaded_files = st.file_uploader("Upload GPS datasets", type=["csv", "xlsx", "xls"], accept_multiple_files=True)
available_local_datasets = {name: path for name, path in LOCAL_DATASET_PATHS.items() if path.exists()}
use_local_datasets = False
if available_local_datasets:
    use_local_datasets = st.checkbox("Use local TLS datasets", value=not uploaded_files)

records, processing_errors = load_dataset_records(uploaded_files, use_local_datasets)
if processing_errors:
    st.warning("Some datasets could not be processed: " + " | ".join(processing_errors))

if not records:
    st.info("Upload datasets, or enable local TLS datasets, to start GPS tracking.")
    st.stop()

gps_points = combine_gps(records)
if gps_points.empty:
    st.info("No valid GPS coordinates were found after rejected rows were excluded.")
    st.stop()

render_gps_dashboard(gps_points, records)
