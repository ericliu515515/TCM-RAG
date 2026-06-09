from __future__ import annotations

import streamlit as st


GLOBAL_STYLES = """
<style>
section[data-testid="stSidebar"] > div,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
section[data-testid="stSidebar"] .block-container {
    margin-top: 0 !important;
    padding-top: 0 !important;
}

section[data-testid="stSidebar"] [data-testid="stVerticalBlock"],
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:first-child,
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
    margin-top: 0 !important;
    padding-top: 0 !important;
}

div[data-testid="stForm"] {
    padding: 0.75rem 0 0.25rem 0;
    margin-top: 1.25rem;
    border: 0 !important;
    box-shadow: none !important;
}

div[data-testid="stForm"] textarea {
    min-height: 46px !important;
    max-height: 76px !important;
    padding: 0.7rem 1rem !important;
    border-radius: 1.35rem !important;
    resize: none;
}

div[data-testid="stForm"] button {
    min-height: 46px;
    max-height: 46px;
    width: 100%;
    border-radius: 999px;
    padding-left: 0.7rem;
    padding-right: 0.7rem;
}

div[data-testid="stForm"] button p {
    display: none;
}

div[data-testid="stForm"] [data-testid="stVerticalBlock"] {
    gap: 0;
}

div[data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    align-items: end;
    gap: 0.45rem;
}

.st-key-doc_window_panel {
    border: 1px solid rgba(49, 51, 63, 0.2);
    border-radius: 0.5rem;
    padding: 0.45rem;
    margin-bottom: 1rem;
}

div[class*="st-key-select_window_"] button,
div[class*="st-key-close_window_"] button {
    min-height: 2.35rem;
    max-height: 2.35rem;
    margin: 0 !important;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

div[class*="st-key-select_window_close_"] button {
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
}

div[class*="st-key-close_window_"] button {
    border-top-left-radius: 0;
    border-bottom-left-radius: 0;
    width: 2.4rem;
    padding-left: 0;
    padding-right: 0;
}

div[class*="st-key-pdf_page_controls_"] button,
div[class*="st-key-pdf_page_controls_"] input {
    min-height: 2.5rem;
    max-height: 2.5rem;
    white-space: nowrap;
}
</style>
"""


def apply_global_styles() -> None:
    st.markdown(GLOBAL_STYLES, unsafe_allow_html=True)
