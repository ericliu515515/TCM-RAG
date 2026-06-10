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
    --chat-control-height: 3.25rem;
    padding: 0.75rem 0 0.25rem 0;
    margin-top: 1.25rem;
    border: 0 !important;
    box-shadow: none !important;
}

div[data-testid="stForm"] [data-testid="stTextInput"],
div[data-testid="stForm"] [data-testid="stTextInput"] > div,
div[data-testid="stForm"] [data-testid="stTextInput"] div[data-baseweb="input"] {
    height: var(--chat-control-height) !important;
    min-height: var(--chat-control-height) !important;
    max-height: var(--chat-control-height) !important;
}

div[data-testid="stForm"] [data-testid="InputInstructions"] {
    display: none !important;
}

div[data-testid="stForm"] textarea,
div[data-testid="stForm"] input[type="text"] {
    box-sizing: border-box !important;
    height: var(--chat-control-height) !important;
    line-height: var(--chat-control-height) !important;
    min-height: var(--chat-control-height) !important;
    max-height: var(--chat-control-height) !important;
    padding: 0 1rem !important;
    border-radius: 1.35rem !important;
    resize: none;
}

div[data-testid="stForm"] button {
    align-items: center;
    border-radius: 0.5rem;
    display: flex;
    height: var(--chat-control-height) !important;
    justify-content: center;
    max-height: var(--chat-control-height) !important;
    max-width: var(--chat-control-height) !important;
    min-height: var(--chat-control-height) !important;
    min-width: var(--chat-control-height) !important;
    padding: 0 !important;
    width: var(--chat-control-height) !important;
}

div[data-testid="stForm"] [data-testid="stFormSubmitButton"] {
    display: flex;
    justify-content: flex-end;
}

div[data-testid="stForm"] button p {
    display: none;
}

div[data-testid="stForm"] [data-testid="stVerticalBlock"] {
    gap: 0;
}

div[data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    align-items: center;
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
