import altair as alt
import pandas as pd
import streamlit as st

from services.google_sheets import load_worksheet_records, load_worksheet_values
from services.ui_theme import apply_liquid_glass_theme

TLS_SHEET = "TLS-Sample"
ECE_SHEET = "ECE-Sample"
SUMMARY_SHEET = "Summary"
QA_LOG_SHEET = "QA_Log"
CORRECTION_LOG_SHEET = "Correction_Log"
REJECTION_LOG_SHEET = "Rejection_Log"
RED_FLAG_SHEET = "Red-Flag"
CALL_BACK_SHEET = "Call-Back"


@st.cache_data(ttl=120)
def load_dashboard_data() -> tuple[pd.DataFrame, pd.DataFrame, list[list[str]], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tls = load_worksheet_records(TLS_SHEET)
    ece = load_worksheet_records(ECE_SHEET)
    summary = load_worksheet_values(SUMMARY_SHEET)
    qa_log = load_worksheet_records(QA_LOG_SHEET)
    correction_log = load_worksheet_records(CORRECTION_LOG_SHEET)
    rejection_log = load_worksheet_records(REJECTION_LOG_SHEET)
    red_flag_log = load_worksheet_records(RED_FLAG_SHEET)
    callback_log = load_worksheet_records(CALL_BACK_SHEET)
    return (
        tls.fillna(""),
        ece.fillna(""),
        summary,
        qa_log.fillna(""),
        correction_log.fillna(""),
        rejection_log.fillna(""),
        red_flag_log.fillna(""),
        callback_log.fillna(""),
    )


def apply_filters(dataframe: pd.DataFrame, regions: list[str], provinces: list[str], districts: list[str]) -> pd.DataFrame:
    filtered = dataframe.copy()
    if regions and "Region" in filtered.columns:
        filtered = filtered[filtered["Region"].isin(regions)]
    if provinces and "Province" in filtered.columns:
        filtered = filtered[filtered["Province"].isin(provinces)]
    if districts and "District" in filtered.columns:
        filtered = filtered[filtered["District"].isin(districts)]
    return filtered


def count_unique(dataframe: pd.DataFrame, column_name: str) -> int:
    if column_name not in dataframe.columns:
        return 0
    series = dataframe[column_name].astype(str).str.strip()
    return series[series != ""].nunique()


def top_counts(dataframe: pd.DataFrame, column_name: str, limit: int = 10) -> pd.DataFrame:
    if column_name not in dataframe.columns:
        return pd.DataFrame(columns=[column_name, "Count"])
    series = dataframe[column_name].astype(str).str.strip()
    series = series[series != ""]
    counts = series.value_counts().head(limit).reset_index()
    counts.columns = [column_name, "Count"]
    return counts


def count_matching(dataframe: pd.DataFrame, column_name: str, expected_value: str) -> int:
    if column_name not in dataframe.columns:
        return 0
    normalized = dataframe[column_name].astype(str).str.strip().str.lower()
    return int(normalized.eq(expected_value.strip().lower()).sum())


def first_non_empty(*values: object) -> str:
    for value in values:
        text = str(value).strip()
        if text and text.lower() != "nan":
            return text
    return ""


def safe_int(value: object) -> int:
    text = str(value).strip().replace(",", "")
    if not text or text == "#REF!":
        return 0
    try:
        return int(float(text))
    except Exception:
        return 0


def pad_summary_rows(rows: list[list[str]]) -> list[list[str]]:
    width = max((len(row) for row in rows), default=0)
    return [row + [""] * (width - len(row)) for row in rows]


def find_first_row(rows: list[list[str]], label: str) -> int | None:
    for index, row in enumerate(rows):
        if any(str(cell).strip() == label for cell in row):
            return index
    return None


def parse_summary_sheet(rows: list[list[str]]) -> dict[str, object]:
    padded = pad_summary_rows(rows)
    if not padded:
        return {
            "updated_date": "",
            "updated_time": "",
            "sample_progress": pd.DataFrame(columns=["Metric", "Value"]),
            "overall_progress": pd.DataFrame(columns=["Tool", "Count"]),
            "owner_progress": pd.DataFrame(columns=["Name", "Date", "Assigned", "Approved", "Rejected", "Remaining"]),
            "qa_progress": pd.DataFrame(columns=["Tool Name", "Approved", "Rejected", "Pending", "Remaining"]),
            "qa_by": pd.DataFrame(columns=["QA By", "Assigned", "Checked", "Approved", "Rejected", "Pending", "Remaining"]),
            "enumerator_performance": pd.DataFrame(columns=["Surveyor_Name", "Region", "Province", "Recived", "QA'd", "Approved", "Rejected", "Pending", "Overall Score"]),
        }

    updated_date = padded[4][11] if len(padded) > 4 and len(padded[4]) > 11 else ""
    updated_time = padded[7][11] if len(padded) > 7 and len(padded[7]) > 11 else ""

    sample_progress_df = pd.DataFrame(
        [
            {"Metric": "TLS Sample Target", "Value": safe_int(padded[2][2] if len(padded) > 2 and len(padded[2]) > 2 else 0)},
            {"Metric": "ECE Sample Target", "Value": safe_int(padded[3][2] if len(padded) > 3 and len(padded[3]) > 2 else 0)},
            {"Metric": "Completed TLS", "Value": safe_int(padded[3][6] if len(padded) > 3 and len(padded[3]) > 6 else 0)},
            {"Metric": "Completed ECE Parent", "Value": safe_int(padded[5][4] if len(padded) > 5 and len(padded[5]) > 4 else 0)},
            {"Metric": "Completed ECE", "Value": safe_int(padded[8][6] if len(padded) > 8 and len(padded[8]) > 6 else 0)},
        ]
    )

    overall_df = pd.DataFrame(columns=["Tool", "Count"])
    overall_row = find_first_row(padded, "Overall Progress")
    if overall_row is not None and len(padded) > overall_row + 4:
        tools_row = padded[overall_row + 2]
        counts_row = padded[overall_row + 4]
        overall_items = []
        for column_index, tool_name in enumerate(tools_row):
            tool_text = str(tool_name).strip()
            if tool_text:
                overall_items.append({"Tool": tool_text, "Count": safe_int(counts_row[column_index])})
        overall_df = pd.DataFrame(overall_items)

    owner_df = pd.DataFrame(columns=["Name", "Date", "Assigned", "Approved", "Rejected", "Remaining"])
    owner_header_row = find_first_row(padded, "Name")
    if owner_header_row is not None:
        owner_items = []
        for row in padded[owner_header_row + 1:]:
            name = str(row[0]).strip()
            if name and name not in {"QA Progress", "QA By", "Enemerator Performance"}:
                owner_items.append(
                    {
                        "Name": name,
                        "Date": row[2] if len(row) > 2 else "",
                        "Assigned": safe_int(row[3] if len(row) > 3 else 0),
                        "Approved": safe_int(row[4] if len(row) > 4 else 0),
                        "Rejected": safe_int(row[5] if len(row) > 5 else 0),
                        "Remaining": safe_int(row[6] if len(row) > 6 else 0),
                    }
                )
            if name == "QA Progress":
                break
        owner_df = pd.DataFrame(owner_items)

    qa_progress_df = pd.DataFrame(columns=["Tool Name", "Approved", "Rejected", "Pending", "Remaining"])
    qa_progress_row = find_first_row(padded, "QA Progress")
    if qa_progress_row is not None:
        qa_progress_items = []
        for row in padded[qa_progress_row + 1:]:
            tool_name = str(row[1]).strip() if len(row) > 1 else ""
            if tool_name and tool_name.lower() != "total":
                qa_progress_items.append(
                    {
                        "Tool Name": tool_name,
                        "Approved": safe_int(row[3] if len(row) > 3 else 0),
                        "Rejected": safe_int(row[4] if len(row) > 4 else 0),
                        "Pending": safe_int(row[5] if len(row) > 5 else 0),
                        "Remaining": safe_int(row[6] if len(row) > 6 else 0),
                    }
                )
            if tool_name.lower() == "total":
                break
        qa_progress_df = pd.DataFrame(qa_progress_items)

    qa_by_df = pd.DataFrame(columns=["QA By", "Assigned", "Checked", "Approved", "Rejected", "Pending", "Remaining"])
    qa_by_row = find_first_row(padded, "QA By")
    if qa_by_row is not None:
        qa_by_items = []
        for row in padded[qa_by_row + 1:]:
            name = str(row[0]).strip()
            if not name:
                continue
            if name.upper() == "TOTAL":
                break
            qa_by_items.append(
                {
                    "QA By": name,
                    "Assigned": safe_int(row[1] if len(row) > 1 else 0),
                    "Checked": safe_int(row[2] if len(row) > 2 else 0),
                    "Approved": safe_int(row[3] if len(row) > 3 else 0),
                    "Rejected": safe_int(row[4] if len(row) > 4 else 0),
                    "Pending": safe_int(row[5] if len(row) > 5 else 0),
                    "Remaining": safe_int(row[6] if len(row) > 6 else 0),
                }
            )
        qa_by_df = pd.DataFrame(qa_by_items)

    enumerator_df = pd.DataFrame(columns=["Surveyor_Name", "Region", "Province", "Recived", "QA'd", "Approved", "Rejected", "Pending", "Overall Score"])
    enumerator_row = find_first_row(padded, "Enemerator Performance")
    if enumerator_row is not None:
        enumerator_items = []
        for row in padded[enumerator_row + 1:]:
            surveyor_name = str(row[0]).strip()
            if not surveyor_name:
                continue
            if surveyor_name == "Surveyor_Name":
                continue
            if surveyor_name.lower() == "total":
                break
            enumerator_items.append(
                {
                    "Surveyor_Name": surveyor_name,
                    "Region": row[1] if len(row) > 1 else "",
                    "Province": row[2] if len(row) > 2 else "",
                    "Recived": safe_int(row[3] if len(row) > 3 else 0),
                    "QA'd": safe_int(row[4] if len(row) > 4 else 0),
                    "Approved": safe_int(row[5] if len(row) > 5 else 0),
                    "Rejected": safe_int(row[6] if len(row) > 6 else 0),
                    "Pending": safe_int(row[7] if len(row) > 7 else 0),
                    "Overall Score": row[8] if len(row) > 8 else "",
                }
            )
        enumerator_df = pd.DataFrame(enumerator_items)

    return {
        "updated_date": updated_date,
        "updated_time": updated_time,
        "sample_progress": sample_progress_df,
        "overall_progress": overall_df,
        "owner_progress": owner_df,
        "qa_progress": qa_progress_df,
        "qa_by": qa_by_df,
        "enumerator_performance": enumerator_df,
    }


def build_log_status_breakdown(qa_log: pd.DataFrame) -> pd.DataFrame:
    if qa_log.empty or "Status" not in qa_log.columns:
        return pd.DataFrame(columns=["Status", "Count"])
    status_series = qa_log["Status"].astype(str).str.strip().replace("", "Unspecified")
    counts = status_series.value_counts().reset_index()
    counts.columns = ["Status", "Count"]
    return counts


def build_tool_mix(qa_log: pd.DataFrame) -> pd.DataFrame:
    if qa_log.empty or "Tool Name" not in qa_log.columns:
        return pd.DataFrame(columns=["Tool Name", "Count"])
    counts = qa_log["Tool Name"].astype(str).str.strip()
    counts = counts[counts != ""].value_counts().reset_index()
    counts.columns = ["Tool Name", "Count"]
    return counts


def build_tool_summary(summary_data: dict[str, object], qa_log: pd.DataFrame) -> pd.DataFrame:
    overall_progress = summary_data["overall_progress"].copy()
    qa_progress = summary_data["qa_progress"].copy()
    qa_mix = build_tool_mix(qa_log).copy()

    if overall_progress.empty:
        overall_progress = pd.DataFrame(columns=["Tool", "Count"])
    if qa_progress.empty:
        qa_progress = pd.DataFrame(columns=["Tool Name", "Approved", "Rejected", "Pending", "Remaining"])
    if qa_mix.empty:
        qa_mix = pd.DataFrame(columns=["Tool Name", "Count"])

    overall_progress = overall_progress.rename(columns={"Tool": "Tool Name", "Count": "Summary Completed"})
    qa_mix = qa_mix.rename(columns={"Count": "QA Log Records"})

    tool_summary = overall_progress.merge(qa_progress, on="Tool Name", how="outer").merge(qa_mix, on="Tool Name", how="outer")
    if tool_summary.empty:
        return pd.DataFrame(columns=["Tool Name", "Summary Completed", "QA Log Records", "Approved", "Rejected", "Pending", "Remaining"])

    for column in ["Summary Completed", "QA Log Records", "Approved", "Rejected", "Pending", "Remaining"]:
        if column not in tool_summary.columns:
            tool_summary[column] = 0
        tool_summary[column] = tool_summary[column].fillna(0).astype(int)

    tool_summary["Tool Name"] = tool_summary["Tool Name"].astype(str).str.strip()
    tool_summary = tool_summary[tool_summary["Tool Name"] != ""]
    return tool_summary.sort_values(["Summary Completed", "QA Log Records"], ascending=False)


def build_progress_snapshot(summary_data: dict[str, object]) -> pd.DataFrame:
    sample_progress = summary_data["sample_progress"].copy()
    if sample_progress.empty:
        return pd.DataFrame(columns=["Stream", "Target", "Completed", "Completion %"])

    tls_target = safe_int(sample_progress.loc[sample_progress["Metric"] == "TLS Sample Target", "Value"].max())
    ece_target = safe_int(sample_progress.loc[sample_progress["Metric"] == "ECE Sample Target", "Value"].max())
    tls_completed = safe_int(sample_progress.loc[sample_progress["Metric"] == "Completed TLS", "Value"].max())
    ece_parent_completed = safe_int(sample_progress.loc[sample_progress["Metric"] == "Completed ECE Parent", "Value"].max())
    ece_completed = safe_int(sample_progress.loc[sample_progress["Metric"] == "Completed ECE", "Value"].max())

    rows = [
        {
            "Stream": "TLS",
            "Target": tls_target,
            "Completed": tls_completed,
            "Completion %": round((tls_completed / tls_target) * 100, 1) if tls_target else 0,
        },
        {
            "Stream": "ECE Parent",
            "Target": ece_target,
            "Completed": ece_parent_completed,
            "Completion %": round((ece_parent_completed / ece_target) * 100, 1) if ece_target else 0,
        },
        {
            "Stream": "ECE",
            "Target": ece_target,
            "Completed": ece_completed,
            "Completion %": round((ece_completed / ece_target) * 100, 1) if ece_target else 0,
        },
    ]
    return pd.DataFrame(rows)


def build_completion_cards(progress_snapshot: pd.DataFrame) -> pd.DataFrame:
    if progress_snapshot.empty:
        return pd.DataFrame(columns=["Label", "Percent", "Remaining", "Target", "Completed"])

    cards = progress_snapshot.copy()
    cards["Remaining"] = (cards["Target"] - cards["Completed"]).clip(lower=0)
    cards["Percent"] = cards["Completion %"].round(1)
    cards["Label"] = cards["Stream"]
    return cards[["Label", "Percent", "Remaining", "Target", "Completed"]]


def build_surveyor_table(summary_enumerator: pd.DataFrame, qa_log: pd.DataFrame) -> pd.DataFrame:
    if summary_enumerator.empty:
        return pd.DataFrame(columns=["Surveyor_Name", "Region", "Province", "Received", "QA'd", "Approved", "Rejected", "Pending"])

    surveyor_df = summary_enumerator.copy()
    surveyor_df = surveyor_df.rename(columns={"Recived": "Received"})

    qa_counts = pd.DataFrame(columns=["Surveyor_Name", "QA_Log_Records"])
    status_summary = pd.DataFrame(columns=["Surveyor_Name", "Approved_Log", "Rejected_Log", "Pending_Log"])

    if not qa_log.empty and "Surveyor_Name" in qa_log.columns:
        qa_work = qa_log.copy()
        qa_work["Surveyor_Name"] = qa_work["Surveyor_Name"].astype(str).str.strip()
        qa_counts = qa_work.groupby("Surveyor_Name").size().reset_index(name="QA_Log_Records")
        qa_work["Status"] = qa_work.get("Status", "").astype(str).str.strip().replace("", "Pending")
        status_summary = (
            qa_work.pivot_table(index="Surveyor_Name", columns="Status", values="KEY", aggfunc="count", fill_value=0)
            .reset_index()
        )
        rename_map = {
            "Approved": "Approved_Log",
            "Rejected": "Rejected_Log",
            "Pending": "Pending_Log",
            "Unspecified": "Pending_Log",
        }
        status_summary = status_summary.rename(columns=rename_map)

    merged = surveyor_df.merge(qa_counts, on="Surveyor_Name", how="left").merge(status_summary, on="Surveyor_Name", how="left")
    for column in ["QA_Log_Records", "Approved_Log", "Rejected_Log", "Pending_Log"]:
        if column not in merged.columns:
            merged[column] = 0
        merged[column] = merged[column].fillna(0).astype(int)
    return merged


def render_metric_card(title: str, value: str, subtitle: str, tone: str) -> None:
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(145deg, #ffffff 0%, #f6f8fb 100%);
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-left: 6px solid {tone};
            border-radius: 20px;
            padding: 16px 18px;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
            min-height: 156px;
            display:flex;
            flex-direction:column;
            justify-content:space-between;
        ">
            <div style="font-size: 0.82rem; letter-spacing: 0.08em; text-transform: uppercase; color: #64748b; font-weight: 700;">
                {title}
            </div>
            <div style="font-size: 2rem; font-weight: 800; color: #0f172a; margin-top: 10px;">
                {value}
            </div>
            <div style="font-size: 0.95rem; color: #475569; margin-top: 8px; line-height: 1.45;">
                {subtitle}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_completion_card(label: str, percent: float, remaining: int, target: int, completed: int, tone: str) -> None:
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(145deg, rgba(255,255,255,0.14) 0%, rgba(255,255,255,0.07) 100%);
            border: 1px solid rgba(255,255,255,0.12);
            border-top: 5px solid {tone};
            border-radius: 22px;
            padding: 16px 18px;
            min-height: 156px;
            box-shadow: 0 16px 40px rgba(0,0,0,0.18);
            display:flex;
            flex-direction:column;
            justify-content:space-between;
        ">
            <div style="font-size: 0.82rem; letter-spacing: 0.08em; text-transform: uppercase; color: #d8e3ff; font-weight: 800;">{label}</div>
            <div>
                <div style="display:flex; align-items:flex-end; gap:10px; margin-top:10px;">
                    <div style="font-size: 2.25rem; font-weight: 800; color: #ffffff; line-height:1;">{percent:.1f}%</div>
                    <div style="font-size: 0.95rem; color: #b8c7e6; margin-bottom: 4px;">completed</div>
                </div>
                <div style="margin-top: 14px; height: 10px; border-radius: 999px; background: rgba(255,255,255,0.10); overflow:hidden;">
                    <div style="width: {min(max(percent, 0), 100)}%; height: 100%; background: linear-gradient(90deg, {tone} 0%, rgba(255,255,255,0.88) 100%);"></div>
                </div>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:14px;">
                <div>
                    <div style="font-size: 0.78rem; color:#9fb0d4; text-transform:uppercase; letter-spacing:0.08em;">Completed</div>
                    <div style="font-size: 1.05rem; color:#f8fbff; font-weight:700;">{completed:,} / {target:,}</div>
                </div>
                <div>
                    <div style="font-size: 0.78rem; color:#9fb0d4; text-transform:uppercase; letter-spacing:0.08em;">Remaining</div>
                    <div style="font-size: 1.05rem; color:#f8fbff; font-weight:700;">{remaining:,}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_bar_chart(dataframe: pd.DataFrame, category: str, title: str, color: str, value_column: str = "Count") -> None:
    if dataframe.empty:
        st.info("No data is available for this view.")
        return

    chart = (
        alt.Chart(dataframe)
        .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, color=color)
        .encode(
            x=alt.X(f"{value_column}:Q", title=value_column),
            y=alt.Y(f"{category}:N", sort="-x", title=None),
            tooltip=[alt.Tooltip(f"{category}:N", title=category), alt.Tooltip(f"{value_column}:Q", title=value_column)],
        )
        .properties(height=340, title=title)
        .configure_view(strokeOpacity=0)
        .configure(background="transparent")
    )
    st.altair_chart(chart, use_container_width=True)


def render_donut_chart(dataframe: pd.DataFrame, category: str, title: str, colors: list[str]) -> None:
    if dataframe.empty:
        st.info("No data is available for this view.")
        return

    chart = (
        alt.Chart(dataframe)
        .mark_arc(innerRadius=58, outerRadius=110)
        .encode(
            theta=alt.Theta("Count:Q"),
            color=alt.Color(f"{category}:N", scale=alt.Scale(range=colors), legend=alt.Legend(title=category)),
            tooltip=[alt.Tooltip(f"{category}:N", title=category), alt.Tooltip("Count:Q", title="Count")],
        )
        .properties(height=320, title=title)
        .configure_view(strokeOpacity=0)
        .configure(background="transparent")
    )
    st.altair_chart(chart, use_container_width=True)


def render_section_header(title: str, description: str) -> None:
    st.markdown(
        f"""
        <div style="margin: 12px 0 4px 0;">
            <div style="font-size: 1.25rem; font-weight: 800; color: #f8fbff;">{title}</div>
            <div style="font-size: 0.96rem; color: #c1d0ec; margin-top: 4px; line-height: 1.65;">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


tls_data, ece_data, summary_rows, qa_log_data, correction_log_data, rejection_log_data, red_flag_log_data, callback_log_data = load_dashboard_data()
summary_data = parse_summary_sheet(summary_rows)
qa_status_breakdown = build_log_status_breakdown(qa_log_data)
qa_tool_mix = build_tool_mix(qa_log_data)
surveyor_command_table = build_surveyor_table(summary_data["enumerator_performance"], qa_log_data)
tool_summary = build_tool_summary(summary_data, qa_log_data)
progress_snapshot = build_progress_snapshot(summary_data)
completion_cards = build_completion_cards(progress_snapshot)

if tls_data.empty and ece_data.empty and not summary_rows and qa_log_data.empty:
    st.warning("The dashboard could not load data from the configured worksheets.")
    st.stop()

all_regions = sorted(
    {
        value
        for frame in [tls_data, ece_data]
        if "Region" in frame.columns
        for value in frame["Region"].astype(str).str.strip().tolist()
        if value
    }
)
all_provinces = sorted(
    {
        value
        for frame in [tls_data, ece_data]
        if "Province" in frame.columns
        for value in frame["Province"].astype(str).str.strip().tolist()
        if value
    }
)
all_districts = sorted(
    {
        value
        for frame in [tls_data, ece_data]
        if "District" in frame.columns
        for value in frame["District"].astype(str).str.strip().tolist()
        if value
    }
)

st.markdown(
    "",
    unsafe_allow_html=True,
)

apply_liquid_glass_theme(
    "Field Monitoring Dashboard",
    "Monitor progress, QA activity, surveyors, and tools in one place.",
    accent="#8b5cf6",
    compact_hero=True,
)

st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)

hero_left, hero_right = st.columns(2, gap="large")

with hero_left:
    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="glass-panel" style="padding: 1.45rem 1.5rem;">
            <div style="font-size: 1.05rem; color: #dce7ff; line-height: 1.75;">
                A compact operational view of progress, QA flow, surveyor performance, and tool status.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with hero_right:
    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
    card_columns = st.columns(3, gap="small")
    card_colors = ["#3b82f6", "#22c55e", "#f59e0b"]
    for index, card in enumerate(completion_cards.itertuples(index=False)):
        with card_columns[index]:
            render_completion_card(card.Label, card.Percent, int(card.Remaining), int(card.Target), int(card.Completed), card_colors[index % len(card_colors)])

filter_panel, _ = st.columns([1, 1], gap="large")
with filter_panel:
    st.markdown("### Filters")
    filter_cols = st.columns(3, gap="small")
    with filter_cols[0]:
        selected_regions = st.multiselect("Region", all_regions, placeholder="All regions")
    with filter_cols[1]:
        selected_provinces = st.multiselect("Province", all_provinces, placeholder="All provinces")
    with filter_cols[2]:
        selected_districts = st.multiselect("District", all_districts, placeholder="All districts")

filtered_tls = apply_filters(tls_data, selected_regions, selected_provinces, selected_districts)
filtered_ece = apply_filters(ece_data, selected_regions, selected_provinces, selected_districts)

total_tls = len(filtered_tls)
total_ece = len(filtered_ece)
combined_total = total_tls + total_ece
qa_log_total = len(qa_log_data)
rejection_total = len(rejection_log_data)
correction_total = len(correction_log_data)
red_flag_total = len(red_flag_log_data)
callback_total = len(callback_log_data)
unique_provinces = len(
    {
        *filtered_tls.get("Province", pd.Series(dtype=str)).astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist(),
        *filtered_ece.get("Province", pd.Series(dtype=str)).astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist(),
    }
)
unique_districts = len(
    {
        *filtered_tls.get("District", pd.Series(dtype=str)).astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist(),
        *filtered_ece.get("District", pd.Series(dtype=str)).astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist(),
    }
)

metric_cols = st.columns(4, gap="large")
with metric_cols[0]:
    render_metric_card("Sample Universe", f"{combined_total:,}", "Combined operational sample volume across TLS and ECE.", "#2563eb")
with metric_cols[1]:
    render_metric_card("QA Log Records", f"{qa_log_total:,}", f"{count_matching(qa_log_data, 'Status', 'Approved')} approved records captured so far.", "#16a34a")
with metric_cols[2]:
    render_metric_card("Operational Risk Flags", f"{red_flag_total + rejection_total + callback_total:,}", f"Red flags: {red_flag_total}, rejections: {rejection_total}, callbacks: {callback_total}.", "#f97316")
with metric_cols[3]:
    render_metric_card("Summary Update", f"{summary_data['updated_date'] or 'N/A'}", f"Last QA log time: {summary_data['updated_time'] or 'N/A'}", "#7c3aed")

overview_tab, command_tab, summary_tab, tls_tab, ece_tab = st.tabs(["Overview", "Command Center", "Summary", "TLS Sample", "ECE Sample"])

with overview_tab:
    render_section_header("Executive Overview", "A consolidated decision layer combining sample coverage, Summary progress, and operational QA signals.")

    summary_top_left, summary_top_right = st.columns(2, gap="large")
    with summary_top_left:
        sample_progress = summary_data["sample_progress"]
        render_bar_chart(sample_progress, "Metric", "Sample Progress Snapshot", "#1d4ed8", value_column="Value")
    with summary_top_right:
        if not qa_status_breakdown.empty:
            render_donut_chart(qa_status_breakdown, "Status", "QA Log Status Mix", ["#22c55e", "#ef4444", "#f59e0b", "#64748b", "#2563eb"])
        else:
            st.info("No QA status data is available yet.")

    geography_left, geography_right = st.columns(2, gap="large")
    with geography_left:
        combined_by_province = (
            pd.concat(
                [
                    filtered_tls.assign(Sample_Type="TLS")[["Province", "Sample_Type"]],
                    filtered_ece.assign(Sample_Type="ECE")[["Province", "Sample_Type"]],
                ],
                ignore_index=True,
            )
            if "Province" in filtered_tls.columns and "Province" in filtered_ece.columns
            else pd.DataFrame(columns=["Province", "Sample_Type"])
        )
        if not combined_by_province.empty:
            province_counts = combined_by_province.groupby("Province").size().reset_index(name="Count").sort_values("Count", ascending=False).head(12)
        else:
            province_counts = pd.DataFrame(columns=["Province", "Count"])
        render_bar_chart(province_counts, "Province", "Top Provinces by Combined Sample Volume", "#2563eb")

    with geography_right:
        sample_mix = pd.DataFrame(
            {
                "Sample Type": ["TLS", "ECE"],
                "Count": [total_tls, total_ece],
            }
        )
        render_donut_chart(sample_mix, "Sample Type", "TLS vs ECE Distribution", ["#16a34a", "#f97316"])

    operational_left, operational_right = st.columns(2, gap="large")
    with operational_left:
        district_counts = pd.concat(
            [
                filtered_tls.get("District", pd.Series(dtype=str)),
                filtered_ece.get("District", pd.Series(dtype=str)),
            ],
            ignore_index=True,
        )
        district_counts = district_counts.astype(str).str.strip()
        district_counts = district_counts[district_counts != ""].value_counts().head(12).reset_index()
        district_counts.columns = ["District", "Count"]
        render_bar_chart(district_counts, "District", "Top Districts by Combined Sample Volume", "#0f766e")

    with operational_right:
        climate_counts = pd.concat(
            [
                filtered_tls.get("Climate", pd.Series(dtype=str)),
                filtered_ece.get("Climate", pd.Series(dtype=str)),
            ],
            ignore_index=True,
        )
        climate_counts = climate_counts.astype(str).str.strip()
        climate_counts = climate_counts[climate_counts != ""].value_counts().reset_index()
        climate_counts.columns = ["Climate", "Count"]
        render_donut_chart(climate_counts, "Climate", "Climate Distribution", ["#1d4ed8", "#22c55e", "#f59e0b", "#ef4444"])

    insights_left, insights_right = st.columns(2, gap="large")
    with insights_left:
        qa_progress = summary_data["qa_progress"]
        if not qa_progress.empty:
            qa_melt = qa_progress.melt(
                id_vars=["Tool Name"],
                value_vars=["Approved", "Rejected", "Pending", "Remaining"],
                var_name="Status",
                value_name="Count",
            )
            chart = (
                alt.Chart(qa_melt)
                .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
                .encode(
                    x=alt.X("Tool Name:N", title=None),
                    y=alt.Y("Count:Q", title="Count"),
                    color=alt.Color("Status:N", scale=alt.Scale(range=["#22c55e", "#ef4444", "#f59e0b", "#64748b"])),
                    tooltip=["Tool Name:N", "Status:N", "Count:Q"],
                )
                .properties(height=340, title="QA Status by Tool")
                .configure_view(strokeOpacity=0)
                .configure(background="transparent")
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No QA progress data is available in Summary.")
    with insights_right:
        st.markdown("### Live Risk Monitor")
        risk_cards = [
            ("Corrections", correction_total, "#2563eb"),
            ("Rejections", rejection_total, "#ef4444"),
            ("Red Flags", red_flag_total, "#f97316"),
            ("Call Backs", callback_total, "#7c3aed"),
        ]
        for label, value, color in risk_cards:
            st.markdown(
                f"""
                <div style="
                    background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
                    border: 1px solid rgba(15,23,42,0.08);
                    border-left: 5px solid {color};
                    border-radius: 16px;
                    padding: 14px 16px;
                    margin-bottom: 12px;
                ">
                    <div style="font-size: 0.82rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700;">{label}</div>
                    <div style="font-size: 1.7rem; font-weight: 800; color: #0f172a; margin-top: 6px;">{value:,}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

with command_tab:
    render_section_header("Command Center", "High-priority field and QA monitoring signals across Summary and operational log sheets.")

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
    command_metrics = st.columns(5, gap="large")
    tls_target = safe_int(summary_data["sample_progress"].loc[summary_data["sample_progress"]["Metric"] == "TLS Sample Target", "Value"].max()) if not summary_data["sample_progress"].empty else 0
    ece_target = safe_int(summary_data["sample_progress"].loc[summary_data["sample_progress"]["Metric"] == "ECE Sample Target", "Value"].max()) if not summary_data["sample_progress"].empty else 0
    completed_total = int(summary_data["overall_progress"]["Count"].sum()) if not summary_data["overall_progress"].empty else 0
    with command_metrics[0]:
        render_metric_card("TLS Target", f"{tls_target:,}", "Target sample size for TLS from Summary.", "#2563eb")
    with command_metrics[1]:
        render_metric_card("ECE Target", f"{ece_target:,}", "Target sample size for ECE from Summary.", "#16a34a")
    with command_metrics[2]:
        render_metric_card("Completed Units", f"{completed_total:,}", "Combined completion count visible in Summary.", "#f97316")
    with command_metrics[3]:
        render_metric_card("Covered Provinces", f"{unique_provinces:,}", "Distinct provinces across the filtered TLS and ECE sample universe.", "#0f766e")
    with command_metrics[4]:
        render_metric_card("Active Surveyors", f"{len(surveyor_command_table):,}", "Surveyors tracked in the Summary performance roster.", "#7c3aed")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    command_left, command_right = st.columns(2, gap="large")
    with command_left:
        if not surveyor_command_table.empty:
            top_surveyors = surveyor_command_table.sort_values(["Received", "Approved_Log", "QA_Log_Records"], ascending=False).head(15)
            chart = (
                alt.Chart(top_surveyors)
                .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, color="#1d4ed8")
                .encode(
                    x=alt.X("Received:Q", title="Received"),
                    y=alt.Y("Surveyor_Name:N", sort="-x", title=None),
                    tooltip=["Surveyor_Name:N", "Region:N", "Province:N", "Received:Q", "Approved_Log:Q", "Rejected_Log:Q", "Pending_Log:Q"],
                )
                .properties(height=360, title="Top Surveyors by Received Volume")
                .configure_view(strokeOpacity=0)
                .configure(background="transparent")
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No surveyor command data is available.")
    with command_right:
        if not qa_tool_mix.empty:
            render_donut_chart(qa_tool_mix, "Tool Name", "QA Log Tool Mix", ["#2563eb", "#22c55e", "#f97316", "#7c3aed", "#0f766e"])
        else:
            st.info("No QA tool mix is available yet.")

        if not summary_data["overall_progress"].empty:
            st.markdown("### Completion Signals")
            st.dataframe(summary_data["overall_progress"], use_container_width=True, hide_index=True)

with summary_tab:
    render_section_header("Summary Command Center", "A full operational view of QA progress, assignment status, timestamps, and surveyor-level performance from the Summary sheet.")

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
    summary_metrics = st.columns(4, gap="large")
    owner_progress = summary_data["owner_progress"]
    qa_by_data = summary_data["qa_by"]
    enumerator_data = summary_data["enumerator_performance"]
    overall_progress = summary_data["overall_progress"]

    assigned_total = int(qa_by_data["Assigned"].sum()) if not qa_by_data.empty else 0
    checked_total = int(qa_by_data["Checked"].sum()) if not qa_by_data.empty else 0
    approved_total = int(qa_by_data["Approved"].sum()) if not qa_by_data.empty else 0
    rejected_total = int(qa_by_data["Rejected"].sum()) if not qa_by_data.empty else 0

    with summary_metrics[0]:
        render_metric_card("Overall Tool Progress", f"{int(overall_progress['Count'].sum()) if not overall_progress.empty else 0:,}", "Total completed units captured in Summary tool progress.", "#2563eb")
    with summary_metrics[1]:
        render_metric_card("Assigned vs Checked", f"{assigned_total:,} / {checked_total:,}", "QA assignment load compared with checked volume.", "#16a34a")
    with summary_metrics[2]:
        render_metric_card("Approved vs Rejected", f"{approved_total:,} / {rejected_total:,}", "Current approval and rejection outcomes from Summary.", "#f97316")
    with summary_metrics[3]:
        render_metric_card("Surveyor Footprint", f"{len(enumerator_data):,}", "Surveyors listed in Enumerator Performance.", "#7c3aed")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    summary_layout_left, summary_layout_right = st.columns(2, gap="large")
    with summary_layout_left:
        if not qa_by_data.empty:
            qa_by_melt = qa_by_data.melt(
                id_vars=["QA By"],
                value_vars=["Assigned", "Checked", "Approved", "Rejected", "Pending", "Remaining"],
                var_name="Status",
                value_name="Count",
            )
            qa_team_chart = (
                alt.Chart(qa_by_melt)
                .mark_bar()
                .encode(
                    x=alt.X("Count:Q", title="Count"),
                    y=alt.Y("QA By:N", sort="-x", title=None),
                    color=alt.Color("Status:N", scale=alt.Scale(range=["#2563eb", "#0f766e", "#22c55e", "#ef4444", "#f59e0b", "#64748b"])),
                    tooltip=["QA By:N", "Status:N", "Count:Q"],
                )
                .properties(height=360, title="QA Team Workload and Outcomes")
                .configure_view(strokeOpacity=0)
                .configure(background="transparent")
            )
            st.altair_chart(qa_team_chart, use_container_width=True)
        else:
            st.info("No QA-by-person data is available in Summary.")

    with summary_layout_right:
        if not owner_progress.empty:
            st.markdown("### Current Summary Snapshot")
            st.dataframe(owner_progress, use_container_width=True, hide_index=True)
        else:
            st.info("No owner progress snapshot is available in Summary.")

        st.markdown("### Last Update")
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(145deg, #f8fafc 0%, #eef2ff 100%);
                border: 1px solid rgba(37, 99, 235, 0.12);
                border-radius: 18px;
                padding: 18px 20px;
                margin-top: 8px;
            ">
                <div style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; font-weight: 700;">Summary Timestamp</div>
                <div style="font-size: 1.45rem; font-weight: 800; color: #0f172a; margin-top: 8px;">{summary_data['updated_date'] or 'N/A'}</div>
                <div style="font-size: 1.05rem; color: #334155; margin-top: 4px;">{summary_data['updated_time'] or 'N/A'} Afghanistan Time</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    progress_left, progress_right = st.columns(2, gap="large")
    with progress_left:
        if not progress_snapshot.empty:
            progress_chart = (
                alt.Chart(progress_snapshot)
                .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, color="#2563eb")
                .encode(
                    x=alt.X("Completed:Q", title="Completed"),
                    y=alt.Y("Stream:N", title=None, sort="-x"),
                    tooltip=["Stream:N", "Target:Q", "Completed:Q", alt.Tooltip("Completion %:Q", title="Completion %")],
                )
                .properties(height=300, title="Progress by Stream")
                .configure_view(strokeOpacity=0)
                .configure(background="transparent")
            )
            st.altair_chart(progress_chart, use_container_width=True)
        else:
            st.info("No progress snapshot is available.")
    with progress_right:
        if not progress_snapshot.empty:
            completion_chart = (
                alt.Chart(progress_snapshot)
                .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, color="#22c55e")
                .encode(
                    x=alt.X("Completion %:Q", title="Completion %"),
                    y=alt.Y("Stream:N", title=None, sort="-x"),
                    tooltip=["Stream:N", "Target:Q", "Completed:Q", alt.Tooltip("Completion %:Q", title="Completion %")],
                )
                .properties(height=300, title="Completion Rate")
                .configure_view(strokeOpacity=0)
                .configure(background="transparent")
            )
            st.altair_chart(completion_chart, use_container_width=True)
        else:
            st.info("No completion-rate data is available.")

    enumerator_left, enumerator_right = st.columns(2, gap="large")
    with enumerator_left:
        if not enumerator_data.empty:
            province_summary = top_counts(enumerator_data, "Province", 12)
            render_bar_chart(province_summary, "Province", "Surveyor Distribution by Province", "#0f766e")
        else:
            st.info("No enumerator performance data is available in Summary.")

    with enumerator_right:
        if not enumerator_data.empty:
            region_summary = top_counts(enumerator_data, "Region", 12)
            render_donut_chart(region_summary, "Region", "Surveyor Distribution by Region", ["#2563eb", "#22c55e", "#f97316", "#7c3aed", "#0f766e", "#ef4444"])
        else:
            st.info("No enumerator performance data is available in Summary.")

    detail_left, detail_right = st.columns(2, gap="large")
    with detail_left:
        if not summary_data["sample_progress"].empty:
            render_bar_chart(summary_data["sample_progress"], "Metric", "Summary Sample and Completion Status", "#2563eb", value_column="Value")
    with detail_right:
        if not qa_log_data.empty:
            recent_columns = [column for column in ["Tool Name", "Province", "District", "Surveyor_Name", "Survey_Date", "Status"] if column in qa_log_data.columns]
            st.markdown("### Latest QA Log Entries")
            st.dataframe(qa_log_data[recent_columns].tail(10), use_container_width=True, hide_index=True)
        else:
            st.info("No QA log records are available yet.")

    if not enumerator_data.empty:
        st.markdown("### Surveyor and Enumerator Performance")
        st.dataframe(surveyor_command_table, use_container_width=True, hide_index=True)

    qa_by_table = summary_data["qa_by"]
    qa_by_left, qa_by_right = st.columns(2, gap="large")
    with qa_by_left:
        if not qa_by_table.empty:
            qa_by_chart_source = qa_by_table.melt(
                id_vars=["QA By"],
                value_vars=["Assigned", "Checked", "Approved", "Rejected", "Pending", "Remaining"],
                var_name="Metric",
                value_name="Count",
            )
            qa_by_chart = (
                alt.Chart(qa_by_chart_source)
                .mark_bar()
                .encode(
                    x=alt.X("QA By:N", title=None),
                    y=alt.Y("Count:Q", title="Count"),
                    color=alt.Color("Metric:N", scale=alt.Scale(range=["#2563eb", "#0f766e", "#22c55e", "#ef4444", "#f59e0b", "#64748b"])),
                    tooltip=["QA By:N", "Metric:N", "Count:Q"],
                )
                .properties(height=360, title="QA By Performance Matrix")
                .configure_view(strokeOpacity=0)
                .configure(background="transparent")
            )
            st.altair_chart(qa_by_chart, use_container_width=True)
        else:
            st.info("No QA By data is available.")
    with qa_by_right:
        st.markdown("### QA By Detail Table")
        if not qa_by_table.empty:
            st.dataframe(qa_by_table, use_container_width=True, hide_index=True)
        else:
            st.info("No QA By detail table is available.")

    tools_left, tools_right = st.columns(2, gap="large")
    with tools_left:
        if not tool_summary.empty:
            tool_chart_source = tool_summary.melt(
                id_vars=["Tool Name"],
                value_vars=["Summary Completed", "QA Log Records", "Approved", "Rejected", "Pending", "Remaining"],
                var_name="Metric",
                value_name="Count",
            )
            tool_chart = (
                alt.Chart(tool_chart_source)
                .mark_bar()
                .encode(
                    x=alt.X("Tool Name:N", title=None),
                    y=alt.Y("Count:Q", title="Count"),
                    color=alt.Color("Metric:N", scale=alt.Scale(range=["#2563eb", "#0f766e", "#22c55e", "#ef4444", "#f59e0b", "#64748b"])),
                    tooltip=["Tool Name:N", "Metric:N", "Count:Q"],
                )
                .properties(height=360, title="Tool-Level Operational Overview")
                .configure_view(strokeOpacity=0)
                .configure(background="transparent")
            )
            st.altair_chart(tool_chart, use_container_width=True)
        else:
            st.info("No tool-level summary is available.")
    with tools_right:
        st.markdown("### Tool Summary Table")
        if not tool_summary.empty:
            st.dataframe(tool_summary, use_container_width=True, hide_index=True)
        else:
            st.info("No tool summary table is available.")

    surveyor_left, surveyor_right = st.columns(2, gap="large")
    with surveyor_left:
        if not surveyor_command_table.empty:
            surveyor_chart_source = surveyor_command_table.melt(
                id_vars=["Surveyor_Name"],
                value_vars=["Received", "QA'd", "Approved", "Rejected", "Pending", "QA_Log_Records"],
                var_name="Metric",
                value_name="Count",
            )
            surveyor_chart = (
                alt.Chart(surveyor_chart_source.head(300))
                .mark_bar()
                .encode(
                    x=alt.X("Count:Q", title="Count"),
                    y=alt.Y("Surveyor_Name:N", sort="-x", title=None),
                    color=alt.Color("Metric:N", scale=alt.Scale(range=["#2563eb", "#0f766e", "#22c55e", "#ef4444", "#f59e0b", "#7c3aed"])),
                    tooltip=["Surveyor_Name:N", "Metric:N", "Count:Q"],
                )
                .properties(height=520, title="Surveyor Performance and QA Activity")
                .configure_view(strokeOpacity=0)
                .configure(background="transparent")
            )
            st.altair_chart(surveyor_chart, use_container_width=True)
        else:
            st.info("No surveyor performance data is available.")
    with surveyor_right:
        st.markdown("### Full Surveyor Table")
        if not surveyor_command_table.empty:
            st.dataframe(surveyor_command_table, use_container_width=True, hide_index=True)
        else:
            st.info("No surveyor table is available.")

with tls_tab:
    render_section_header("TLS Sample Intelligence", "Structural and operational patterns across the TLS sample worksheet.")

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
    tls_metrics = st.columns(4, gap="large")
    with tls_metrics[0]:
        render_metric_card("TLS Records", f"{len(filtered_tls):,}", "Filtered row count from the TLS sample.", "#16a34a")
    with tls_metrics[1]:
        render_metric_card("Unique Schools", f"{count_unique(filtered_tls, 'PS_Code'):,}", "Distinct schools represented by PS_Code.", "#2563eb")
    with tls_metrics[2]:
        render_metric_card("Unique Classes", f"{count_unique(filtered_tls, 'Class_Code'):,}", "Distinct classroom codes in the current filter.", "#f59e0b")
    with tls_metrics[3]:
        render_metric_card("Active SMS", f"{count_matching(filtered_tls, 'Active_SMS', 'Yes'):,}", "Rows flagged with SMS participation across the filter scope.", "#7c3aed")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    tls_left, tls_right = st.columns(2, gap="large")
    with tls_left:
        render_bar_chart(top_counts(filtered_tls, "TLS_Type", 8), "TLS_Type", "TLS Type Breakdown", "#16a34a")
    with tls_right:
        render_donut_chart(top_counts(filtered_tls, "TLS_Gender", 8), "TLS_Gender", "Gender Split", ["#2563eb", "#ec4899", "#14b8a6"])

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    tls_bottom_left, tls_bottom_right = st.columns(2, gap="large")
    with tls_bottom_left:
        render_bar_chart(top_counts(filtered_tls, "Class_Shift", 8), "Class_Shift", "Class Shift Profile", "#f59e0b")
    with tls_bottom_right:
        render_bar_chart(top_counts(filtered_tls, "Instruction_Language", 8), "Instruction_Language", "Instruction Language Distribution", "#7c3aed")

with ece_tab:
    render_section_header("ECE Sample Intelligence", "Coverage and data quality signals across the ECE sample worksheet.")

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
    ece_metrics = st.columns(4, gap="large")
    with ece_metrics[0]:
        render_metric_card("ECE Records", f"{len(filtered_ece):,}", "Filtered row count from the ECE sample.", "#f97316")
    with ece_metrics[1]:
        render_metric_card("Unique ECE IDs", f"{count_unique(filtered_ece, 'sample_ECE_ID'):,}", "Distinct sample ECE identifiers.", "#2563eb")
    with ece_metrics[2]:
        render_metric_card("Named PB Sites", f"{count_unique(filtered_ece, 'PB_Name'):,}", "Distinct PB names available in the filtered view.", "#16a34a")
    with ece_metrics[3]:
        missing_pb = 0
        if "PB_Name" in filtered_ece.columns:
            missing_pb = int(filtered_ece["PB_Name"].astype(str).str.strip().eq("").sum())
        render_metric_card("Missing PB Name", f"{missing_pb:,}", "Rows where the PB name is not available.", "#ef4444")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    ece_left, ece_right = st.columns(2, gap="large")
    with ece_left:
        render_bar_chart(top_counts(filtered_ece, "Province", 12), "Province", "ECE Sample by Province", "#f97316")
    with ece_right:
        render_bar_chart(top_counts(filtered_ece, "District", 12), "District", "ECE Sample by District", "#0f766e")

    if "PB_Name" in filtered_ece.columns:
        st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
        st.markdown("### PB Name Coverage")
        pb_status = pd.DataFrame(
            {
                "Status": ["Available", "Missing"],
                "Count": [
                    int(filtered_ece["PB_Name"].astype(str).str.strip().ne("").sum()),
                    int(filtered_ece["PB_Name"].astype(str).str.strip().eq("").sum()),
                ],
            }
        )
        render_donut_chart(pb_status, "Status", "PB Name Availability", ["#22c55e", "#ef4444"])
