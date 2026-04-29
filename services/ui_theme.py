from __future__ import annotations

import streamlit as st


def apply_liquid_glass_theme(
    page_title: str,
    page_description: str,
    accent: str = "#8b5cf6",
    eyebrow_label: str | None = None,
    compact_hero: bool = False,
) -> None:
    eyebrow = eyebrow_label or page_title
    hero_padding = "18px 24px" if compact_hero else "30px 32px"
    eyebrow_padding = "0.38rem 0.75rem" if compact_hero else "0.5rem 0.9rem"
    eyebrow_font = "0.7rem" if compact_hero else "0.75rem"
    title_size = "clamp(1.8rem, 2.3vw, 2.7rem)" if compact_hero else "clamp(2.2rem, 3vw, 3.9rem)"
    title_margin = "0.55rem" if compact_hero else "1rem"
    copy_margin = "0.55rem" if compact_hero else "1rem"
    copy_size = "0.93rem" if compact_hero else "1.03rem"
    copy_line = "1.55" if compact_hero else "1.72"
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

        :root {{
            --glass-accent: {accent};
            --glass-accent-soft: rgba(139, 92, 246, 0.22);
            --glass-text: #e8eefc;
            --glass-muted: #a9b8d6;
            --glass-panel: rgba(8, 15, 34, 0.52);
            --glass-panel-strong: rgba(6, 13, 29, 0.74);
            --glass-border: rgba(255, 255, 255, 0.16);
            --glass-highlight: rgba(255, 255, 255, 0.18);
            --glass-shadow: 0 24px 80px rgba(1, 6, 20, 0.45);
        }}

        html, body, [class*="css"] {{
            font-family: "Manrope", sans-serif;
        }}

        [data-testid="stAppViewContainer"] {{
            background:
                radial-gradient(circle at 15% 20%, rgba(56, 189, 248, 0.22), transparent 28%),
                radial-gradient(circle at 85% 18%, rgba(139, 92, 246, 0.24), transparent 30%),
                radial-gradient(circle at 70% 78%, rgba(34, 197, 94, 0.18), transparent 24%),
                linear-gradient(180deg, #020611 0%, #071428 46%, #08111d 100%);
            color: var(--glass-text);
        }}

        [data-testid="stHeader"] {{
            background: rgba(2, 6, 17, 0.16);
        }}

        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, rgba(8, 15, 34, 0.86) 0%, rgba(4, 10, 24, 0.92) 100%);
            border-right: 1px solid rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(22px);
        }}

        [data-testid="stSidebar"] * {{
            color: #dce7ff !important;
        }}

        .block-container {{
            max-width: 1480px;
            padding-top: 1.35rem;
            padding-bottom: 2.4rem;
        }}

        .glass-hero {{
            position: relative;
            overflow: hidden;
            padding: {hero_padding};
            border-radius: 30px;
            background:
                linear-gradient(135deg, rgba(255,255,255,0.16) 0%, rgba(255,255,255,0.06) 100%),
                linear-gradient(135deg, rgba(34,197,94,0.10) 0%, rgba(59,130,246,0.10) 45%, rgba(139,92,246,0.16) 100%);
            border: 1px solid var(--glass-border);
            box-shadow: var(--glass-shadow);
            backdrop-filter: blur(28px) saturate(145%);
            -webkit-backdrop-filter: blur(28px) saturate(145%);
        }}

        .glass-hero::before {{
            content: "";
            position: absolute;
            inset: 1px;
            border-radius: 29px;
            background: linear-gradient(180deg, rgba(255,255,255,0.16), rgba(255,255,255,0.03));
            pointer-events: none;
        }}

        .glass-eyebrow {{
            position: relative;
            z-index: 1;
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            padding: {eyebrow_padding};
            border-radius: 999px;
            background: rgba(255,255,255,0.12);
            border: 1px solid rgba(255,255,255,0.14);
            color: #f4f7ff;
            font-size: {eyebrow_font};
            font-weight: 800;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }}

        .glass-title {{
            position: relative;
            z-index: 1;
            margin-top: {title_margin};
            margin-bottom: 0;
            color: #f8fbff;
            font-size: {title_size};
            line-height: 1.04;
            font-weight: 800;
            letter-spacing: -0.04em;
        }}

        .glass-copy {{
            position: relative;
            z-index: 1;
            max-width: 900px;
            margin-top: {copy_margin};
            color: var(--glass-muted);
            font-size: {copy_size};
            line-height: {copy_line};
        }}

        .glass-panel {{
            background: linear-gradient(180deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.06) 100%);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 24px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.28);
            backdrop-filter: blur(24px) saturate(145%);
            -webkit-backdrop-filter: blur(24px) saturate(145%);
            padding: 1.15rem 1.2rem;
            margin-bottom: 1rem;
        }}

        .glass-panel h1, .glass-panel h2, .glass-panel h3, .glass-panel h4, .glass-panel p, .glass-panel label {{
            color: var(--glass-text) !important;
        }}

        .glass-chip-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-top: 1rem;
            position: relative;
            z-index: 1;
        }}

        .glass-chip {{
            padding: 0.7rem 0.95rem;
            border-radius: 16px;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.12);
            color: #dfe9ff;
            font-size: 0.92rem;
            font-weight: 600;
        }}

        .stButton > button,
        div[data-testid="stFormSubmitButton"] > button {{
            border-radius: 16px !important;
            border: 1px solid rgba(255,255,255,0.16) !important;
            background:
                linear-gradient(135deg, rgba(255,255,255,0.20) 0%, rgba(255,255,255,0.06) 100%),
                linear-gradient(135deg, {accent} 0%, rgba(59,130,246,0.92) 100%) !important;
            color: #f9fbff !important;
            font-weight: 800 !important;
            letter-spacing: 0.01em;
            min-height: 3rem;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.22);
        }}

        .stButton > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover {{
            border-color: rgba(255,255,255,0.28) !important;
            transform: translateY(-1px);
        }}

        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        textarea,
        input {{
            background: rgba(10, 18, 37, 0.62) !important;
            color: #f8fbff !important;
            border-radius: 16px !important;
            border: 1px solid rgba(255,255,255,0.10) !important;
            backdrop-filter: blur(18px);
        }}

        div[data-baseweb="select"] {{
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }}

        div[data-baseweb="select"] span,
        div[data-baseweb="select"] input,
        div[data-baseweb="tag"] {{
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }}

        label, .stMarkdown, .stCaption, .stTextInput label, .stMultiSelect label, .stSelectbox label {{
            color: #dbe7ff !important;
        }}

        [data-testid="stFileUploader"] section {{
            background: rgba(8, 15, 34, 0.50);
            border: 1px dashed rgba(255,255,255,0.16);
            border-radius: 24px;
            backdrop-filter: blur(24px);
        }}

        [data-testid="stDataFrame"],
        [data-testid="stTable"] {{
            background: transparent !important;
            border-radius: 0 !important;
            border: none !important;
            box-shadow: none !important;
            overflow: visible !important;
        }}

        [data-testid="stDataFrame"] > div,
        [data-testid="stTable"] > div,
        [data-testid="stDataFrameGlideDataEditor"],
        [data-testid="stDataFrameResizable"] {{
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }}

        [data-testid="stDataFrame"] canvas,
        [data-testid="stDataFrame"] [role="grid"],
        [data-testid="stDataFrame"] [data-testid="stElementToolbar"],
        [data-testid="stTable"] table {{
            background: transparent !important;
        }}

        [data-testid="stVegaLiteChart"],
        [data-testid="stArrowVegaLiteChart"],
        [data-testid="stPlotlyChart"],
        [data-testid="stDeckGlJsonChart"] {{
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }}

        [data-testid="stVegaLiteChart"] > div,
        [data-testid="stArrowVegaLiteChart"] > div,
        [data-testid="stPlotlyChart"] > div,
        [data-testid="stDeckGlJsonChart"] > div {{
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }}

        [data-testid="stMetric"] {{
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 22px;
            padding: 1rem 1rem 0.8rem 1rem;
            backdrop-filter: blur(22px);
            margin-bottom: 0.85rem;
        }}

        [data-testid="column"] > div {{
            padding-bottom: 0.35rem;
        }}

        .stMultiSelect,
        .stSelectbox,
        .stTextInput,
        .stFileUploader,
        .stDataFrame,
        .stTable,
        .stAlert {{
            margin-bottom: 0.9rem;
        }}

        [data-testid="stMetricLabel"],
        [data-testid="stMetricValue"] {{
            color: #f3f7ff !important;
        }}

        div[role="tablist"] {{
            gap: 0.55rem;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 0.4rem;
            backdrop-filter: blur(18px);
            margin-top: 1rem;
            margin-bottom: 1rem;
        }}

        button[role="tab"] {{
            border-radius: 14px !important;
            color: #dce7ff !important;
            font-weight: 700 !important;
        }}

        button[role="tab"][aria-selected="true"] {{
            background: rgba(255,255,255,0.12) !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
        }}

        div[data-testid="stAlert"] {{
            background: rgba(9, 17, 38, 0.56) !important;
            border: 1px solid rgba(255,255,255,0.10) !important;
            border-radius: 20px !important;
            backdrop-filter: blur(22px);
        }}

        hr {{
            border-color: rgba(255,255,255,0.08);
        }}
        </style>

        <div class="glass-hero">
            <div class="glass-eyebrow">{eyebrow}</div>
            <h1 class="glass-title">{page_title}</h1>
            <div class="glass-copy">{page_description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_glass_section(title: str, description: str | None = None) -> None:
    description_html = f'<div style="color:#a9b8d6; margin-top:0.35rem; line-height:1.6;">{description}</div>' if description else ""
    st.markdown(
        f"""
        <div class="glass-panel" style="margin-top: 1.15rem; margin-bottom: 1rem;">
            <div style="font-size: 1.18rem; font-weight: 800; color: #f8fbff;">{title}</div>
            {description_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_glass_chip_row(items: list[str]) -> None:
    chips = "".join(f'<div class="glass-chip">{item}</div>' for item in items)
    st.markdown(f'<div class="glass-chip-row">{chips}</div>', unsafe_allow_html=True)
