import re

import altair as alt
import pandas as pd
import streamlit as st

from services.google_sheets import (
    append_dataframe_to_worksheet,
    GoogleSheetsConnectionError,
    get_worksheet_column_values,
    update_summary_timestamp,
)
from services.ui_theme import apply_liquid_glass_theme, render_glass_section
from services.surveycto import fetch_form_dataframe


TARGET_WORKSHEET = "QA_Log"
SURVEYCTO_DATASETS = [
    {"display_name": "Tool 2 ECE Classroom Observation", "form_id": "ECE_Tool2_Classroom_Observation"},
    {"display_name": "Tool 3 ECE Parent Interview", "form_id": "ECE_Tool3_Parent_Interview"},
    {"display_name": "Tool 5 TLS Classroom Observation", "form_id": "TLS_Tool5_Classroom_Observation"},
]
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
CHART_FONT = "Manrope"
CHART_TEXT = "#dbe7ff"
CHART_MUTED = "#93a4c4"
CHART_GRID = "rgba(219, 231, 255, 0.12)"
CHART_HEIGHT = 360
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


def count_unique(dataframe: pd.DataFrame, column_name: str) -> int:
    if dataframe.empty or column_name not in dataframe.columns:
        return 0
    values = dataframe[column_name].astype(str).str.strip()
    return int(values[values != ""].nunique())


def top_counts(dataframe: pd.DataFrame, column_name: str, limit: int = 12) -> pd.DataFrame:
    if dataframe.empty or column_name not in dataframe.columns:
        return pd.DataFrame(columns=[column_name, "Count"])
    values = dataframe[column_name].astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return pd.DataFrame(columns=[column_name, "Count"])
    counts = values.value_counts().head(limit).reset_index()
    counts.columns = [column_name, "Count"]
    return counts


def padded_numeric_domain(values: pd.Series, padding: float = 0.22, minimum: float = 1) -> list[float]:
    numeric_values = pd.to_numeric(values, errors="coerce").fillna(0)
    max_value = float(numeric_values.max()) if not numeric_values.empty else 0
    return [0, max(max_value * (1 + padding), minimum)]


def modernize_chart(chart: alt.TopLevelMixin) -> alt.TopLevelMixin:
    return (
        chart.configure(background="transparent")
        .configure_view(strokeOpacity=0)
        .configure_title(font=CHART_FONT, fontSize=16, fontWeight=800, color=CHART_TEXT, anchor="start", offset=16)
        .configure_axis(
            labelFont=CHART_FONT,
            titleFont=CHART_FONT,
            labelColor=CHART_MUTED,
            titleColor=CHART_MUTED,
            gridColor=CHART_GRID,
            domainColor="rgba(219, 231, 255, 0.18)",
            tickColor="rgba(219, 231, 255, 0.16)",
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
            symbolType="circle",
            symbolSize=90,
        )
    )


def render_luxury_metric(title: str, value: str, subtitle: str, tone: str) -> None:
    st.markdown(
        f"""
        <div style="
            position:relative; overflow:hidden; min-height:154px; padding:17px 18px;
            border-radius:16px; border:1px solid rgba(226,232,240,0.18);
            background:linear-gradient(145deg,rgba(255,255,255,0.15),rgba(255,255,255,0.04)),linear-gradient(135deg,rgba(10,18,37,0.96),rgba(3,8,20,0.92));
            box-shadow:0 22px 58px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.18);
            backdrop-filter:blur(24px) saturate(150%); -webkit-backdrop-filter:blur(24px) saturate(150%);
        ">
            <div style="position:absolute; left:0; right:0; top:0; height:3px; background:linear-gradient(90deg,{tone},rgba(255,255,255,0.82),transparent);"></div>
            <div style="position:absolute; right:14px; top:14px; width:34px; height:34px; border-radius:11px; background:linear-gradient(145deg,{tone},rgba(255,255,255,0.10)); box-shadow:0 0 28px color-mix(in srgb,{tone} 42%,transparent);"></div>
            <div style="position:relative; z-index:1; max-width:calc(100% - 48px); color:#b9c8e7; font-size:0.72rem; letter-spacing:0.14em; text-transform:uppercase; font-weight:900;">{title}</div>
            <div style="position:relative; z-index:1; margin-top:18px; color:#f8fbff; font-size:clamp(1.75rem,2vw,2.3rem); line-height:1; font-weight:900; overflow-wrap:anywhere;">{value}</div>
            <div style="position:relative; z-index:1; margin-top:16px; padding-top:11px; border-top:1px solid rgba(226,232,240,0.12); color:#a9b8d6; font-size:0.82rem; line-height:1.45; font-weight:600;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_bar_chart(dataframe: pd.DataFrame, category: str, title: str, color: str, height: int = CHART_HEIGHT) -> None:
    if dataframe.empty or "Count" not in dataframe.columns:
        st.info("No data is available for this chart.")
        return
    chart_data = dataframe.copy()
    chart_data["Count"] = pd.to_numeric(chart_data["Count"], errors="coerce").fillna(0)
    chart_data = chart_data[chart_data["Count"] > 0]
    if chart_data.empty:
        st.info("No data is available for this chart.")
        return
    x_domain = padded_numeric_domain(chart_data["Count"], padding=0.28)
    base = alt.Chart(chart_data).encode(
        x=alt.X("Count:Q", title="Rows", scale=alt.Scale(domain=x_domain)),
        y=alt.Y(f"{category}:N", sort="-x", title=None),
        tooltip=[alt.Tooltip(f"{category}:N", title=category), alt.Tooltip("Count:Q", format=",")],
    )
    bars = base.mark_bar(cornerRadiusTopRight=9, cornerRadiusBottomRight=9, color=color, opacity=0.86)
    glow = base.mark_bar(cornerRadiusTopRight=9, cornerRadiusBottomRight=9, color=color, opacity=0.18, size=24)
    labels = base.mark_text(align="left", baseline="middle", dx=8, color=CHART_TEXT, font=CHART_FONT, fontSize=11, fontWeight=800).encode(
        text=alt.Text("Count:Q", format=",")
    )
    st.altair_chart(modernize_chart(alt.layer(glow, bars, labels).properties(height=height, title=title)), use_container_width=True)


def render_donut_chart(dataframe: pd.DataFrame, category: str, title: str, colors: list[str]) -> None:
    if dataframe.empty or "Count" not in dataframe.columns:
        st.info("No data is available for this chart.")
        return
    chart_data = dataframe.copy()
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
            color=alt.Color(f"{category}:N", scale=alt.Scale(range=colors), legend=alt.Legend(title=category)),
            tooltip=[f"{category}:N", alt.Tooltip("Count:Q", format=","), alt.Tooltip("Share:Q", format=".1%")],
        )
    )
    center = alt.Chart(pd.DataFrame({"Total": [f"{total:,}"]})).mark_text(
        font=CHART_FONT, fontSize=25, fontWeight=900, color=CHART_TEXT, dy=-4
    ).encode(text="Total:N")
    st.altair_chart(modernize_chart(alt.layer(arc, center).properties(height=CHART_HEIGHT, title=title)), use_container_width=True)


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


def extract_tool_name(source_name: str) -> str:
    match = re.search(r"(Tool\s*\d+)", source_name, flags=re.IGNORECASE)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).title()
    return source_name


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
    "Load datasets directly from SurveyCTO and append only new validated rows into QA_Log.",
    accent="#f59e0b",
)

render_glass_section(
    "SurveyCTO Import Workflow",
    "Load Tool 2, Tool 3, and Tool 5 directly from SurveyCTO, then append only new keys to QA_Log.",
)

transformed_datasets: list[tuple[str, pd.DataFrame]] = []
processing_errors: list[str] = []
file_profile_rows: list[dict[str, object]] = []

for dataset_meta in SURVEYCTO_DATASETS:
    try:
        source_df = fetch_form_dataframe(dataset_meta["form_id"]).fillna("")
        transformed = transform_dataset(source_df, dataset_meta["display_name"])
        transformed_datasets.append((dataset_meta["display_name"], transformed))
        file_profile_rows.append(
            {
                "Dataset": dataset_meta["display_name"],
                "Form ID": dataset_meta["form_id"],
                "Tool Name": extract_tool_name(dataset_meta["display_name"]),
                "Source Rows": len(source_df),
                "Valid KEY Rows": int(transformed["KEY"].astype(str).str.strip().ne("").sum()),
                "Missing KEY Rows": int(transformed["KEY"].astype(str).str.strip().eq("").sum()),
                "Unique Keys": count_unique(transformed, "KEY"),
            }
        )
    except Exception as exc:
        processing_errors.append(f"{dataset_meta['display_name']} ({dataset_meta['form_id']}): {exc}")

consolidated_rows = consolidate_uploaded_rows(transformed_datasets)
file_profile = pd.DataFrame(file_profile_rows)

try:
    existing_keys = {
        key.strip()
        for key in get_worksheet_column_values(TARGET_WORKSHEET, "KEY")
        if key.strip()
    }
except GoogleSheetsConnectionError as exc:
    st.error(str(exc))
    st.stop()

rows_to_add = consolidated_rows[~consolidated_rows["KEY"].isin(existing_keys)].copy() if not consolidated_rows.empty else pd.DataFrame(columns=TARGET_COLUMNS)
duplicate_rows = len(consolidated_rows) - len(rows_to_add) if not consolidated_rows.empty else 0

metric_cols = st.columns(4, gap="large")
with metric_cols[0]:
    render_luxury_metric("SurveyCTO datasets", f"{len(SURVEYCTO_DATASETS):,}", f"Loaded successfully: {len(transformed_datasets):,}.", "#2563eb")
with metric_cols[1]:
    render_luxury_metric("Consolidated rows", f"{len(consolidated_rows):,}", "Unique KEY rows after cross-dataset consolidation.", "#8b5cf6")
with metric_cols[2]:
    render_luxury_metric("New QA_Log rows", f"{len(rows_to_add):,}", f"Existing duplicate keys skipped: {duplicate_rows:,}.", "#22c55e")
with metric_cols[3]:
    missing_keys = int(file_profile["Missing KEY Rows"].sum()) if not file_profile.empty else 0
    render_luxury_metric("Missing KEY rows", f"{missing_keys:,}", f"Processing errors: {len(processing_errors):,}.", "#f97316")

if processing_errors:
    st.warning("Some datasets could not be processed: " + " | ".join(processing_errors))

st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

profile_left, profile_right = st.columns(2, gap="large")
with profile_left:
    render_bar_chart(file_profile.rename(columns={"Source Rows": "Count"}), "Dataset", "SurveyCTO Dataset Volume", "#38bdf8")
with profile_right:
    render_donut_chart(top_counts(consolidated_rows, "Tool Name", 10), "Tool Name", "Tool Mix Ready for QA_Log", ["#2563eb", "#22c55e", "#f97316", "#8b5cf6", "#0f766e", "#ef4444"])

st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

table_left, table_right = st.columns(2, gap="large")
with table_left:
    st.markdown("### Dataset Quality Profile")
    if file_profile.empty:
        st.info("No dataset profile is available.")
    else:
        st.dataframe(file_profile, use_container_width=True, hide_index=True, height=460)

with table_right:
    st.markdown("### Rows Ready To Append")
    if rows_to_add.empty:
        st.info("No new rows are ready to append.")
    else:
        st.dataframe(rows_to_add[TARGET_COLUMNS], use_container_width=True, hide_index=True, height=460)

if not consolidated_rows.empty:
    if st.button(f"Add Data To {TARGET_WORKSHEET}", type="primary"):
        if processing_errors:
            st.error("Some SurveyCTO datasets could not be processed.")
            st.stop()
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
    st.error("SurveyCTO datasets could not be processed.")
else:
    st.info("No rows were returned from SurveyCTO yet.")
