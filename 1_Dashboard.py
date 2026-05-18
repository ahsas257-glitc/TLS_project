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
DEFAULT_TLS_COLLECTION_TARGET = 400
DEFAULT_ECE_COLLECTION_TARGET = 162


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


def normalize_filter_text(value: object) -> str:
    return " ".join(str(value).strip().lower().split())


def normalized_filter_values(values: list[str]) -> set[str]:
    return {normalize_filter_text(value) for value in values if normalize_filter_text(value)}


def apply_text_filter(dataframe: pd.DataFrame, column_name: str, selected_values: list[str]) -> pd.DataFrame:
    if dataframe.empty or column_name not in dataframe.columns or not selected_values:
        return dataframe
    wanted = normalized_filter_values(selected_values)
    if not wanted:
        return dataframe
    normalized = dataframe[column_name].fillna("").astype(str).map(normalize_filter_text)
    return dataframe[normalized.isin(wanted)]


def apply_filters(dataframe: pd.DataFrame, regions: list[str], provinces: list[str], districts: list[str]) -> pd.DataFrame:
    filtered = dataframe.copy()
    filtered = apply_text_filter(filtered, "Region", regions)
    filtered = apply_text_filter(filtered, "Province", provinces)
    filtered = apply_text_filter(filtered, "District", districts)
    return filtered


def unique_filter_values(frames: list[pd.DataFrame], column_name: str) -> list[str]:
    values: set[str] = set()
    for frame in frames:
        if column_name not in frame.columns:
            continue
        for value in frame[column_name].fillna("").astype(str).str.strip().tolist():
            if value:
                values.add(value)
    return sorted(values, key=lambda item: item.lower())


def apply_log_filters(dataframe: pd.DataFrame, provinces: list[str], districts: list[str]) -> pd.DataFrame:
    filtered = dataframe.copy()
    filtered = apply_text_filter(filtered, "Province", provinces)
    filtered = apply_text_filter(filtered, "District", districts)
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


def first_existing_column(dataframe: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized_lookup = {str(column).strip().lower(): column for column in dataframe.columns}
    for candidate in candidates:
        column = normalized_lookup.get(candidate.strip().lower())
        if column is not None:
            return column
    return None


def clean_series(dataframe: pd.DataFrame, column_name: str | None) -> pd.Series:
    if not column_name or column_name not in dataframe.columns:
        return pd.Series(dtype=str)
    return dataframe[column_name].fillna("").astype(str).str.strip()


def non_empty_count(dataframe: pd.DataFrame, column_name: str | None) -> int:
    series = clean_series(dataframe, column_name)
    if series.empty:
        return 0
    return int(series.ne("").sum())


def count_positive(dataframe: pd.DataFrame, column_name: str | None) -> int:
    if not column_name or column_name not in dataframe.columns:
        return 0
    numeric = pd.to_numeric(dataframe[column_name].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
    return int((numeric > 0).sum())


def normalize_status(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return "Pending"
    lowered = text.lower()
    if "approve" in lowered:
        return "Approved"
    if "reject" in lowered:
        return "Rejected"
    if "pending" in lowered:
        return "Pending"
    if "call" in lowered:
        return "Call Back"
    return text.title()


def status_mask(dataframe: pd.DataFrame, expected_status: str) -> pd.Series:
    if dataframe.empty:
        return pd.Series(dtype=bool, index=dataframe.index)
    if "Status" not in dataframe.columns:
        return pd.Series(False, index=dataframe.index)
    return dataframe["Status"].apply(normalize_status).eq(expected_status)


def exclude_status(dataframe: pd.DataFrame, status: str) -> pd.DataFrame:
    if dataframe.empty or "Status" not in dataframe.columns:
        return dataframe.copy()
    return dataframe[~status_mask(dataframe, status)].copy()


def only_status(dataframe: pd.DataFrame, status: str) -> pd.DataFrame:
    if dataframe.empty or "Status" not in dataframe.columns:
        return dataframe.iloc[0:0].copy()
    return dataframe[status_mask(dataframe, status)].copy()


def build_status_counts(dataframe: pd.DataFrame, status_column: str = "Status") -> pd.DataFrame:
    if dataframe.empty or status_column not in dataframe.columns:
        return pd.DataFrame(columns=["Status", "Count"])
    statuses = dataframe[status_column].apply(normalize_status)
    counts = statuses.value_counts().reset_index()
    counts.columns = ["Status", "Count"]
    return counts


def filter_qa_by_tools(qa_log: pd.DataFrame, tool_names: list[str]) -> pd.DataFrame:
    if qa_log.empty or "Tool Name" not in qa_log.columns:
        return qa_log.iloc[0:0].copy()
    wanted = {tool_name.strip().lower() for tool_name in tool_names}
    return qa_log[qa_log["Tool Name"].astype(str).str.strip().str.lower().isin(wanted)].copy()


def build_sample_health(sample_df: pd.DataFrame, qa_log: pd.DataFrame, stream: str, tool_names: list[str]) -> dict[str, object]:
    id_candidates = {
        "TLS": ["TPM_TLS_ID", "TPM ID", "TPM-ID", "TPM_ID", "Class_Code", "TLS_SN"],
        "ECE": ["TPM_ECE_ID", "TPM ID", "TPM-ID", "TPM_ID", "sample_ECE_ID"],
    }
    sample_id_column = first_existing_column(sample_df, id_candidates.get(stream, []))
    qa_id_column = first_existing_column(qa_log, ["TPM-ID (ECE, TLS)", "TPM_ID", "TPM-ID", "TPM TLS ID", "TPM ECE ID"])
    total_data_column = first_existing_column(sample_df, ["Total Data", "Total_Data", "TotalData"])
    tool_column = first_existing_column(sample_df, tool_names + [tool.replace(" ", "_") for tool in tool_names])

    qa_subset = filter_qa_by_tools(qa_log, tool_names)
    sample_ids = clean_series(sample_df, sample_id_column)
    qa_ids = clean_series(qa_subset, qa_id_column)
    qa_id_set = {value for value in qa_ids.tolist() if value}
    matched_mask = sample_ids.isin(qa_id_set) if not sample_ids.empty else pd.Series(False, index=sample_df.index)
    if qa_id_column and not sample_ids.empty and qa_id_column in qa_subset.columns:
        filtered_qa_subset = qa_subset[qa_subset[qa_id_column].astype(str).str.strip().isin({value for value in sample_ids.tolist() if value})].copy()
    else:
        filtered_qa_subset = qa_subset.iloc[0:0].copy()
    duplicate_ids = int(sample_ids[sample_ids != ""].duplicated().sum()) if not sample_ids.empty else 0
    missing_sample_ids = int(sample_ids.eq("").sum()) if not sample_ids.empty else len(sample_df)

    status_counts = build_status_counts(filtered_qa_subset)
    all_status_counts = build_status_counts(qa_subset)
    status_lookup = dict(zip(status_counts.get("Status", []), status_counts.get("Count", [])))

    critical_columns = [
        first_existing_column(sample_df, ["Region"]),
        first_existing_column(sample_df, ["Province"]),
        first_existing_column(sample_df, ["District"]),
        sample_id_column,
    ]
    critical_columns = list(dict.fromkeys(column for column in critical_columns if column))
    missing_critical = 0
    if critical_columns and not sample_df.empty:
        missing_critical = int(sample_df[critical_columns].fillna("").astype(str).apply(lambda row: any(not cell.strip() for cell in row), axis=1).sum())

    return {
        "sample_id_column": sample_id_column,
        "qa_id_column": qa_id_column,
        "tool_column": tool_column,
        "total_data_column": total_data_column,
        "qa_total_records": len(qa_subset),
        "qa_records": len(filtered_qa_subset),
        "qa_unmatched": max(len(qa_subset) - len(filtered_qa_subset), 0),
        "qa_matched": int(matched_mask.sum()) if len(matched_mask) else 0,
        "qa_coverage": round((int(matched_mask.sum()) / len(sample_df)) * 100, 1) if len(sample_df) else 0,
        "approved": int(status_lookup.get("Approved", 0)),
        "rejected": int(status_lookup.get("Rejected", 0)),
        "pending": int(status_lookup.get("Pending", 0)),
        "tool_positive": count_positive(sample_df, tool_column),
        "total_data_positive": count_positive(sample_df, total_data_column),
        "missing_critical": missing_critical,
        "missing_sample_ids": missing_sample_ids,
        "duplicate_ids": duplicate_ids,
        "status_counts": status_counts,
        "all_status_counts": all_status_counts,
        "qa_subset": filtered_qa_subset,
    }


def build_completeness_table(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    rows = []
    total = len(dataframe)
    for column in columns:
        if column not in dataframe.columns:
            continue
        complete = non_empty_count(dataframe, column)
        rows.append(
            {
                "Field": column,
                "Complete": complete,
                "Missing": max(total - complete, 0),
                "Complete %": round((complete / total) * 100, 1) if total else 0,
            }
        )
    return pd.DataFrame(rows)


def build_geo_coverage(sample_df: pd.DataFrame, qa_subset: pd.DataFrame, sample_id_column: str | None, qa_id_column: str | None) -> pd.DataFrame:
    province_column = first_existing_column(sample_df, ["Province"])
    if sample_df.empty or not province_column:
        return pd.DataFrame(columns=["Province", "Sample", "QA Matched", "Coverage %"])

    work = sample_df[[province_column]].copy()
    work["Sample ID"] = clean_series(sample_df, sample_id_column)
    qa_ids = set(clean_series(qa_subset, qa_id_column).tolist()) if qa_id_column else set()
    work["QA Matched Flag"] = work["Sample ID"].isin({value for value in qa_ids if value})
    grouped = (
        work.groupby(province_column, dropna=False)
        .agg(Sample=("Sample ID", "size"), **{"QA Matched": ("QA Matched Flag", "sum")})
        .reset_index()
        .rename(columns={province_column: "Province"})
    )
    grouped["Coverage %"] = (grouped["QA Matched"] / grouped["Sample"] * 100).round(1)
    return grouped.sort_values(["QA Matched", "Sample"], ascending=False).head(15)


def build_standard_view(dataframe: pd.DataFrame, preferred_columns: list[str], limit: int = 250) -> pd.DataFrame:
    existing = [column for column in preferred_columns if column in dataframe.columns]
    if not existing:
        existing = dataframe.columns.tolist()[:12]
    return dataframe[existing].head(limit)


def metric_value(metric_frame: pd.DataFrame, metric_name: str) -> int:
    if metric_frame.empty or "Metric" not in metric_frame.columns or "Value" not in metric_frame.columns:
        return 0
    values = metric_frame.loc[metric_frame["Metric"] == metric_name, "Value"]
    if values.empty:
        return 0
    return safe_int(values.max())


def build_sheet_reconciliation(
    summary_data: dict[str, object],
    tls_df: pd.DataFrame,
    ece_df: pd.DataFrame,
    qa_log: pd.DataFrame,
    red_flag_log: pd.DataFrame,
    callback_log: pd.DataFrame,
) -> pd.DataFrame:
    sample_progress = summary_data["sample_progress"]
    overall_progress = summary_data["overall_progress"]
    qa_progress = summary_data["qa_progress"]

    rows = [
        {
            "Source": "TLS-Sample",
            "Sheet Count": len(tls_df),
            "Summary Count": metric_value(sample_progress, "TLS Sample Target"),
            "Variance": len(tls_df) - metric_value(sample_progress, "TLS Sample Target"),
            "Signal": "TLS target vs actual rows",
        },
        {
            "Source": "ECE-Sample",
            "Sheet Count": len(ece_df),
            "Summary Count": metric_value(sample_progress, "ECE Sample Target"),
            "Variance": len(ece_df) - metric_value(sample_progress, "ECE Sample Target"),
            "Signal": "ECE target vs actual rows",
        },
    ]

    tool_aliases = {
        "Tool 2": "Tool 2 ECE",
        "Tool 3": "Tool 3 ECE Parent",
        "Tool 5": "Tool 5 TLS",
    }
    for tool_key, summary_tool in tool_aliases.items():
        sheet_count = count_matching(qa_log, "Tool Name", tool_key)
        summary_count = 0
        if not overall_progress.empty and "Tool" in overall_progress.columns:
            matches = overall_progress[overall_progress["Tool"].astype(str).str.contains(tool_key, case=False, na=False)]
            summary_count = int(matches["Count"].sum()) if not matches.empty and "Count" in matches.columns else 0
        rows.append(
            {
                "Source": f"QA_Log {tool_key}",
                "Sheet Count": sheet_count,
                "Summary Count": summary_count,
                "Variance": sheet_count - summary_count,
                "Signal": f"{summary_tool} QA log vs Summary",
            }
        )

    approved_log = count_matching(qa_log, "Status", "Approved")
    rejected_log = count_matching(qa_log, "Status", "Rejected")
    approved_summary = int(qa_progress["Approved"].sum()) if not qa_progress.empty and "Approved" in qa_progress.columns else 0
    rejected_summary = int(qa_progress["Rejected"].sum()) if not qa_progress.empty and "Rejected" in qa_progress.columns else 0
    rows.extend(
        [
            {
                "Source": "QA_Log Approved",
                "Sheet Count": approved_log,
                "Summary Count": approved_summary,
                "Variance": approved_log - approved_summary,
                "Signal": "Approved outcome consistency",
            },
            {
                "Source": "QA_Log Rejected",
                "Sheet Count": rejected_log,
                "Summary Count": rejected_summary,
                "Variance": rejected_log - rejected_summary,
                "Signal": "Rejected outcome consistency",
            },
            {
                "Source": "Red-Flag",
                "Sheet Count": len(red_flag_log),
                "Summary Count": 0,
                "Variance": len(red_flag_log),
                "Signal": "Risk records available for monitoring",
            },
            {
                "Source": "Call-Back",
                "Sheet Count": len(callback_log),
                "Summary Count": 0,
                "Variance": len(callback_log),
                "Signal": "Callback records available for monitoring",
            },
        ]
    )
    return pd.DataFrame(rows)


def build_sample_qa_match_table(tls_health: dict[str, object], ece_health: dict[str, object], tls_df: pd.DataFrame, ece_df: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "Stream": "TLS / Tool 5",
            "Sample Rows": len(tls_df),
            "QA Tool Rows": int(tls_health["qa_total_records"]),
            "Matched QA IDs": int(tls_health["qa_records"]),
            "Unmatched QA Rows": int(tls_health["qa_unmatched"]),
            "Coverage %": float(tls_health["qa_coverage"]),
        },
        {
            "Stream": "ECE / Tool 2-3",
            "Sample Rows": len(ece_df),
            "QA Tool Rows": int(ece_health["qa_total_records"]),
            "Matched QA IDs": int(ece_health["qa_records"]),
            "Unmatched QA Rows": int(ece_health["qa_unmatched"]),
            "Coverage %": float(ece_health["qa_coverage"]),
        },
    ]
    return pd.DataFrame(rows)


def build_command_completion_table(
    tls_health: dict[str, object],
    ece_health: dict[str, object],
    tls_rejected_health: dict[str, object],
    ece_rejected_health: dict[str, object],
    tls_target: int,
    ece_target: int,
) -> pd.DataFrame:
    rows = [
        {
            "Stream": "TLS / Tool 5",
            "Target": tls_target,
            "Clean Completed": int(tls_health["qa_matched"]),
            "Rejected": int(tls_rejected_health["qa_matched"]),
        },
        {
            "Stream": "ECE / Tool 2-3",
            "Target": ece_target,
            "Clean Completed": int(ece_health["qa_matched"]),
            "Rejected": int(ece_rejected_health["qa_matched"]),
        },
    ]
    table = pd.DataFrame(rows)
    table["Remaining"] = (table["Target"] - table["Clean Completed"]).clip(lower=0)
    table["Clean Completion %"] = table.apply(
        lambda row: round((row["Clean Completed"] / row["Target"]) * 100, 1) if row["Target"] else 0,
        axis=1,
    )
    return table


def build_sample_geo_matrix(tls_df: pd.DataFrame, ece_df: pd.DataFrame) -> pd.DataFrame:
    frames = []
    if not tls_df.empty and {"Province", "District"}.issubset(tls_df.columns):
        frames.append(tls_df[["Province", "District"]].assign(Stream="TLS"))
    if not ece_df.empty and {"Province", "District"}.issubset(ece_df.columns):
        frames.append(ece_df[["Province", "District"]].assign(Stream="ECE"))
    if not frames:
        return pd.DataFrame(columns=["Province", "District", "Stream", "Count"])
    combined = pd.concat(frames, ignore_index=True)
    combined["Province"] = combined["Province"].astype(str).str.strip()
    combined["District"] = combined["District"].astype(str).str.strip()
    combined = combined[(combined["Province"] != "") & (combined["District"] != "")]
    return combined.groupby(["Province", "District", "Stream"]).size().reset_index(name="Count").sort_values("Count", ascending=False).head(80)


def build_qa_audit_matrix(qa_log: pd.DataFrame) -> pd.DataFrame:
    audit_columns = ["Background Audit", "Photo Quality", "Audio Quality", "Form Accuracy", "Call_back"]
    if qa_log.empty:
        return pd.DataFrame(columns=["Audit Field", "Status", "Filled", "Total", "Filled %"])
    rows = []
    total = len(qa_log)
    status_series = qa_log["Status"].apply(normalize_status) if "Status" in qa_log.columns else pd.Series(["Pending"] * len(qa_log))
    for column in audit_columns:
        if column not in qa_log.columns:
            continue
        work = pd.DataFrame({"Status": status_series, "Filled": qa_log[column].astype(str).str.strip().ne("")})
        grouped = work.groupby("Status").agg(Filled=("Filled", "sum"), Total=("Filled", "size")).reset_index()
        for row in grouped.itertuples(index=False):
            rows.append(
                {
                    "Audit Field": column,
                    "Status": row.Status,
                    "Filled": int(row.Filled),
                    "Total": int(row.Total),
                    "Filled %": round((int(row.Filled) / int(row.Total)) * 100, 1) if int(row.Total) else 0,
                }
            )
    return pd.DataFrame(rows)


def build_qa_timeline(qa_log: pd.DataFrame) -> pd.DataFrame:
    if qa_log.empty or "QC Date" not in qa_log.columns:
        return pd.DataFrame(columns=["Date", "Tool Name", "Status", "Count"])
    work = qa_log.copy()
    work["Date"] = pd.to_datetime(work["QC Date"], errors="coerce", dayfirst=True).dt.date.astype(str)
    work["Date"] = work["Date"].replace("NaT", "")
    work = work[work["Date"] != ""]
    if work.empty:
        return pd.DataFrame(columns=["Date", "Tool Name", "Status", "Count"])
    work["Status"] = work["Status"].apply(normalize_status) if "Status" in work.columns else "Pending"
    if "Tool Name" not in work.columns:
        work["Tool Name"] = "Unknown"
    return work.groupby(["Date", "Tool Name", "Status"]).size().reset_index(name="Count")


def build_risk_register(red_flag_log: pd.DataFrame, callback_log: pd.DataFrame, qa_log: pd.DataFrame) -> pd.DataFrame:
    frames = []
    if not red_flag_log.empty:
        frames.append(red_flag_log.copy().assign(Risk_Type="Red Flag"))
    if not callback_log.empty:
        frames.append(callback_log.copy().assign(Risk_Type="Call Back"))
    if not qa_log.empty and "Call_back" in qa_log.columns:
        callback_mask = qa_log["Call_back"].astype(str).str.strip().str.lower().isin({"true", "yes", "1"})
        if callback_mask.any():
            frames.append(qa_log[callback_mask].copy().assign(Risk_Type="QA Callback Flag"))
    if not qa_log.empty and "Status" in qa_log.columns:
        rejected = qa_log[qa_log["Status"].apply(normalize_status).eq("Rejected")].copy()
        if not rejected.empty:
            frames.append(rejected.assign(Risk_Type="Rejected QA"))
    if not frames:
        return pd.DataFrame(columns=["Risk_Type", "Province", "District", "Tool Name", "Surveyor_Name", "Status", "Rejection Reason"])
    risk = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    preferred = ["Risk_Type", "Province", "District", "Tool Name", "Surveyor_Name", "Status", "Rejection Reason", "Remark", "QC Date", "Survey_Date"]
    return risk[[column for column in preferred if column in risk.columns]]


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
    status_series = qa_log["Status"].apply(normalize_status)
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


def build_rejection_reason_breakdown(rejected_qa_log: pd.DataFrame, limit: int = 12) -> pd.DataFrame:
    reason_column = first_existing_column(rejected_qa_log, ["Rejection Reason", "Reject Reason", "Reason", "Remark"])
    if rejected_qa_log.empty or not reason_column:
        return pd.DataFrame(columns=["Rejection Reason", "Count"])
    reasons = rejected_qa_log[reason_column].astype(str).str.strip()
    reasons = reasons.replace("", "Unspecified")
    counts = reasons.value_counts().head(limit).reset_index()
    counts.columns = ["Rejection Reason", "Count"]
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
        if "Status" in qa_work.columns:
            qa_work["Status"] = qa_work["Status"].apply(normalize_status)
        else:
            qa_work["Status"] = "Pending"
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
            position: relative;
            overflow: hidden;
            background:
                linear-gradient(145deg, rgba(255,255,255,0.16) 0%, rgba(255,255,255,0.055) 48%, rgba(255,255,255,0.025) 100%),
                linear-gradient(135deg, rgba(10, 18, 37, 0.94) 0%, rgba(6, 13, 29, 0.88) 58%, rgba(3, 8, 20, 0.94) 100%);
            border: 1px solid rgba(226, 232, 240, 0.18);
            border-radius: 16px;
            padding: 18px 19px 17px 19px;
            box-sizing: border-box;
            box-shadow:
                0 22px 58px rgba(0, 0, 0, 0.30),
                inset 0 1px 0 rgba(255,255,255,0.20),
                inset 0 -1px 0 rgba(255,255,255,0.06);
            width: 100%;
            height: 188px;
            min-height: 188px;
            display:flex;
            flex-direction:column;
            justify-content:space-between;
            backdrop-filter: blur(24px) saturate(150%);
            -webkit-backdrop-filter: blur(24px) saturate(150%);
        ">
            <div style="
                position:absolute;
                left:0;
                right:0;
                top:0;
                height:3px;
                background: linear-gradient(90deg, {tone} 0%, rgba(255,255,255,0.86) 48%, rgba(255,255,255,0) 100%);
            "></div>
            <div style="
                position:absolute;
                left:1px;
                right:1px;
                top:1px;
                height:42%;
                background: linear-gradient(180deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0) 100%);
                pointer-events:none;
            "></div>
            <div style="
                position:absolute;
                right:14px;
                top:14px;
                width:34px;
                height:34px;
                border-radius: 11px;
                background: linear-gradient(145deg, {tone} 0%, rgba(255,255,255,0.12) 100%);
                opacity:0.95;
                box-shadow: 0 10px 28px color-mix(in srgb, {tone} 42%, transparent), inset 0 1px 0 rgba(255,255,255,0.34);
            "></div>
            <div style="position:relative; z-index:1;">
                <div style="
                    display:flex;
                    align-items:center;
                    gap:9px;
                    color:#b9c8e7;
                    font-size: 0.72rem;
                    letter-spacing: 0.14em;
                    text-transform: uppercase;
                    font-weight: 900;
                    line-height:1.25;
                    max-width: calc(100% - 52px);
                    min-height: 24px;
                    overflow-wrap:anywhere;
                ">
                    <span style="width:7px; height:7px; border-radius:999px; background:{tone}; box-shadow:0 0 18px {tone}; flex:0 0 auto;"></span>
                    <span>{title}</span>
                </div>
                <div style="
                    font-size: clamp(1.8rem, 2.1vw, 2.35rem);
                    font-weight: 900;
                    color: #f8fbff;
                    margin-top: 14px;
                    line-height:1;
                    letter-spacing: 0;
                    text-shadow: 0 14px 32px rgba(0,0,0,0.36);
                    overflow-wrap:anywhere;
                ">
                    {value}
                </div>
            </div>
            <div style="
                position:relative;
                z-index:1;
                margin-top: 12px;
                padding-top: 10px;
                border-top: 1px solid rgba(226,232,240,0.12);
            ">
                <div style="
                    height:5px;
                    width:74px;
                    border-radius:999px;
                    background: linear-gradient(90deg, {tone} 0%, rgba(255,255,255,0.62) 100%);
                    margin-bottom: 8px;
                    box-shadow: 0 0 24px color-mix(in srgb, {tone} 42%, transparent);
                "></div>
                <div style="
                    font-size: 0.78rem;
                    color: #a9b8d6;
                    line-height: 1.35;
                    font-weight: 600;
                    max-height: 3.95em;
                    overflow:hidden;
                    overflow-wrap:anywhere;
                ">
                    {subtitle}
                </div>
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
            border: 1px solid rgba(226,232,240,0.18);
            border-radius: 14px;
            padding: 16px 18px;
            min-height: 156px;
            box-shadow: 0 16px 40px rgba(0,0,0,0.18), inset 0 2px 0 {tone};
            display:flex;
            flex-direction:column;
            justify-content:space-between;
        ">
            <div style="font-size: 0.82rem; letter-spacing: 0.08em; text-transform: uppercase; color: #d8e3ff; font-weight: 800;">{label}</div>
            <div>
                <div style="display:flex; flex-direction:column; gap:4px; margin-top:12px;">
                    <div style="font-size: 2.15rem; font-weight: 800; color: #ffffff; line-height:1;">{percent:.1f}%</div>
                    <div style="font-size: 0.78rem; color: #b8c7e6; text-transform:uppercase; letter-spacing:0.08em; font-weight:700;">Completed</div>
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


CHART_FONT = "Manrope"
CHART_TEXT = "#dbe7ff"
CHART_MUTED = "#93a4c4"
CHART_GRID = "rgba(219, 231, 255, 0.12)"
CHART_HEIGHT_STANDARD = 360
TABLE_HEIGHT_STANDARD = 360
STATUS_COLORS = {
    "Approved": "#22c55e",
    "Rejected": "#ef4444",
    "Pending": "#f59e0b",
    "Remaining": "#64748b",
    "Checked": "#0f766e",
    "Assigned": "#2563eb",
    "QA Log Records": "#8b5cf6",
    "Summary Completed": "#38bdf8",
    "Clean Completed": "#22c55e",
    "Received": "#38bdf8",
    "QA'd": "#0f766e",
    "Matched QA IDs": "#22c55e",
    "Unmatched QA Rows": "#ef4444",
}


def padded_numeric_domain(values: pd.Series, padding: float = 0.14, minimum: float = 1) -> list[float]:
    numeric_values = pd.to_numeric(values, errors="coerce").fillna(0)
    max_value = float(numeric_values.max()) if not numeric_values.empty else 0
    upper = max(max_value * (1 + padding), minimum)
    return [0, upper]


def modernize_chart(chart: alt.TopLevelMixin) -> alt.TopLevelMixin:
    return (
        chart
        .properties(padding={"top": 18, "right": 16, "bottom": 12, "left": 16})
        .configure(background="transparent")
        .configure_view(strokeOpacity=0)
        .configure_title(
            font=CHART_FONT,
            fontSize=16,
            fontWeight=800,
            color=CHART_TEXT,
            anchor="start",
            offset=22,
            limit=520,
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
            columns=3,
            labelLimit=150,
            titleLimit=150,
            symbolType="circle",
            symbolSize=90,
        )
    )


def render_standard_table(dataframe: pd.DataFrame, height: int = TABLE_HEIGHT_STANDARD) -> None:
    st.dataframe(dataframe, use_container_width=True, hide_index=True, height=height)


def render_bar_chart(
    dataframe: pd.DataFrame,
    category: str,
    title: str,
    color: str,
    value_column: str = "Count",
    height: int = CHART_HEIGHT_STANDARD,
) -> None:
    if dataframe.empty:
        st.info("No data is available for this view.")
        return

    chart_data = dataframe.copy()
    chart_data[value_column] = pd.to_numeric(chart_data[value_column], errors="coerce").fillna(0)
    chart_data = chart_data[chart_data[value_column] > 0].sort_values(value_column, ascending=False).head(14)
    if chart_data.empty:
        st.info("No data is available for this view.")
        return
    x_domain = padded_numeric_domain(chart_data[value_column])

    base = alt.Chart(chart_data).encode(
        x=alt.X(f"{value_column}:Q", title=value_column, axis=alt.Axis(grid=True), scale=alt.Scale(domain=x_domain)),
        y=alt.Y(f"{category}:N", sort="-x", title=None),
        tooltip=[
            alt.Tooltip(f"{category}:N", title=category),
            alt.Tooltip(f"{value_column}:Q", title=value_column, format=","),
        ],
    )
    bars = base.mark_bar(cornerRadiusTopRight=9, cornerRadiusBottomRight=9, color=color, opacity=0.88)
    glow = base.mark_bar(cornerRadiusTopRight=9, cornerRadiusBottomRight=9, color=color, opacity=0.18, size=23)
    labels = base.mark_text(
        align="left",
        baseline="middle",
        dx=7,
        color=CHART_TEXT,
        font=CHART_FONT,
        fontSize=11,
        fontWeight=700,
    ).encode(text=alt.Text(f"{value_column}:Q", format=","))

    chart = (
        alt.layer(glow, bars, labels)
        .properties(height=height, title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_donut_chart(dataframe: pd.DataFrame, category: str, title: str, colors: list[str]) -> None:
    if dataframe.empty:
        st.info("No data is available for this view.")
        return

    chart_data = dataframe.copy()
    chart_data["Count"] = pd.to_numeric(chart_data["Count"], errors="coerce").fillna(0)
    chart_data = chart_data[chart_data["Count"] > 0]
    if chart_data.empty:
        st.info("No data is available for this view.")
        return

    total = int(chart_data["Count"].sum())
    chart_data["Share"] = chart_data["Count"] / total if total else 0
    color_domain = None
    color_range = colors
    if category == "Status":
        color_domain = ["Approved", "Rejected", "Pending", "Remaining", "Call Back", "Unspecified"]
        color_range = [
            STATUS_COLORS["Approved"],
            STATUS_COLORS["Rejected"],
            STATUS_COLORS["Pending"],
            STATUS_COLORS["Remaining"],
            "#8b5cf6",
            "#94a3b8",
        ]
    scale_options = {"range": color_range}
    if color_domain is not None:
        scale_options["domain"] = color_domain
    arc = (
        alt.Chart(chart_data)
        .mark_arc(innerRadius=64, outerRadius=112, cornerRadius=5, padAngle=0.025)
        .encode(
            theta=alt.Theta("Count:Q"),
            color=alt.Color(f"{category}:N", scale=alt.Scale(**scale_options), legend=alt.Legend(title=category)),
            tooltip=[
                alt.Tooltip(f"{category}:N", title=category),
                alt.Tooltip("Count:Q", title="Count", format=","),
                alt.Tooltip("Share:Q", title="Share", format=".1%"),
            ],
        )
    )
    center = (
        alt.Chart(pd.DataFrame({"Total": [f"{total:,}"], "Label": ["total"]}))
        .mark_text(font=CHART_FONT, fontSize=25, fontWeight=800, color=CHART_TEXT, dy=-6)
        .encode(text="Total:N")
    )
    center_label = (
        alt.Chart(pd.DataFrame({"Label": ["records"]}))
        .mark_text(font=CHART_FONT, fontSize=11, fontWeight=700, color=CHART_MUTED, dy=20)
        .encode(text="Label:N")
    )
    chart = alt.layer(arc, center, center_label).properties(
        height=CHART_HEIGHT_STANDARD + 18,
        title=alt.TitleParams(text=title, anchor="start", offset=24),
        padding={"top": 22, "right": 18, "bottom": 16, "left": 18},
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_progress_bullet_chart(progress_dataframe: pd.DataFrame, title: str = "Target Completion Matrix") -> None:
    if progress_dataframe.empty:
        st.info("No progress snapshot is available.")
        return

    chart_data = progress_dataframe.copy()
    for column in ["Target", "Completed", "Completion %"]:
        chart_data[column] = pd.to_numeric(chart_data[column], errors="coerce").fillna(0)
    chart_data["Target Label"] = chart_data["Target"].map(lambda value: f"{int(value):,}")
    chart_data["Completed Label"] = chart_data["Completed"].map(lambda value: f"{int(value):,}")
    chart_data["Percent Label"] = chart_data["Completion %"].map(lambda value: f"{value:.1f}%")
    x_domain = padded_numeric_domain(chart_data["Target"])

    base = alt.Chart(chart_data).encode(
        y=alt.Y("Stream:N", sort=None, title=None),
        tooltip=[
            "Stream:N",
            alt.Tooltip("Target:Q", format=","),
            alt.Tooltip("Completed:Q", format=","),
            alt.Tooltip("Completion %:Q", format=".1f"),
        ],
    )
    target = base.mark_bar(cornerRadius=10, color="rgba(219, 231, 255, 0.16)", size=26).encode(
        x=alt.X("Target:Q", title="Target / Completed", scale=alt.Scale(domain=x_domain))
    )
    completed = base.mark_bar(cornerRadius=10, color="#38bdf8", size=18).encode(
        x=alt.X("Completed:Q", title="Target / Completed", scale=alt.Scale(domain=x_domain))
    )
    marker = base.mark_tick(color="#f8fafc", thickness=3, size=34).encode(x="Target:Q")
    label = base.mark_text(align="left", dx=8, color=CHART_TEXT, font=CHART_FONT, fontWeight=800).encode(
        x="Completed:Q",
        text="Percent Label:N",
    )
    chart = alt.layer(target, completed, marker, label).properties(height=CHART_HEIGHT_STANDARD, title=title)
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_stacked_status_chart(dataframe: pd.DataFrame, id_column: str, value_columns: list[str], title: str, height: int = 360) -> None:
    if dataframe.empty:
        st.info("No data is available for this view.")
        return

    existing_columns = [column for column in value_columns if column in dataframe.columns]
    if not existing_columns or id_column not in dataframe.columns:
        st.info("No data is available for this view.")
        return

    chart_data = dataframe[[id_column, *existing_columns]].copy()
    for column in existing_columns:
        chart_data[column] = pd.to_numeric(chart_data[column], errors="coerce").fillna(0)
    chart_data = chart_data.melt(id_vars=[id_column], value_vars=existing_columns, var_name="Metric", value_name="Count")
    chart_data = chart_data[chart_data["Count"] > 0]
    if chart_data.empty:
        st.info("No data is available for this view.")
        return

    colors = [STATUS_COLORS.get(metric, "#8b5cf6") for metric in existing_columns]
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=7, cornerRadiusBottomRight=7)
        .encode(
            x=alt.X("Count:Q", stack="normalize", title="Share of workload", axis=alt.Axis(format=".0%"), scale=alt.Scale(domain=[0, 1.08])),
            y=alt.Y(f"{id_column}:N", sort="-x", title=None),
            color=alt.Color("Metric:N", scale=alt.Scale(domain=existing_columns, range=colors), legend=alt.Legend(title=None)),
            tooltip=[alt.Tooltip(f"{id_column}:N", title=id_column), "Metric:N", alt.Tooltip("Count:Q", format=",")],
        )
        .properties(height=height, title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_heatmap_chart(dataframe: pd.DataFrame, x_column: str, y_column: str, value_column: str, title: str, color_scheme: str = "tealblues") -> None:
    if dataframe.empty or any(column not in dataframe.columns for column in [x_column, y_column, value_column]):
        st.info("No data is available for this view.")
        return

    chart_data = dataframe.copy()
    chart_data[value_column] = pd.to_numeric(chart_data[value_column], errors="coerce").fillna(0)
    chart = (
        alt.Chart(chart_data)
        .mark_rect(cornerRadius=4)
        .encode(
            x=alt.X(f"{x_column}:N", title=None),
            y=alt.Y(f"{y_column}:N", title=None),
            color=alt.Color(f"{value_column}:Q", scale=alt.Scale(scheme=color_scheme), title=value_column),
            tooltip=[f"{x_column}:N", f"{y_column}:N", alt.Tooltip(f"{value_column}:Q", format=",")],
        )
        .properties(height=CHART_HEIGHT_STANDARD, title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_temporal_status_chart(dataframe: pd.DataFrame, title: str) -> None:
    if dataframe.empty or not {"Date", "Status", "Count"}.issubset(dataframe.columns):
        st.info("No timeline data is available for this view.")
        return
    chart_data = dataframe.copy()
    chart_data["Count"] = pd.to_numeric(chart_data["Count"], errors="coerce").fillna(0)
    color_domain = ["Approved", "Rejected", "Pending", "Remaining", "Call Back", "Unspecified"]
    color_range = [STATUS_COLORS["Approved"], STATUS_COLORS["Rejected"], STATUS_COLORS["Pending"], STATUS_COLORS["Remaining"], "#8b5cf6", "#94a3b8"]
    chart = (
        alt.Chart(chart_data)
        .mark_area(opacity=0.74, interpolate="monotone", line=True, point=True)
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Count:Q", stack="zero", title="QA records"),
            color=alt.Color("Status:N", scale=alt.Scale(domain=color_domain, range=color_range), legend=alt.Legend(title=None)),
            tooltip=["Date:T", "Tool Name:N", "Status:N", alt.Tooltip("Count:Q", format=",")],
        )
        .properties(height=CHART_HEIGHT_STANDARD, title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_reconciliation_chart(dataframe: pd.DataFrame) -> None:
    if dataframe.empty:
        st.info("No reconciliation data is available.")
        return
    chart_data = dataframe.copy()
    chart_data["Variance"] = pd.to_numeric(chart_data["Variance"], errors="coerce").fillna(0)
    chart_data["Abs Variance"] = chart_data["Variance"].abs()
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=8, cornerRadiusBottomRight=8)
        .encode(
            x=alt.X("Variance:Q", title="Sheet minus Summary"),
            y=alt.Y("Source:N", sort="-x", title=None),
            color=alt.condition(alt.datum.Variance == 0, alt.value("#22c55e"), alt.value("#f59e0b")),
            tooltip=["Source:N", "Signal:N", alt.Tooltip("Sheet Count:Q", format=","), alt.Tooltip("Summary Count:Q", format=","), alt.Tooltip("Variance:Q", format=",")],
        )
        .properties(height=CHART_HEIGHT_STANDARD, title="Sheet Reconciliation: Actual vs Summary")
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_coverage_match_chart(dataframe: pd.DataFrame, stream_label: str, title: str, color_scheme: str = "tealblues") -> None:
    if dataframe.empty or not {"Province", "Sample", "QA Matched", "Coverage %"}.issubset(dataframe.columns):
        st.info(f"No province coverage data is available for {stream_label}.")
        return

    chart_data = dataframe.copy()
    for column in ["Sample", "QA Matched", "Coverage %"]:
        chart_data[column] = pd.to_numeric(chart_data[column], errors="coerce").fillna(0)
    chart_data = chart_data.sort_values("Sample", ascending=False).head(14)
    chart_data["Coverage Label"] = chart_data["Coverage %"].map(lambda value: f"{value:.1f}%")
    x_domain = padded_numeric_domain(chart_data["Sample"], padding=0.26)

    base = alt.Chart(chart_data).encode(
        y=alt.Y("Province:N", sort="-x", title=None),
        tooltip=[
            "Province:N",
            alt.Tooltip("Sample:Q", title=f"{stream_label} sample", format=","),
            alt.Tooltip("QA Matched:Q", title="Matched QA", format=","),
            alt.Tooltip("Coverage %:Q", title="Coverage", format=".1f"),
        ],
    )
    sample_bar = base.mark_bar(cornerRadiusTopRight=9, cornerRadiusBottomRight=9, color="rgba(219, 231, 255, 0.14)", size=28).encode(
        x=alt.X("Sample:Q", title=f"{stream_label} sample / matched QA", scale=alt.Scale(domain=x_domain))
    )
    matched_bar = base.mark_bar(cornerRadiusTopRight=9, cornerRadiusBottomRight=9, size=18).encode(
        x=alt.X("QA Matched:Q", title=f"{stream_label} sample / matched QA", scale=alt.Scale(domain=x_domain)),
        color=alt.Color("Coverage %:Q", scale=alt.Scale(scheme=color_scheme), legend=alt.Legend(title="Coverage")),
    )
    coverage_dot = base.mark_circle(size=120, stroke="#f8fafc", strokeWidth=1.5, opacity=0.96).encode(
        x=alt.X("QA Matched:Q", scale=alt.Scale(domain=x_domain)),
        color=alt.Color("Coverage %:Q", scale=alt.Scale(scheme=color_scheme), legend=None),
    )
    labels = base.mark_text(align="left", dx=10, color=CHART_TEXT, font=CHART_FONT, fontSize=11, fontWeight=800).encode(
        x="Sample:Q",
        text="Coverage Label:N",
    )
    chart = alt.layer(sample_bar, matched_bar, coverage_dot, labels).properties(height=CHART_HEIGHT_STANDARD, title=title)
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def build_profile_source(dataframe: pd.DataFrame, profile_columns: list[tuple[str, str]], limit: int = 8) -> pd.DataFrame:
    frames = []
    for column_name, label in profile_columns:
        if column_name not in dataframe.columns:
            continue
        profile_counts = top_counts(dataframe, column_name, limit).rename(columns={column_name: "Value"})
        if profile_counts.empty:
            continue
        frames.append(profile_counts.assign(Profile=label))
    if not frames:
        return pd.DataFrame(columns=["Value", "Count", "Profile", "Display"])
    profile_source = pd.concat(frames, ignore_index=True)
    profile_source["Display"] = profile_source["Profile"] + " - " + profile_source["Value"]
    return profile_source


def render_profile_radar_chart(profile_source: pd.DataFrame, title: str, colors: list[str], height: int = 420) -> None:
    if profile_source.empty:
        st.info("No profile fields are available for this view.")
        return

    chart_data = profile_source.copy()
    chart_data["Count"] = pd.to_numeric(chart_data["Count"], errors="coerce").fillna(0)
    chart_data = chart_data[chart_data["Count"] > 0].sort_values(["Profile", "Count"], ascending=[True, False]).head(24)
    x_domain = padded_numeric_domain(chart_data["Count"], padding=0.32)

    base = alt.Chart(chart_data).encode(
        x=alt.X("Count:Q", title="Count", scale=alt.Scale(domain=x_domain)),
        y=alt.Y("Display:N", sort="-x", title=None),
        color=alt.Color("Profile:N", scale=alt.Scale(range=colors), legend=alt.Legend(title=None)),
        tooltip=["Profile:N", "Value:N", alt.Tooltip("Count:Q", format=",")],
    )
    bars = base.mark_bar(cornerRadiusTopRight=8, cornerRadiusBottomRight=8, opacity=0.84)
    dots = base.mark_circle(size=82, stroke="#f8fafc", strokeWidth=1.2)
    labels = base.mark_text(align="left", dx=8, color=CHART_TEXT, font=CHART_FONT, fontSize=11, fontWeight=800).encode(text=alt.Text("Count:Q", format=","))
    chart = alt.layer(bars, dots, labels).properties(height=height, title=title)
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def render_completeness_chart(completeness: pd.DataFrame, title: str, color: str, height: int = 420) -> None:
    if completeness.empty:
        st.info("No completeness fields are available.")
        return

    chart_data = completeness.copy()
    for column in ["Complete", "Missing", "Complete %"]:
        chart_data[column] = pd.to_numeric(chart_data[column], errors="coerce").fillna(0)
    chart_data["Missing %"] = 100 - chart_data["Complete %"]
    chart_data["Complete Label"] = chart_data["Complete %"].map(lambda value: f"{value:.1f}%")

    base = alt.Chart(chart_data).encode(
        y=alt.Y("Field:N", sort="-x", title=None),
        tooltip=["Field:N", alt.Tooltip("Complete:Q", format=","), alt.Tooltip("Missing:Q", format=","), alt.Tooltip("Complete %:Q", format=".1f")],
    )
    track = base.mark_bar(cornerRadius=9, color="rgba(219, 231, 255, 0.14)", size=20).encode(
        x=alt.X("value:Q", title="Completion rate", scale=alt.Scale(domain=[0, 110])),
    ).transform_calculate(value="100")
    complete = base.mark_bar(cornerRadius=9, color=color, size=14, opacity=0.9).encode(
        x=alt.X("Complete %:Q", title="Completion rate", scale=alt.Scale(domain=[0, 110]))
    )
    labels = base.mark_text(align="left", dx=7, color=CHART_TEXT, font=CHART_FONT, fontSize=11, fontWeight=800).encode(
        x="Complete %:Q",
        text="Complete Label:N",
    )
    chart = alt.layer(track, complete, labels).properties(height=height, title=title)
    st.altair_chart(modernize_chart(chart), use_container_width=True)


def build_sample_health_table(health: dict[str, object], tool_label: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Signal": "Matched QA records", "Value": int(health["qa_records"])},
            {"Signal": f"All {tool_label} QA records", "Value": int(health["qa_total_records"])},
            {"Signal": f"Unmatched {tool_label} QA records", "Value": int(health["qa_unmatched"])},
            {"Signal": "Approved", "Value": int(health["approved"])},
            {"Signal": "Pending", "Value": int(health["pending"])},
            {"Signal": f"{tool_label} positive flags", "Value": int(health["tool_positive"])},
            {"Signal": "Total Data positive flags", "Value": int(health["total_data_positive"])},
            {"Signal": "Missing sample IDs", "Value": int(health["missing_sample_ids"])},
            {"Signal": "Duplicate sample IDs", "Value": int(health["duplicate_ids"])},
        ]
    )


def render_sample_health_signal_chart(health: dict[str, object], title: str, color: str) -> None:
    chart_data = pd.DataFrame(
        [
            {"Stage": "Sample matched", "Metric": "Matched QA IDs", "Count": int(health["qa_matched"])},
            {"Stage": "QA records", "Metric": "Approved", "Count": int(health["approved"])},
            {"Stage": "QA records", "Metric": "Pending", "Count": int(health["pending"])},
            {"Stage": "Integrity", "Metric": "Missing IDs", "Count": int(health["missing_sample_ids"])},
            {"Stage": "Integrity", "Metric": "Duplicate IDs", "Count": int(health["duplicate_ids"])},
        ]
    )
    chart_data = chart_data[chart_data["Count"] > 0]
    if chart_data.empty:
        st.info("No health signals are available for this view.")
        return

    metric_order = ["Matched QA IDs", "Approved", "Pending", "Missing IDs", "Duplicate IDs"]
    color_range = [
        color,
        STATUS_COLORS["Approved"],
        STATUS_COLORS["Pending"],
        "#f97316",
        "#8b5cf6",
    ]
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8)
        .encode(
            x=alt.X("Metric:N", sort=metric_order, title=None, axis=alt.Axis(labelAngle=-22)),
            y=alt.Y("Count:Q", title="Records"),
            color=alt.Color("Metric:N", scale=alt.Scale(domain=metric_order, range=color_range), legend=None),
            tooltip=["Stage:N", "Metric:N", alt.Tooltip("Count:Q", format=",")],
        )
        .properties(height=300, title=title)
    )
    st.altair_chart(modernize_chart(chart), use_container_width=True)


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
progress_snapshot = build_progress_snapshot(summary_data)
completion_cards = build_completion_cards(progress_snapshot)

if tls_data.empty and ece_data.empty and not summary_rows and qa_log_data.empty:
    st.warning("The dashboard could not load data from the configured worksheets.")
    st.stop()

all_regions = unique_filter_values([tls_data, ece_data], "Region")

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

    region_scoped_tls = apply_filters(tls_data, selected_regions, [], [])
    region_scoped_ece = apply_filters(ece_data, selected_regions, [], [])
    all_provinces = unique_filter_values([region_scoped_tls, region_scoped_ece], "Province")

    with filter_cols[1]:
        selected_provinces = st.multiselect("Province", all_provinces, placeholder="All provinces")
        selected_provinces = [province for province in selected_provinces if province in all_provinces]

    province_scoped_tls = apply_filters(tls_data, selected_regions, selected_provinces, [])
    province_scoped_ece = apply_filters(ece_data, selected_regions, selected_provinces, [])
    all_districts = unique_filter_values([province_scoped_tls, province_scoped_ece], "District")

    with filter_cols[2]:
        selected_districts = st.multiselect("District", all_districts, placeholder="All districts")
        selected_districts = [district for district in selected_districts if district in all_districts]

filtered_tls = apply_filters(tls_data, selected_regions, selected_provinces, selected_districts)
filtered_ece = apply_filters(ece_data, selected_regions, selected_provinces, selected_districts)
log_scope_districts = selected_districts
if selected_provinces:
    log_scope_provinces = selected_provinces
elif selected_regions:
    log_scope_provinces = unique_filter_values([region_scoped_tls, region_scoped_ece], "Province")
else:
    log_scope_provinces = []

filtered_qa_log_all_data = apply_log_filters(qa_log_data, log_scope_provinces, log_scope_districts)
filtered_rejected_qa_log_data = only_status(filtered_qa_log_all_data, "Rejected")
filtered_qa_log_data = exclude_status(filtered_qa_log_all_data, "Rejected")
filtered_correction_log_data = apply_log_filters(correction_log_data, log_scope_provinces, log_scope_districts)
filtered_rejection_log_data = apply_log_filters(rejection_log_data, log_scope_provinces, log_scope_districts)
filtered_red_flag_log_data = apply_log_filters(red_flag_log_data, log_scope_provinces, log_scope_districts)
filtered_callback_log_data = apply_log_filters(callback_log_data, log_scope_provinces, log_scope_districts)

qa_status_breakdown = build_log_status_breakdown(filtered_qa_log_data)
qa_tool_mix = build_tool_mix(filtered_qa_log_data)
rejected_tool_mix = build_tool_mix(filtered_rejected_qa_log_data)
rejection_reason_breakdown = build_rejection_reason_breakdown(filtered_rejected_qa_log_data)
surveyor_command_table = build_surveyor_table(summary_data["enumerator_performance"], filtered_qa_log_data)
tool_summary = build_tool_summary(summary_data, filtered_qa_log_data)

total_tls = len(filtered_tls)
total_ece = len(filtered_ece)
combined_total = total_tls + total_ece
sample_progress_data = summary_data["sample_progress"]
tls_collection_target = (
    safe_int(sample_progress_data.loc[sample_progress_data["Metric"] == "TLS Sample Target", "Value"].max())
    if not sample_progress_data.empty
    else 0
)
ece_collection_target = (
    safe_int(sample_progress_data.loc[sample_progress_data["Metric"] == "ECE Sample Target", "Value"].max())
    if not sample_progress_data.empty
    else 0
)
tls_collection_target = tls_collection_target or DEFAULT_TLS_COLLECTION_TARGET
ece_collection_target = ece_collection_target or DEFAULT_ECE_COLLECTION_TARGET
collection_target_total = tls_collection_target + ece_collection_target
qa_log_total = len(filtered_qa_log_data)
qa_log_all_total = len(filtered_qa_log_all_data)
qa_rejected_total = len(filtered_rejected_qa_log_data)
rejection_total = len(filtered_rejection_log_data)
correction_total = len(filtered_correction_log_data)
red_flag_total = len(filtered_red_flag_log_data)
callback_total = len(filtered_callback_log_data)
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
tls_health = build_sample_health(filtered_tls, filtered_qa_log_data, "TLS", ["Tool 5", "TLS Tool 5"])
ece_health = build_sample_health(filtered_ece, filtered_qa_log_data, "ECE", ["Tool 2", "Tool 3", "ECE Tool 2", "ECE Parent Tool 3"])
tls_rejected_health = build_sample_health(filtered_tls, filtered_rejected_qa_log_data, "TLS", ["Tool 5", "TLS Tool 5"])
ece_rejected_health = build_sample_health(filtered_ece, filtered_rejected_qa_log_data, "ECE", ["Tool 2", "Tool 3", "ECE Tool 2", "ECE Parent Tool 3"])
combined_qa_matched = int(tls_health["qa_matched"]) + int(ece_health["qa_matched"])
combined_qa_coverage = round((combined_qa_matched / collection_target_total) * 100, 1) if collection_target_total else 0
combined_rejected_matched = int(tls_rejected_health["qa_matched"]) + int(ece_rejected_health["qa_matched"])
remaining_collection_target = max(collection_target_total - combined_qa_matched, 0)
sheet_reconciliation = build_sheet_reconciliation(summary_data, filtered_tls, filtered_ece, filtered_qa_log_data, filtered_red_flag_log_data, filtered_callback_log_data)
risk_sheet_reconciliation = build_sheet_reconciliation(summary_data, filtered_tls, filtered_ece, filtered_qa_log_all_data, filtered_red_flag_log_data, filtered_callback_log_data)
sample_match_table = build_sample_qa_match_table(tls_health, ece_health, filtered_tls, filtered_ece)
command_completion_table = build_command_completion_table(
    tls_health,
    ece_health,
    tls_rejected_health,
    ece_rejected_health,
    tls_collection_target,
    ece_collection_target,
)
sample_geo_matrix = build_sample_geo_matrix(filtered_tls, filtered_ece)
qa_audit_matrix = build_qa_audit_matrix(filtered_qa_log_data)
qa_timeline = build_qa_timeline(filtered_qa_log_data)
risk_register = build_risk_register(filtered_red_flag_log_data, filtered_callback_log_data, filtered_qa_log_all_data)

metric_cols = st.columns(4, gap="large")
with metric_cols[0]:
    render_metric_card("QA Coverage", f"{combined_qa_coverage:.1f}%", f"{combined_qa_matched:,} clean matched QA against target.", "#16a34a")
with metric_cols[1]:
    render_metric_card(
        "Collection Target",
        f"{collection_target_total:,}",
        f"TLS {tls_collection_target:,} + ECE {ece_collection_target:,}; raw universe {combined_total:,}.",
        "#2563eb",
    )
with metric_cols[2]:
    render_metric_card("Operational Risk Flags", f"{red_flag_total + rejection_total + callback_total:,}", f"Red flags {red_flag_total}; rejections {rejection_total}; callbacks {callback_total}.", "#f97316")
with metric_cols[3]:
    render_metric_card("Summary Update", f"{summary_data['updated_date'] or 'N/A'}", f"Last QA log time {summary_data['updated_time'] or 'N/A'}.", "#7c3aed")

overview_tab, command_tab, summary_tab, risk_tab, tls_tab, ece_tab = st.tabs(["Overview", "Command Center", "Summary", "QA & Risk", "TLS Sample", "ECE Sample"])

with overview_tab:
    render_section_header("Executive Overview", "A consolidated decision layer combining sample coverage, Summary progress, and operational QA signals.")

    summary_top_left, summary_top_right = st.columns(2, gap="large")
    with summary_top_left:
        render_progress_bullet_chart(progress_snapshot, "Sample Progress: Target vs Completed")
    with summary_top_right:
        if not qa_status_breakdown.empty:
            render_donut_chart(qa_status_breakdown, "Status", "Clean QA Status Mix", ["#22c55e", "#f59e0b", "#64748b", "#2563eb"])
        else:
            st.info("No QA status data is available yet.")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
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
                "Count": [tls_collection_target, ece_collection_target],
            }
        )
        render_donut_chart(sample_mix, "Sample Type", "TLS vs ECE Collection Target", ["#16a34a", "#f97316"])

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
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

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    insights_left, insights_right = st.columns(2, gap="large")
    with insights_left:
        qa_progress = summary_data["qa_progress"]
        if not qa_progress.empty:
            render_stacked_status_chart(
                qa_progress,
                "Tool Name",
                ["Approved", "Pending", "Remaining"],
                "Clean QA Status Composition by Tool",
                height=340,
            )
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
                    border: 1px solid rgba(148, 163, 184, 0.30);
                    border-radius: 14px;
                    padding: 14px 16px;
                    margin-bottom: 12px;
                    box-shadow: inset 0 2px 0 {color}, 0 10px 26px rgba(15,23,42,0.06);
                ">
                    <div style="font-size: 0.82rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700;">{label}</div>
                    <div style="font-size: 1.7rem; font-weight: 800; color: #0f172a; margin-top: 6px;">{value:,}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    intelligence_left, intelligence_right = st.columns(2, gap="large")
    with intelligence_left:
        if not sample_geo_matrix.empty:
            render_heatmap_chart(sample_geo_matrix, "District", "Province", "Count", "Sample Density Heatmap by Province and District", "viridis")
        else:
            st.info("No sample density matrix is available for this filter.")
    with intelligence_right:
        render_reconciliation_chart(sheet_reconciliation)

with command_tab:
    render_section_header("Command Center", "Clean completion excludes rejected QA records; rejected data is tracked as a separate operational signal.")

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
    command_metrics = st.columns(5, gap="large")
    with command_metrics[0]:
        render_metric_card("Collection Target", f"{collection_target_total:,}", f"TLS: {tls_collection_target:,}; ECE: {ece_collection_target:,}.", "#2563eb")
    with command_metrics[1]:
        render_metric_card("Clean Completed", f"{combined_qa_matched:,}", "Matched QA records after excluding Status = Rejected.", "#16a34a")
    with command_metrics[2]:
        render_metric_card("Rejected QA", f"{combined_rejected_matched:,}", "Matched rejected QA records tracked outside clean completion.", "#ef4444")
    with command_metrics[3]:
        render_metric_card("Remaining Target", f"{remaining_collection_target:,}", "Target still not covered by clean matched QA.", "#f97316")
    with command_metrics[4]:
        render_metric_card("Active Surveyors", f"{len(surveyor_command_table):,}", "Surveyors tracked from clean QA activity and Summary roster.", "#7c3aed")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    command_left, command_right = st.columns(2, gap="large")
    with command_left:
        if not surveyor_command_table.empty:
            top_surveyors = surveyor_command_table.sort_values(["QA_Log_Records", "Approved_Log", "Received"], ascending=False).head(15)
            render_bar_chart(top_surveyors, "Surveyor_Name", "Top Surveyors by Clean QA Records", "#38bdf8", value_column="QA_Log_Records")
        else:
            st.info("No surveyor command data is available.")
    with command_right:
        if not rejected_tool_mix.empty:
            render_donut_chart(rejected_tool_mix, "Tool Name", "Rejected QA Tool Mix", ["#ef4444", "#f97316", "#8b5cf6", "#64748b", "#2563eb"])
        else:
            st.info("No rejected QA tool mix is available yet.")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    match_left, match_right = st.columns(2, gap="large")
    with match_left:
        render_stacked_status_chart(
            command_completion_table,
            "Stream",
            ["Clean Completed", "Rejected", "Remaining"],
            "Clean Completion vs Rejected by Stream",
            height=360,
        )
    with match_right:
        st.markdown("### Command Completion Table")
        render_standard_table(command_completion_table)

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    command_signal_left, command_signal_right = st.columns(2, gap="large")
    with command_signal_left:
        if not qa_tool_mix.empty:
            render_donut_chart(qa_tool_mix, "Tool Name", "Clean QA Tool Mix", ["#2563eb", "#22c55e", "#f97316", "#7c3aed", "#0f766e"])
        else:
            st.info("No clean QA tool mix is available yet.")
    with command_signal_right:
        render_reconciliation_chart(sheet_reconciliation)

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
            render_stacked_status_chart(
                qa_by_data,
                "QA By",
                ["Assigned", "Checked", "Approved", "Rejected", "Pending", "Remaining"],
                "QA Team Workload and Outcomes",
                height=360,
            )
        else:
            st.info("No QA-by-person data is available in Summary.")

    with summary_layout_right:
        if not owner_progress.empty:
            st.markdown("### Current Summary Snapshot")
            render_standard_table(owner_progress)
        else:
            st.info("No owner progress snapshot is available in Summary.")

        st.markdown("### Last Update")
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(145deg, #f8fafc 0%, #eef2ff 100%);
                border: 1px solid rgba(37, 99, 235, 0.12);
                border-radius: 14px;
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
        render_progress_bullet_chart(progress_snapshot, "Stream Progress Against Target")
    with progress_right:
        completion_rank = progress_snapshot[["Stream", "Completion %"]].copy() if not progress_snapshot.empty else pd.DataFrame(columns=["Stream", "Completion %"])
        render_bar_chart(completion_rank, "Stream", "Completion Rate Leaderboard", "#22c55e", value_column="Completion %")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
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

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    detail_left, detail_right = st.columns(2, gap="large")
    with detail_left:
        if not summary_data["sample_progress"].empty:
            render_bar_chart(summary_data["sample_progress"], "Metric", "Summary Sample and Completion Status", "#2563eb", value_column="Value")
        else:
            st.info("No sample progress rows are available in Summary.")
    with detail_right:
        if not filtered_qa_log_data.empty:
            recent_columns = [column for column in ["Tool Name", "Province", "District", "Surveyor_Name", "Survey_Date", "Status"] if column in filtered_qa_log_data.columns]
            st.markdown("### Latest Clean QA Log Entries")
            render_standard_table(filtered_qa_log_data[recent_columns].tail(10), height=360)
        else:
            st.info("No QA log records are available for the selected filter.")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    qa_by_table = summary_data["qa_by"]
    qa_by_left, qa_by_right = st.columns(2, gap="large")
    with qa_by_left:
        if not qa_by_table.empty:
            render_stacked_status_chart(
                qa_by_table,
                "QA By",
                ["Assigned", "Checked", "Approved", "Rejected", "Pending", "Remaining"],
                "QA By Performance Matrix",
                height=360,
            )
        else:
            st.info("No QA By data is available.")
    with qa_by_right:
        st.markdown("### QA By Detail Table")
        if not qa_by_table.empty:
            render_standard_table(qa_by_table)
        else:
            st.info("No QA By detail table is available.")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    tools_left, tools_right = st.columns(2, gap="large")
    with tools_left:
        if not tool_summary.empty:
            render_stacked_status_chart(
                tool_summary,
                "Tool Name",
                ["Summary Completed", "QA Log Records", "Approved", "Pending", "Remaining"],
                "Tool-Level Clean QA Overview",
                height=360,
            )
        else:
            st.info("No tool-level summary is available.")
    with tools_right:
        st.markdown("### Tool Summary Table")
        if not tool_summary.empty:
            render_standard_table(tool_summary)
        else:
            st.info("No tool summary table is available.")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    surveyor_left, surveyor_right = st.columns(2, gap="large")
    with surveyor_left:
        if not surveyor_command_table.empty:
            render_stacked_status_chart(
                surveyor_command_table.head(25),
                "Surveyor_Name",
                ["Received", "QA'd", "Approved", "Pending", "QA_Log_Records"],
                "Surveyor Performance and Clean QA Activity",
                height=520,
            )
        else:
            st.info("No surveyor performance data is available.")
    with surveyor_right:
        st.markdown("### Full Surveyor Table")
        if not surveyor_command_table.empty:
            render_standard_table(surveyor_command_table, height=520)
        else:
            st.info("No surveyor table is available.")

with risk_tab:
    render_section_header("QA and Risk Intelligence", "Rejected QA is monitored separately while clean QA logic excludes rejected rows from coverage and progress signals.")

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
    risk_metrics = st.columns(5, gap="large")
    with risk_metrics[0]:
        render_metric_card("QA Scope Records", f"{qa_log_all_total:,}", "All QA_Log rows inside the selected geographic scope.", "#2563eb")
    with risk_metrics[1]:
        render_metric_card("Clean QA Records", f"{qa_log_total:,}", "QA_Log rows after excluding Status = Rejected.", "#22c55e")
    with risk_metrics[2]:
        render_metric_card("Rejected QA", f"{qa_rejected_total:,}", "Rejected records are tracked here, not counted in clean QA logic.", "#ef4444")
    with risk_metrics[3]:
        render_metric_card("Red Flags", f"{len(filtered_red_flag_log_data):,}", "Records available in the Red-Flag sheet for this scope.", "#f97316")
    with risk_metrics[4]:
        render_metric_card("Call Backs", f"{len(filtered_callback_log_data):,}", "Records available in the Call-Back sheet for this scope.", "#8b5cf6")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    risk_top_left, risk_top_right = st.columns(2, gap="large")
    with risk_top_left:
        render_temporal_status_chart(qa_timeline, "Clean QA Timeline by QC Date and Status")
    with risk_top_right:
        if not qa_audit_matrix.empty:
            render_heatmap_chart(qa_audit_matrix, "Status", "Audit Field", "Filled %", "Clean QA Evidence Completeness Matrix", "plasma")
        else:
            st.info("No QA audit matrix is available for this filter.")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    risk_mid_left, risk_mid_right = st.columns(2, gap="large")
    with risk_mid_left:
        if not filtered_qa_log_data.empty and {"Province", "Status"}.issubset(filtered_qa_log_data.columns):
            qa_status_province = filtered_qa_log_data.copy()
            qa_status_province["Status"] = qa_status_province["Status"].apply(normalize_status)
            qa_status_province = qa_status_province.groupby(["Province", "Status"]).size().reset_index(name="Count")
            render_heatmap_chart(qa_status_province, "Status", "Province", "Count", "Clean QA Outcome Heatmap by Province", "magma")
        else:
            st.info("No province-level QA status data is available.")
    with risk_mid_right:
        if not risk_register.empty:
            risk_mix = risk_register.groupby("Risk_Type").size().reset_index(name="Count")
            render_donut_chart(risk_mix, "Risk_Type", "Risk Register Mix", ["#ef4444", "#f97316", "#8b5cf6", "#64748b"])
        else:
            st.info("No risk records are available in Red-Flag, Call-Back, or QA rejection/callback flags for this filter.")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    rejected_left, rejected_right = st.columns(2, gap="large")
    with rejected_left:
        if not rejected_tool_mix.empty:
            render_donut_chart(rejected_tool_mix, "Tool Name", "Rejected QA by Tool", ["#ef4444", "#f97316", "#8b5cf6", "#64748b", "#2563eb"])
        else:
            st.info("No rejected QA tool mix is available for this filter.")
    with rejected_right:
        if not rejection_reason_breakdown.empty:
            render_bar_chart(rejection_reason_breakdown, "Rejection Reason", "Top Rejection Reasons", "#ef4444")
        else:
            st.info("No rejection reason data is available for this filter.")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    register_left, register_right = st.columns(2, gap="large")
    with register_left:
        st.markdown("### Full QA Sheet Reconciliation Table")
        render_standard_table(risk_sheet_reconciliation, height=520)
    with register_right:
        st.markdown("### Risk Register")
        if not risk_register.empty:
            render_standard_table(risk_register.tail(50), height=520)
        else:
            st.info("No risk register rows are available for the selected filter.")

with tls_tab:
    render_section_header("TLS Sample Command View", "Aligned monitoring view for TLS sample volume, Tool 5 QA match coverage, profile distribution, completeness, and operational records.")

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
    tls_metrics = st.columns(5, gap="large")
    with tls_metrics[0]:
        render_metric_card("TLS Records", f"{len(filtered_tls):,}", "Filtered rows from the current TLS-Sample worksheet.", "#16a34a")
    with tls_metrics[1]:
        render_metric_card("Tool 5 QA Coverage", f"{float(tls_health['qa_coverage']):.1f}%", f"{int(tls_health['qa_matched']):,} current TLS IDs matched; {int(tls_health['qa_unmatched']):,} Tool 5 QA rows are unmatched.", "#2563eb")
    with tls_metrics[2]:
        render_metric_card("Matched Approved / Pending", f"{int(tls_health['approved']):,} / {int(tls_health['pending']):,}", "Tool 5 clean QA outcomes after excluding rejected rows.", "#f59e0b")
    with tls_metrics[3]:
        render_metric_card("Unique Classes", f"{count_unique(filtered_tls, 'Class_Code'):,}", "Distinct classroom codes in the current filter.", "#7c3aed")
    with tls_metrics[4]:
        render_metric_card("Data Issues", f"{int(tls_health['missing_critical']) + int(tls_health['duplicate_ids']):,}", f"Missing critical fields: {int(tls_health['missing_critical']):,}; duplicate IDs: {int(tls_health['duplicate_ids']):,}.", "#ef4444")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    tls_command_left, tls_command_right = st.columns(2, gap="large")
    with tls_command_left:
        tls_geo_coverage = build_geo_coverage(
            filtered_tls,
            tls_health["qa_subset"],
            tls_health["sample_id_column"],
            tls_health["qa_id_column"],
        )
        render_coverage_match_chart(tls_geo_coverage, "TLS", "TLS Province Coverage and QA Match", "tealblues")

    with tls_command_right:
        tls_status_counts = tls_health["status_counts"]
        if isinstance(tls_status_counts, pd.DataFrame) and not tls_status_counts.empty:
            render_donut_chart(tls_status_counts, "Status", "Matched Tool 5 Clean QA Status", ["#22c55e", "#f59e0b", "#64748b"])
        else:
            st.info("No matched Tool 5 QA status is available for the selected TLS scope.")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    tls_profile_left, tls_profile_right = st.columns(2, gap="large")
    with tls_profile_left:
        tls_profile_source = build_profile_source(
            filtered_tls,
            [("TLS_Type", "TLS Type"), ("TLS_Gender", "Gender"), ("Class_Shift", "Shift")],
        )
        render_profile_radar_chart(tls_profile_source, "TLS Segment Profile", ["#16a34a", "#2563eb", "#f97316"])

    with tls_profile_right:
        tls_completeness = build_completeness_table(
            filtered_tls,
            [
                "TPM_TLS_ID",
                "Region",
                "Province",
                "District",
                "Village",
                "TLS_SN",
                "Class_Code",
                "IP",
                "Donor",
                "Classroom_Infra",
                "TLS_Classes",
                "TLS_Gender",
                "Class_Shift",
                "TLS_Type",
                "TLS_Grades",
                "Active_SMS",
                "PS_Name",
                "PS_Code",
                "Instruction_Language",
                "Total Data",
                "Tool 5",
            ],
        )
        render_completeness_chart(tls_completeness, "TLS Field Completeness", "#0f766e")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    tls_health_left, tls_health_right = st.columns(2, gap="large")
    with tls_health_left:
        render_sample_health_signal_chart(tls_health, "TLS Clean QA and Integrity Signals", "#16a34a")
    with tls_health_right:
        st.markdown("### TLS Sample Health")
        render_standard_table(build_sample_health_table(tls_health, "Tool 5"), height=300)

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    tls_table_left, tls_table_right = st.columns(2, gap="large")
    recent_tls_qa_columns = [
        column
        for column in ["Tool Name", "Province", "District", "Village", "PB_Name", "TPM-ID (ECE, TLS)", "Surveyor_Name", "Survey_Date", "QC By", "QC Date", "Status", "Rejection Reason"]
        if column in tls_health["qa_subset"].columns
    ]
    with tls_table_left:
        if recent_tls_qa_columns:
            st.markdown("### Latest Matched Tool 5 Clean QA")
            render_standard_table(tls_health["qa_subset"][recent_tls_qa_columns].tail(12), height=520)
        else:
            st.info("No matched Tool 5 QA rows are available for this TLS scope.")

    with tls_table_right:
        st.markdown("### TLS Operational Sample Table")
        tls_standard_columns = [
            "TPM_TLS_ID",
            "Region",
            "Province",
            "District",
            "Village",
            "TLS_SN",
            "Class_Code",
            "IP",
            "Donor",
            "TLS_Type",
            "TLS_Grades",
            "TLS_Gender",
            "Class_Shift",
            "Active_SMS",
            "PS_Name",
            "PS_Code",
            "Instruction_Language",
            "Total Data",
            "Tool 5",
        ]
        render_standard_table(build_standard_view(filtered_tls, tls_standard_columns), height=520)

with ece_tab:
    render_section_header("ECE Sample Command View", "Aligned monitoring view for ECE sample volume, Tool 2/3 QA match coverage, profile distribution, completeness, and operational records.")

    st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
    ece_metrics = st.columns(5, gap="large")
    with ece_metrics[0]:
        render_metric_card("ECE Records", f"{len(filtered_ece):,}", "Filtered row count from the ECE sample.", "#f97316")
    with ece_metrics[1]:
        render_metric_card("QA Coverage", f"{float(ece_health['qa_coverage']):.1f}%", f"{int(ece_health['qa_matched']):,} ECE IDs matched; {int(ece_health['qa_unmatched']):,} ECE QA rows are unmatched.", "#2563eb")
    with ece_metrics[2]:
        render_metric_card("Approved / Pending", f"{int(ece_health['approved']):,} / {int(ece_health['pending']):,}", "Tool 2/3 clean QA outcomes after excluding rejected rows.", "#16a34a")
    with ece_metrics[3]:
        missing_pb = 0
        if "PB_Name" in filtered_ece.columns:
            missing_pb = int(filtered_ece["PB_Name"].astype(str).str.strip().eq("").sum())
        render_metric_card("Missing PB Name", f"{missing_pb:,}", "Rows where the PB name is not available.", "#ef4444")
    with ece_metrics[4]:
        render_metric_card("Unique ECE IDs", f"{count_unique(filtered_ece, 'sample_ECE_ID'):,}", "Distinct sample ECE identifiers.", "#7c3aed")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    ece_command_left, ece_command_right = st.columns(2, gap="large")
    with ece_command_left:
        ece_geo_coverage = build_geo_coverage(
            filtered_ece,
            ece_health["qa_subset"],
            ece_health["sample_id_column"],
            ece_health["qa_id_column"],
        )
        render_coverage_match_chart(ece_geo_coverage, "ECE", "ECE Province Coverage and QA Match", "orangered")

    with ece_command_right:
        ece_status_counts = ece_health["status_counts"]
        if isinstance(ece_status_counts, pd.DataFrame) and not ece_status_counts.empty:
            render_donut_chart(ece_status_counts, "Status", "Matched ECE Clean QA Status", ["#22c55e", "#f59e0b", "#64748b"])
        else:
            st.info("No matched ECE QA status is available for the selected ECE scope.")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    ece_profile_left, ece_profile_right = st.columns(2, gap="large")
    with ece_profile_left:
        ece_profile_source = build_profile_source(
            filtered_ece,
            [("Climate", "Climate"), ("Province", "Province"), ("District", "District")],
        )
        render_profile_radar_chart(ece_profile_source, "ECE Segment Profile", ["#f97316", "#2563eb", "#0f766e"])

    with ece_profile_right:
        ece_completeness = build_completeness_table(
            filtered_ece,
            [
                "TPM_ECE_ID",
                "Region",
                "Province",
                "District",
                "Climate",
                "sample_ECE_ID",
                "PB_EMIS_Code",
                "PB_Name",
                "Total Data",
                "Tool 2",
                "Tool 3",
            ],
        )
        render_completeness_chart(ece_completeness, "ECE Field Completeness", "#f97316")

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    ece_health_left, ece_health_right = st.columns(2, gap="large")
    with ece_health_left:
        render_sample_health_signal_chart(ece_health, "ECE Clean QA and Integrity Signals", "#f97316")
    with ece_health_right:
        st.markdown("### ECE Sample Health")
        render_standard_table(build_sample_health_table(ece_health, "Tool 2/3"), height=300)

    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    ece_table_left, ece_table_right = st.columns(2, gap="large")
    recent_ece_qa_columns = [
        column
        for column in ["Tool Name", "Province", "District", "Village", "PB_Name", "TPM-ID (ECE, TLS)", "Surveyor_Name", "Survey_Date", "QC By", "QC Date", "Status", "Rejection Reason"]
        if column in ece_health["qa_subset"].columns
    ]
    with ece_table_left:
        if recent_ece_qa_columns:
            st.markdown("### Latest Matched Tool 2/3 Clean QA")
            render_standard_table(ece_health["qa_subset"][recent_ece_qa_columns].tail(12), height=520)
        else:
            st.info("No matched Tool 2/3 QA rows are available for this ECE scope.")

    with ece_table_right:
        st.markdown("### ECE Operational Sample Table")
        ece_standard_columns = ["TPM_ECE_ID", "Region", "Province", "District", "Climate", "sample_ECE_ID", "PB_EMIS_Code", "PB_Name", "Total Data", "Tool 2", "Tool 3"]
        render_standard_table(build_standard_view(filtered_ece, ece_standard_columns), height=520)
