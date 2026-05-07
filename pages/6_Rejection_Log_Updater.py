from __future__ import annotations

from collections import OrderedDict

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


QA_LOG_SHEET = "QA_Log"
REJECTION_LOG_SHEET = "Rejection_Log"
TARGET_COLUMNS = [
    "KEY",
    "Tool Name",
    "TPM-ID (ECE, TLS)",
    "Surveyor_Name",
    "Province",
    "District",
    "Rejected_by",
    "Rejection Reason",
]
CHART_FONT = "Manrope"
CHART_TEXT = "#dbe7ff"
CHART_MUTED = "#93a4c4"
CHART_GRID = "rgba(219, 231, 255, 0.12)"
CHART_HEIGHT = 360


def to_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_status(value: object) -> str:
    text = " ".join(to_text(value).lower().split())
    if "reject" in text:
        return "rejected"
    return text


def first_existing_column(dataframe: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {str(column).strip().lower(): column for column in dataframe.columns}
    for candidate in candidates:
        column = lookup.get(candidate.strip().lower())
        if column is not None:
            return column
    return None


def column_value(row: pd.Series, column_name: str | None) -> str:
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


def padded_numeric_domain(values: pd.Series, padding: float = 0.18, minimum: float = 1) -> list[float]:
    numeric_values = pd.to_numeric(values, errors="coerce").fillna(0)
    max_value = float(numeric_values.max()) if not numeric_values.empty else 0
    return [0, max(max_value * (1 + padding), minimum)]


def modernize_chart(chart: alt.TopLevelMixin) -> alt.TopLevelMixin:
    return (
        chart
        .configure(background="transparent")
        .configure_view(strokeOpacity=0)
        .configure_title(
            font=CHART_FONT,
            fontSize=16,
            fontWeight=800,
            color=CHART_TEXT,
            anchor="start",
            offset=16,
        )
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
            position:relative;
            overflow:hidden;
            min-height:154px;
            padding:17px 18px;
            border-radius:16px;
            border:1px solid rgba(226,232,240,0.18);
            background:
                linear-gradient(145deg, rgba(255,255,255,0.15), rgba(255,255,255,0.04)),
                linear-gradient(135deg, rgba(10,18,37,0.96), rgba(3,8,20,0.92));
            box-shadow:0 22px 58px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.18);
            backdrop-filter:blur(24px) saturate(150%);
            -webkit-backdrop-filter:blur(24px) saturate(150%);
        ">
            <div style="position:absolute; inset:0 auto auto 0; width:100%; height:3px; background:linear-gradient(90deg,{tone},rgba(255,255,255,0.82),transparent);"></div>
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
        x=alt.X("Count:Q", title="Rejected rows", scale=alt.Scale(domain=x_domain)),
        y=alt.Y(f"{category}:N", sort="-x", title=None),
        tooltip=[alt.Tooltip(f"{category}:N", title=category), alt.Tooltip("Count:Q", format=",")],
    )
    bars = base.mark_bar(cornerRadiusTopRight=9, cornerRadiusBottomRight=9, color=color, opacity=0.86)
    glow = base.mark_bar(cornerRadiusTopRight=9, cornerRadiusBottomRight=9, color=color, opacity=0.18, size=24)
    dots = base.mark_circle(size=76, color="#f8fafc", opacity=0.9).encode(x="Count:Q")
    labels = base.mark_text(align="left", baseline="middle", dx=8, color=CHART_TEXT, font=CHART_FONT, fontSize=11, fontWeight=800).encode(
        text=alt.Text("Count:Q", format=",")
    )
    st.altair_chart(modernize_chart(alt.layer(glow, bars, dots, labels).properties(height=height, title=title)), use_container_width=True)


def render_donut_chart(dataframe: pd.DataFrame, category: str, title: str, colors: list[str], height: int = CHART_HEIGHT) -> None:
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
    center = alt.Chart(pd.DataFrame({"Total": [f"{total:,}"], "Label": ["rejected"]})).mark_text(
        font=CHART_FONT, fontSize=25, fontWeight=900, color=CHART_TEXT, dy=-6
    ).encode(text="Total:N")
    center_label = alt.Chart(pd.DataFrame({"Label": ["rejected"]})).mark_text(
        font=CHART_FONT, fontSize=11, fontWeight=800, color=CHART_MUTED, dy=20
    ).encode(text="Label:N")
    st.altair_chart(modernize_chart(alt.layer(arc, center, center_label).properties(height=height, title=title)), use_container_width=True)


def render_reason_tool_matrix(dataframe: pd.DataFrame) -> None:
    if dataframe.empty or not {"Tool Name", "Rejection Reason"}.issubset(dataframe.columns):
        st.info("No tool/reason matrix is available.")
        return
    matrix = dataframe.copy()
    matrix["Tool Name"] = matrix["Tool Name"].astype(str).str.strip()
    matrix["Rejection Reason"] = matrix["Rejection Reason"].astype(str).str.strip()
    matrix = matrix[(matrix["Tool Name"] != "") & (matrix["Rejection Reason"] != "")]
    if matrix.empty:
        st.info("No tool/reason matrix is available.")
        return
    matrix = matrix.groupby(["Tool Name", "Rejection Reason"]).size().reset_index(name="Count")
    chart = (
        alt.Chart(matrix)
        .mark_rect(cornerRadius=5)
        .encode(
            x=alt.X("Tool Name:N", title=None),
            y=alt.Y("Rejection Reason:N", title=None),
            color=alt.Color("Count:Q", scale=alt.Scale(scheme="reds"), title="Rejected"),
            tooltip=["Tool Name:N", "Rejection Reason:N", alt.Tooltip("Count:Q", format=",")],
        )
        .properties(height=CHART_HEIGHT, title="Rejection Reason x Tool Matrix")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def build_rejection_rows(qa_log: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if qa_log.empty:
        return pd.DataFrame(columns=TARGET_COLUMNS), 0

    status_column = first_existing_column(qa_log, ["Status"])
    if not status_column:
        return pd.DataFrame(columns=TARGET_COLUMNS), 0

    key_column = first_existing_column(qa_log, ["KEY", "Key", "key"])
    qc_by_column = first_existing_column(qa_log, ["QC By", "QC_By", "Rejected_by", "Rejected By"])
    reason_column = first_existing_column(qa_log, ["Rejection Reason", "Rejection_Reason", "Reject Reason", "Reason"])
    tool_column = first_existing_column(qa_log, ["Tool Name", "Tool_Name"])
    tpm_column = first_existing_column(qa_log, ["TPM-ID (ECE, TLS)", "TPM_ID", "TPM-ID", "TPM ID"])
    surveyor_column = first_existing_column(qa_log, ["Surveyor_Name", "Surveyor Name", "Enumerator"])
    province_column = first_existing_column(qa_log, ["Province"])
    district_column = first_existing_column(qa_log, ["District"])

    rejected = qa_log[qa_log[status_column].map(normalize_status).eq("rejected")].copy()
    skipped_blank_keys = 0
    keyed_rows: OrderedDict[str, dict[str, str]] = OrderedDict()

    for _, row in rejected.iterrows():
        key = column_value(row, key_column)
        if not key:
            skipped_blank_keys += 1
            continue

        keyed_rows[key] = {
            "KEY": key,
            "Tool Name": column_value(row, tool_column),
            "TPM-ID (ECE, TLS)": column_value(row, tpm_column),
            "Surveyor_Name": column_value(row, surveyor_column),
            "Province": column_value(row, province_column),
            "District": column_value(row, district_column),
            "Rejected_by": column_value(row, qc_by_column),
            "Rejection Reason": column_value(row, reason_column),
        }

    if not keyed_rows:
        return pd.DataFrame(columns=TARGET_COLUMNS), skipped_blank_keys
    return pd.DataFrame(list(keyed_rows.values()), columns=TARGET_COLUMNS), skipped_blank_keys


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


def sync_rejection_log(rejection_rows: pd.DataFrame, rebuild_from_qa_log: bool) -> dict[str, int]:
    worksheet = get_worksheet(REJECTION_LOG_SHEET)
    headers, existing_rows = read_sheet_values(REJECTION_LOG_SHEET)
    existing_records = rows_to_records(headers, existing_rows)

    by_key: OrderedDict[str, dict[str, str]] = OrderedDict()
    unkeyed_existing: list[dict[str, str]] = []
    if not rebuild_from_qa_log:
        for record in existing_records:
            key = to_text(record.get("KEY", ""))
            if key:
                by_key[key] = {header: to_text(record.get(header, "")) for header in headers}
            elif any(to_text(record.get(header, "")) for header in headers):
                unkeyed_existing.append({header: to_text(record.get(header, "")) for header in headers})

    inserted = 0
    updated = 0
    for _, row in rejection_rows.iterrows():
        key = to_text(row.get("KEY", ""))
        if not key:
            continue

        incoming = {header: "" for header in headers}
        incoming.update({column: to_text(row.get(column, "")) for column in TARGET_COLUMNS})
        if key in by_key:
            updated += 1
        else:
            inserted += 1
        by_key[key] = incoming

    output_records = unkeyed_existing + list(by_key.values())
    output_values = [headers]
    output_values.extend([[record.get(header, "") for header in headers] for record in output_records])

    worksheet.clear()
    worksheet.update("A1", output_values)
    clear_google_sheets_caches()

    return {
        "source_rejected": len(rejection_rows),
        "inserted": inserted,
        "updated": updated,
        "final_rows": len(output_records),
        "removed": max(len(existing_records) - len(output_records), 0) if rebuild_from_qa_log else 0,
    }


apply_liquid_glass_theme(
    "Rejection Log Updater",
    "Sync rejected QA records from QA_Log into Rejection_Log with QC ownership and rejection reason.",
    accent="#ef4444",
    compact_hero=True,
)

render_glass_section(
    "Rejection Log Sync",
    "Rows with Status = Rejected in QA_Log will update Rejection_Log. Rejected_by is filled from QC By.",
)

try:
    qa_log = load_worksheet_records(QA_LOG_SHEET).fillna("")
except GoogleSheetsConnectionError as exc:
    st.error(str(exc))
    st.stop()

rejection_rows, skipped_blank_keys = build_rejection_rows(qa_log)

metric_cols = st.columns(4, gap="large")
with metric_cols[0]:
    render_luxury_metric("QA_Log rows", f"{len(qa_log):,}", "Total QA records loaded from the source sheet.", "#2563eb")
with metric_cols[1]:
    rejection_rate = (len(rejection_rows) / len(qa_log) * 100) if len(qa_log) else 0
    render_luxury_metric("Rejected rows", f"{len(rejection_rows):,}", f"Current rejection rate: {rejection_rate:.1f}%.", "#ef4444")
with metric_cols[2]:
    render_luxury_metric("Rejected by", f"{count_unique(rejection_rows, 'Rejected_by'):,}", f"Skipped blank KEY rows: {skipped_blank_keys:,}.", "#f97316")
with metric_cols[3]:
    render_luxury_metric("Target sheet", REJECTION_LOG_SHEET, "Safe upsert by KEY into Rejection_Log.", "#8b5cf6")

st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

chart_left, chart_right = st.columns(2, gap="large")
with chart_left:
    render_bar_chart(top_counts(rejection_rows, "Rejection Reason", 12), "Rejection Reason", "Top Rejection Reasons", "#ef4444")
with chart_right:
    render_donut_chart(top_counts(rejection_rows, "Tool Name", 10), "Tool Name", "Rejected Records by Tool", ["#ef4444", "#f97316", "#8b5cf6", "#2563eb", "#0f766e", "#22c55e"])

st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

geo_left, geo_right = st.columns(2, gap="large")
with geo_left:
    render_bar_chart(top_counts(rejection_rows, "Province", 12), "Province", "Rejected Records by Province", "#f97316")
with geo_right:
    render_bar_chart(top_counts(rejection_rows, "Rejected_by", 12), "Rejected_by", "Rejected Records by QC", "#8b5cf6")

st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

matrix_left, matrix_right = st.columns(2, gap="large")
with matrix_left:
    render_reason_tool_matrix(rejection_rows)
with matrix_right:
    render_bar_chart(top_counts(rejection_rows, "District", 12), "District", "Rejected Records by District", "#0f766e")

st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)

preview_left, preview_right = st.columns(2, gap="large")
with preview_left:
    st.markdown("### Rejected QA Preview")
    if rejection_rows.empty:
        st.info("No rejected QA_Log rows with a valid KEY were found.")
    else:
        st.dataframe(rejection_rows, use_container_width=True, hide_index=True, height=520)

with preview_right:
    st.markdown("### Sync Options")
    rebuild_from_qa_log = st.checkbox(
        "Rebuild Rejection_Log from current QA_Log rejected rows",
        value=False,
        help="When off, the app updates or inserts rejected rows and keeps any existing Rejection_Log rows that are not in the current QA_Log rejected set.",
    )
    st.caption(
        "Default mode is safe upsert: update matching KEY rows, insert new rejected KEY rows, and keep older rows."
    )

    if st.button("Update Rejection_Log", type="primary", disabled=rejection_rows.empty):
        try:
            result = sync_rejection_log(rejection_rows, rebuild_from_qa_log)
            update_summary_timestamp("Summary")
        except GoogleSheetsConnectionError as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:
            st.error(f"Unable to update Rejection_Log: {exc}")
            st.stop()

        st.success(
            "Rejection_Log was updated successfully. "
            f"Inserted: {result['inserted']:,}; updated: {result['updated']:,}; final rows: {result['final_rows']:,}."
        )
        if rebuild_from_qa_log and result["removed"]:
            st.info(f"Rows removed during rebuild: {result['removed']:,}.")
