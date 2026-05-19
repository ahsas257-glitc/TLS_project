from __future__ import annotations

from collections import OrderedDict
import re

import altair as alt
import pandas as pd
import streamlit as st

from services.google_sheets import (
    GoogleSheetsConnectionError,
    clear_google_sheets_caches,
    get_worksheet,
    load_worksheet_records,
    update_summary_timestamp,
)
from services.ui_theme import apply_liquid_glass_theme, render_glass_section
from services.surveycto import fetch_form_dataframe


QA_LOG_SHEET = "QA_Log"
CALL_BACK_SHEET = "Call-Back"
TARGET_COLUMNS = [
    "KEY",
    "Surveyor_Name",
    "Province",
    "District",
    "Resp_phone",
    "Resp_name",
    "Question",
    "Old_Value",
    "Verified",
    "Tool Name",
    "Remarks",
    "Call_Back By",
]
CHART_FONT = "Manrope"
CHART_TEXT = "#dbe7ff"
CHART_MUTED = "#93a4c4"
CHART_GRID = "rgba(219, 231, 255, 0.12)"
CHART_HEIGHT = 360
SURVEYCTO_DATASETS = [
    {"display_name": "Tool 2 ECE Classroom Observation", "form_id": "ECE_Tool2_Classroom_Observation"},
    {"display_name": "Tool 3 ECE Parent Interview", "form_id": "ECE_Tool3_Parent_Interview"},
    {"display_name": "Tool 5 TLS Classroom Observation", "form_id": "TLS_Tool5_Classroom_Observation"},
]


def to_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", to_text(value).lower())


def is_true(value: object) -> bool:
    text = to_text(value).lower()
    return text in {"true", "yes", "y", "1", "checked", "tick", "ticked", "بله"} or value is True


def first_existing_column(dataframe: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {normalize_name(column): column for column in dataframe.columns}
    for candidate in candidates:
        column = lookup.get(normalize_name(candidate))
        if column is not None:
            return column
    return None


def value_from_row(row: pd.Series, column_name: str | None) -> str:
    if not column_name:
        return ""
    return to_text(row.get(column_name, ""))


def count_unique(dataframe: pd.DataFrame, column_name: str) -> int:
    if dataframe.empty or column_name not in dataframe.columns:
        return 0
    values = dataframe[column_name].astype(str).str.strip()
    return int(values[values != ""].nunique())


def top_counts(dataframe: pd.DataFrame, column_name: str, limit: int = 12) -> pd.DataFrame:
    if dataframe.empty or column_name not in dataframe.columns:
        return pd.DataFrame(columns=[column_name, "Count"])
    series = dataframe[column_name].astype(str).str.strip()
    series = series[series != ""]
    if series.empty:
        return pd.DataFrame(columns=[column_name, "Count"])
    counts = series.value_counts().head(limit).reset_index()
    counts.columns = [column_name, "Count"]
    return counts


def padded_numeric_domain(values: pd.Series, padding: float = 0.2, minimum: float = 1) -> list[float]:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0)
    max_value = float(numeric.max()) if not numeric.empty else 0
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
        x=alt.X("Count:Q", title="Call-back rows", scale=alt.Scale(domain=x_domain)),
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


def build_dataset_index() -> tuple[dict[str, dict[str, str]], list[str], list[str]]:
    dataset_index: OrderedDict[str, dict[str, str]] = OrderedDict()
    dataset_columns: OrderedDict[str, None] = OrderedDict()
    errors: list[str] = []

    for dataset_meta in SURVEYCTO_DATASETS:
        try:
            dataframe = fetch_form_dataframe(dataset_meta["form_id"]).fillna("")
            if dataframe.empty:
                errors.append(f"{dataset_meta['display_name']}: no rows found in SurveyCTO.")
                continue

            key_column = first_existing_column(dataframe, ["KEY", "Key", "key", "_uuid", "uuid", "instanceid", "InstanceID"])
            if not key_column:
                errors.append(f"{dataset_meta['display_name']}: KEY column was not found.")
                continue

            for column in dataframe.columns:
                dataset_columns[to_text(column)] = None

            for _, row in dataframe.iterrows():
                key = value_from_row(row, key_column)
                if not key:
                    continue
                current = dataset_index.setdefault(key, {})
                for column in dataframe.columns:
                    value = value_from_row(row, column)
                    if value and not current.get(to_text(column)):
                        current[to_text(column)] = value
        except Exception as exc:
            errors.append(f"{dataset_meta['display_name']} ({dataset_meta['form_id']}): {exc}")
    return dict(dataset_index), list(dataset_columns.keys()), errors


def get_dataset_value(dataset_record: dict[str, str], label: str) -> str:
    if not label:
        return ""
    if label in dataset_record:
        return to_text(dataset_record[label])
    wanted = normalize_name(label)
    for column, value in dataset_record.items():
        if normalize_name(column) == wanted:
            return to_text(value)
    return ""


def get_field(row: pd.Series, qa_column: str | None, dataset_record: dict[str, str], candidates: list[str]) -> str:
    qa_value = value_from_row(row, qa_column)
    if qa_value:
        return qa_value
    for candidate in candidates:
        value = get_dataset_value(dataset_record, candidate)
        if value:
            return value
    return ""


def build_call_back_rows(qa_log: pd.DataFrame, dataset_index: dict[str, dict[str, str]]) -> tuple[pd.DataFrame, int]:
    if qa_log.empty:
        return pd.DataFrame(columns=TARGET_COLUMNS), 0

    callback_column = first_existing_column(qa_log, ["Call_back", "Call Back", "Callback", "Call_Back"])
    if not callback_column:
        return pd.DataFrame(columns=TARGET_COLUMNS), 0

    key_column = first_existing_column(qa_log, ["KEY", "Key", "key"])
    tool_column = first_existing_column(qa_log, ["Tool Name", "Tool_Name"])
    surveyor_column = first_existing_column(qa_log, ["Surveyor_Name", "Surveyor Name", "Enumerator"])
    province_column = first_existing_column(qa_log, ["Province"])
    district_column = first_existing_column(qa_log, ["District"])
    qc_by_column = first_existing_column(qa_log, ["QC By", "QC_By", "Call_Back By", "Call Back By"])
    question_column = first_existing_column(qa_log, ["Question", "Call_Back Question", "Call Back Question", "Label", "Field"])
    verified_column = first_existing_column(qa_log, ["Verified"])
    remarks_column = first_existing_column(qa_log, ["Remarks", "Remark", "Comment", "Comments"])
    phone_column = first_existing_column(qa_log, ["Resp_phone", "Resp Phone", "Respondent Phone", "Phone", "Phone_Number"])
    name_column = first_existing_column(qa_log, ["Resp_name", "Resp Name", "Respondent Name", "Name"])

    callback_rows = qa_log[qa_log[callback_column].map(is_true)].copy()
    skipped_blank_keys = 0
    rows: list[dict[str, str]] = []
    for _, row in callback_rows.iterrows():
        key = value_from_row(row, key_column)
        if not key:
            skipped_blank_keys += 1
            continue
        dataset_record = dataset_index.get(key, {})
        question = value_from_row(row, question_column)
        rows.append(
            {
                "KEY": key,
                "Surveyor_Name": get_field(row, surveyor_column, dataset_record, ["Surveyor_Name", "Surveyor Name", "enumerator", "Enumerator", "username"]),
                "Province": get_field(row, province_column, dataset_record, ["Province", "province"]),
                "District": get_field(row, district_column, dataset_record, ["District", "district"]),
                "Resp_phone": get_field(row, phone_column, dataset_record, ["Resp_phone", "Resp Phone", "Respondent Phone", "phone", "Phone", "Phone_Number", "resp_phone"]),
                "Resp_name": get_field(row, name_column, dataset_record, ["Resp_name", "Resp Name", "Respondent Name", "respondent_name", "Name"]),
                "Question": question,
                "Old_Value": get_dataset_value(dataset_record, question),
                "Verified": value_from_row(row, verified_column),
                "Tool Name": value_from_row(row, tool_column),
                "Remarks": value_from_row(row, remarks_column),
                "Call_Back By": value_from_row(row, qc_by_column),
            }
        )
    return pd.DataFrame(rows, columns=TARGET_COLUMNS), skipped_blank_keys


def refresh_old_values(rows: pd.DataFrame, dataset_index: dict[str, dict[str, str]]) -> pd.DataFrame:
    refreshed = rows.copy().fillna("").astype(str)
    if refreshed.empty:
        return refreshed
    refreshed["Old_Value"] = refreshed.apply(
        lambda row: get_dataset_value(dataset_index.get(to_text(row.get("KEY", "")), {}), to_text(row.get("Question", ""))),
        axis=1,
    )
    return refreshed[TARGET_COLUMNS]


def read_sheet_values(worksheet_name: str) -> tuple[list[str], list[list[str]]]:
    worksheet = get_worksheet(worksheet_name)
    values = worksheet.get_all_values()
    if not values:
        return TARGET_COLUMNS.copy(), []
    headers = [to_text(value) for value in values[0]]
    rows = values[1:]
    for column in TARGET_COLUMNS:
        if column not in headers:
            headers.append(column)
    return headers, rows


def rows_to_records(headers: list[str], rows: list[list[str]]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row in rows:
        record = {}
        for index, header in enumerate(headers):
            record[header] = to_text(row[index]) if index < len(row) else ""
        if any(record.values()):
            records.append(record)
    return records


def callback_identity(record: dict[str, str]) -> str:
    key = to_text(record.get("KEY", ""))
    question = normalize_name(record.get("Question", ""))
    return f"{key}::{question}"


def sync_call_back_sheet(call_back_rows: pd.DataFrame, rebuild_from_qa_log: bool) -> dict[str, int]:
    worksheet = get_worksheet(CALL_BACK_SHEET)
    headers, existing_rows = read_sheet_values(CALL_BACK_SHEET)
    existing_records = rows_to_records(headers, existing_rows)

    by_identity: OrderedDict[str, dict[str, str]] = OrderedDict()
    unkeyed_existing: list[dict[str, str]] = []
    if not rebuild_from_qa_log:
        for record in existing_records:
            identity = callback_identity(record)
            if identity.strip(":"):
                by_identity[identity] = {header: to_text(record.get(header, "")) for header in headers}
            else:
                unkeyed_existing.append({header: to_text(record.get(header, "")) for header in headers})

    inserted = 0
    updated = 0
    for _, row in call_back_rows.iterrows():
        incoming = {header: "" for header in headers}
        incoming.update({column: to_text(row.get(column, "")) for column in TARGET_COLUMNS})
        identity = callback_identity(incoming)
        if not to_text(incoming.get("KEY", "")):
            continue
        if identity in by_identity:
            updated += 1
        else:
            inserted += 1
        by_identity[identity] = incoming

    output_records = unkeyed_existing + list(by_identity.values())
    output_values = [headers]
    output_values.extend([[record.get(header, "") for header in headers] for record in output_records])
    worksheet.clear()
    worksheet.update("A1", output_values)
    clear_google_sheets_caches()
    return {
        "inserted": inserted,
        "updated": updated,
        "final_rows": len(output_records),
        "removed": max(len(existing_records) - len(output_records), 0) if rebuild_from_qa_log else 0,
    }


apply_liquid_glass_theme(
    "Call-Back Updater",
    "Import datasets, resolve old values by KEY and question label, and sync checked QA call-backs into Call-Back.",
    accent="#8b5cf6",
    compact_hero=True,
)

render_glass_section(
    "Automated Call-Back Workflow",
    "Rows with Call_back = True in QA_Log become Call-Back rows. Call_Back By is filled from QC By; Old_Value is read automatically from SurveyCTO datasets using KEY and Question.",
)

try:
    qa_log = load_worksheet_records(QA_LOG_SHEET).fillna("")
except GoogleSheetsConnectionError as exc:
    st.error(str(exc))
    st.stop()

upload_left, upload_right = st.columns(2, gap="large")
with upload_left:
    st.info("Source datasets are loaded automatically from SurveyCTO forms.")

dataset_index, dataset_columns, dataset_errors = build_dataset_index()
base_call_back_rows, skipped_blank_keys = build_call_back_rows(qa_log, dataset_index)

with upload_right:
    st.markdown("### Dataset lookup")
    st.caption("Question must match a dataset column label loaded from SurveyCTO. You can edit Question below before syncing.")
    if dataset_columns:
        st.dataframe(pd.DataFrame({"Available dataset labels": dataset_columns}), use_container_width=True, hide_index=True, height=180)
    else:
        st.info("No dataset labels were loaded from SurveyCTO.")

metric_cols = st.columns(4, gap="large")
with metric_cols[0]:
    render_luxury_metric("QA_Log rows", f"{len(qa_log):,}", "Total QA records loaded from the source sheet.", "#2563eb")
with metric_cols[1]:
    render_luxury_metric("Call-back rows", f"{len(base_call_back_rows):,}", "Rows where Call_back is checked/true.", "#8b5cf6")
with metric_cols[2]:
    render_luxury_metric("Dataset keys", f"{len(dataset_index):,}", f"Uploaded columns: {len(dataset_columns):,}.", "#22c55e")
with metric_cols[3]:
    old_value_rate = int(base_call_back_rows["Old_Value"].astype(str).str.strip().ne("").sum()) if not base_call_back_rows.empty else 0
    render_luxury_metric("Old values found", f"{old_value_rate:,}", f"Skipped blank KEY rows: {skipped_blank_keys:,}.", "#f97316")

if dataset_errors:
    st.warning("Some datasets could not be imported: " + " | ".join(dataset_errors))

st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

chart_left, chart_right = st.columns(2, gap="large")
with chart_left:
    render_bar_chart(top_counts(base_call_back_rows, "Question", 12), "Question", "Call-Back Questions", "#8b5cf6")
with chart_right:
    render_donut_chart(top_counts(base_call_back_rows, "Tool Name", 10), "Tool Name", "Call-Back by Tool", ["#8b5cf6", "#2563eb", "#f97316", "#0f766e", "#22c55e", "#ef4444"])

st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

geo_left, geo_right = st.columns(2, gap="large")
with geo_left:
    render_bar_chart(top_counts(base_call_back_rows, "Province", 12), "Province", "Call-Back by Province", "#2563eb")
with geo_right:
    render_bar_chart(top_counts(base_call_back_rows, "Call_Back By", 12), "Call_Back By", "Call-Back by QC", "#f97316")

st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

editor_left, sync_right = st.columns(2, gap="large")
with editor_left:
    st.markdown("### Call-Back Preview and Question Labels")
    if base_call_back_rows.empty:
        st.info("No QA_Log rows with Call_back = True were found.")
        edited_rows = base_call_back_rows
    else:
        edited_rows = st.data_editor(
            base_call_back_rows,
            use_container_width=True,
            hide_index=True,
            height=560,
            column_config={
                "Question": st.column_config.TextColumn(
                    "Question",
                    help="Type the dataset column label. Old_Value will be pulled from that column by KEY.",
                ),
                "Verified": st.column_config.CheckboxColumn("Verified"),
            },
            num_rows="dynamic",
            key="call_back_editor",
        )

final_rows = refresh_old_values(pd.DataFrame(edited_rows), dataset_index)

with sync_right:
    st.markdown("### Auto-filled Old Values")
    if final_rows.empty:
        st.info("No rows are ready for sync.")
    else:
        st.dataframe(final_rows[["KEY", "Question", "Old_Value", "Call_Back By"]], use_container_width=True, hide_index=True, height=310)

    rebuild_from_qa_log = st.checkbox(
        "Rebuild Call-Back from current QA_Log call-back rows",
        value=False,
        help="When off, the app updates or inserts by KEY + Question and keeps older Call-Back rows.",
    )
    ready_rows = final_rows[final_rows["KEY"].astype(str).str.strip().ne("")].copy()
    missing_questions = int(ready_rows["Question"].astype(str).str.strip().eq("").sum()) if not ready_rows.empty else 0
    missing_old_values = int(ready_rows["Old_Value"].astype(str).str.strip().eq("").sum()) if not ready_rows.empty else 0
    st.caption(f"Ready rows: {len(ready_rows):,}. Missing Question: {missing_questions:,}. Missing Old_Value: {missing_old_values:,}.")

    if st.button("Update Call-Back Sheet", type="primary", disabled=ready_rows.empty):
        try:
            result = sync_call_back_sheet(ready_rows, rebuild_from_qa_log)
            update_summary_timestamp("Summary")
        except GoogleSheetsConnectionError as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:
            st.error(f"Unable to update Call-Back: {exc}")
            st.stop()

        st.success(
            "Call-Back sheet was updated successfully. "
            f"Inserted: {result['inserted']:,}; updated: {result['updated']:,}; final rows: {result['final_rows']:,}."
        )
        if rebuild_from_qa_log and result["removed"]:
            st.info(f"Rows removed during rebuild: {result['removed']:,}.")
