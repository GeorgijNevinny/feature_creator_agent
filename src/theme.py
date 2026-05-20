"""Material-inspired theme (Google-like): Roboto, #1a73e8, symmetric surfaces."""

from __future__ import annotations

import streamlit as st

# Google / Material 3 palette
_GOOGLE_BLUE = "#1a73e8"
_GOOGLE_BLUE_HOVER = "#1765cc"
_GOOGLE_GREEN = "#1e8e3e"
_GOOGLE_TEXT = "#202124"
_GOOGLE_TEXT_SECONDARY = "#5f6368"
_GOOGLE_SURFACE = "#ffffff"
_GOOGLE_BG = "#f8f9fa"
_GOOGLE_BORDER = "#dadce0"
_GOOGLE_BORDER_LIGHT = "#e8eaed"


def inject_theme() -> None:
    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Roboto:wght@400;500;700&display=swap');

:root {{
  --google-blue: {_GOOGLE_BLUE};
  --google-blue-hover: {_GOOGLE_BLUE_HOVER};
  --google-green: {_GOOGLE_GREEN};
  --google-text: {_GOOGLE_TEXT};
  --google-text-secondary: {_GOOGLE_TEXT_SECONDARY};
  --google-surface: {_GOOGLE_SURFACE};
  --google-bg: {_GOOGLE_BG};
  --google-border: {_GOOGLE_BORDER};
  --google-border-light: {_GOOGLE_BORDER_LIGHT};
  --elevation-1: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
  --elevation-2: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 2px 6px 2px rgba(60, 64, 67, 0.15);
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;
  --content-max: 880px;
}}

.stApp {{
  font-family: "Google Sans", "Roboto", system-ui, sans-serif;
  background: var(--google-bg);
  color: var(--google-text);
}}

[data-testid="stHeader"] {{
  background: var(--google-surface) !important;
  border-bottom: 1px solid var(--google-border-light);
  box-shadow: none !important;
}}

[data-testid="stSidebar"] {{
  background: var(--google-surface) !important;
  border-right: 1px solid var(--google-border-light) !important;
  box-shadow: none !important;
}}

[data-testid="stSidebar"] > div:first-child {{
  padding-top: 1.25rem;
}}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{
  font-family: "Google Sans", "Roboto", sans-serif !important;
  font-weight: 500 !important;
  color: var(--google-text) !important;
  font-size: 1.125rem !important;
}}

[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{
  color: var(--google-text-secondary) !important;
  font-size: 0.875rem !important;
}}

.main .block-container {{
  padding-top: 2.5rem;
  padding-bottom: 4rem;
  max-width: var(--content-max);
  margin-left: auto !important;
  margin-right: auto !important;
  padding-left: 1.5rem;
  padding-right: 1.5rem;
}}

.app-header {{
  text-align: center;
  margin: 0 auto 2rem;
  max-width: 36rem;
}}

h1.app-page-title {{
  font-family: "Google Sans", "Roboto", sans-serif !important;
  font-weight: 400 !important;
  font-size: 2.25rem !important;
  letter-spacing: -0.02em !important;
  color: var(--google-text) !important;
  text-align: center !important;
  margin: 0 0 0.5rem 0 !important;
  line-height: 1.2 !important;
}}

p.app-page-subtitle {{
  text-align: center;
  color: var(--google-text-secondary);
  font-size: 0.9375rem;
  line-height: 1.6;
  margin: 0 auto;
  font-weight: 400;
}}

.section-heading {{
  font-family: "Google Sans", "Roboto", sans-serif !important;
  font-weight: 500 !important;
  font-size: 1.125rem !important;
  color: var(--google-text) !important;
  letter-spacing: 0;
  margin: 0 0 1rem 0 !important;
  padding: 0 0 0.75rem 0;
  border-bottom: 1px solid var(--google-border-light);
}}

.section-heading--spaced {{
  margin-top: 2rem !important;
}}

.notice-panel {{
  background: var(--google-surface);
  border: 1px solid var(--google-border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--elevation-1);
  padding: 1.25rem 1.5rem;
  margin: 0 0 1.25rem 0;
  color: var(--google-text);
  font-size: 0.875rem;
  line-height: 1.55;
}}

.upload-hint-card {{
  text-align: center;
  margin: 1rem 0 0;
  padding: 1rem 1.25rem;
  border-radius: var(--radius-md);
  background: #f1f3f4;
  border: none;
  color: var(--google-text-secondary);
  font-size: 0.875rem;
  line-height: 1.5;
}}

.file-meta-bar {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
  margin: 0 0 1.25rem;
}}

.file-meta-chip {{
  display: inline-flex;
  align-items: center;
  padding: 0.375rem 0.875rem;
  border-radius: var(--radius-xl);
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--google-text);
  background: #e8f0fe;
  border: none;
}}

.file-meta-chip:first-child {{
  background: #f1f3f4;
  color: var(--google-text-secondary);
}}

.summary-grid {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}}

@media (max-width: 640px) {{
  .summary-grid {{ grid-template-columns: 1fr; }}
}}

.summary-card {{
  border: 1px solid var(--google-border-light);
  border-radius: var(--radius-md);
  padding: 1rem 1.125rem;
  background: #fafafa;
  box-shadow: none;
  height: 100%;
}}

.summary-card h4 {{
  margin: 0 0 0.35rem;
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--google-text-secondary);
}}

.summary-card p {{
  margin: 0;
  font-size: 0.875rem;
  color: var(--google-text);
  line-height: 1.5;
}}

.stTabs [data-baseweb="tab-list"] {{
  gap: 4px;
  padding: 4px;
  background: #f1f3f4;
  border-radius: var(--radius-md);
  border-bottom: none !important;
}}

.stTabs [data-baseweb="tab"] {{
  border-radius: var(--radius-sm);
  color: var(--google-text-secondary);
  font-family: "Google Sans", "Roboto", sans-serif !important;
  font-weight: 500 !important;
  font-size: 0.875rem !important;
}}

.stTabs [aria-selected="true"] {{
  color: var(--google-blue) !important;
  background: var(--google-surface) !important;
  box-shadow: var(--elevation-1);
}}

.stButton > button[kind="primary"] {{
  background: var(--google-blue) !important;
  color: #fff !important;
  border: none !important;
  font-family: "Google Sans", "Roboto", sans-serif !important;
  font-weight: 500 !important;
  font-size: 0.875rem !important;
  border-radius: var(--radius-xl) !important;
  padding: 0.625rem 1.5rem !important;
  box-shadow: none !important;
  letter-spacing: 0.01em;
  transition: background 0.15s ease, box-shadow 0.15s ease !important;
}}

.stButton > button[kind="primary"]:hover {{
  background: var(--google-blue-hover) !important;
  box-shadow: var(--elevation-1) !important;
}}

.stButton > button[kind="secondary"] {{
  border-radius: var(--radius-xl) !important;
  border-color: var(--google-border) !important;
  color: var(--google-blue) !important;
  font-weight: 500 !important;
}}

[data-testid="stFileUploader"] {{
  width: 100%;
}}

[data-testid="stFileUploaderDropzone"] {{
  background: var(--google-surface) !important;
  border: 1px dashed var(--google-border) !important;
  border-radius: var(--radius-lg) !important;
  min-height: 7.5rem !important;
  padding: 1.5rem !important;
  transition: border-color 0.2s ease, background 0.2s ease !important;
  box-shadow: none !important;
}}

[data-testid="stFileUploaderDropzone"]:hover {{
  border-color: var(--google-blue) !important;
  background: #f8f9fa !important;
}}

[data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderDropzoneInstructions"] {{
  justify-content: center !important;
  text-align: center !important;
}}

[data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderDropzoneInstructions"] span {{
  color: var(--google-text-secondary) !important;
  font-size: 0.875rem !important;
}}

[data-testid="stFileUploaderDropzone"] button {{
  border-radius: var(--radius-xl) !important;
  border: 1px solid var(--google-border) !important;
  color: var(--google-blue) !important;
  font-weight: 500 !important;
  background: var(--google-surface) !important;
}}

div[data-testid="stAlert"] {{
  border-radius: var(--radius-md) !important;
  border: 1px solid var(--google-border-light) !important;
  border-left: 4px solid var(--google-blue) !important;
  background: var(--google-surface) !important;
  box-shadow: var(--elevation-1) !important;
  font-size: 0.875rem !important;
}}

[data-testid="stProgress"] > div > div {{
  background: #e8eaed !important;
  border-radius: 999px !important;
  height: 4px !important;
}}

[data-testid="stProgress"] > div > div > div {{
  background: var(--google-blue) !important;
  border-radius: 999px !important;
}}

[data-testid="stDataFrame"] {{
  border: 1px solid var(--google-border-light);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--elevation-1);
}}

[data-testid="stExpander"] {{
  border: 1px solid var(--google-border-light) !important;
  border-radius: var(--radius-md) !important;
  background: var(--google-surface) !important;
  box-shadow: none !important;
}}

[data-testid="stCaptionContainer"] {{
  color: var(--google-text-secondary) !important;
}}

div[data-testid="stVerticalBlockBorderWrapper"] {{
  border: 1px solid var(--google-border-light) !important;
  border-radius: var(--radius-lg) !important;
  background: var(--google-surface) !important;
  box-shadow: var(--elevation-1) !important;
  padding: 0.5rem 1rem 1rem !important;
  margin-bottom: 1.25rem !important;
}}

[data-testid="stDownloadButton"] button {{
  border-radius: var(--radius-xl) !important;
  border: 1px solid var(--google-border) !important;
  color: var(--google-blue) !important;
  font-weight: 500 !important;
  background: var(--google-surface) !important;
}}

#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
</style>
        """,
        unsafe_allow_html=True,
    )
