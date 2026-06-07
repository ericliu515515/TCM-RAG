from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
USER_UPLOADS_DIR = PROJECT_ROOT / "docs" / "user_uploads"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

load_dotenv(PROJECT_ROOT / ".env")
USER_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@st.cache_resource
def load_ask_tcm():
    from tcmagent.rag import ask_tcm

    return ask_tcm


st.set_page_config(
    page_title="TCM Citation RAG",
    page_icon="",
    layout="centered",
)

st.title("TCM Citation RAG")
st.caption("Ask a Traditional Chinese Medicine question and retrieve cited context.")
st.markdown(
    """
    <style>
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
    </style>
    """,
    unsafe_allow_html=True,
)


if "messages" not in st.session_state:
    st.session_state.messages = []


def render_assistant_details(message: dict) -> None:
    search_question = message.get("search_question")
    scores = message.get("scores")
    sources = message.get("sources")

    if search_question:
        with st.expander("Standalone retrieval question"):
            st.write(search_question)

    if scores is not None:
        with st.expander("Retrieval scores"):
            st.caption("FAISS distance score: lower means more related.")
            st.write(scores)

    if sources:
        with st.expander("Sources"):
            for index, source in enumerate(sources, start=1):
                citation = source.get("citation_markdown", "No citation")
                page = source.get("pdf_page", "unknown")

                st.markdown(f"**Source {index} - page {page}**")
                st.markdown(citation)
                st.json(source)
    elif sources == []:
        st.info("No source passed the retrieval threshold.")


def render_chat_message(message: dict) -> None:
    st.markdown(message["content"])

    if message["role"] == "assistant":
        render_assistant_details(message)


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Status")
        st.write("Vector store: `docs/faiss_openai_test_embedding_3_small`")
        st.write("Threshold: `MAX_DISTANCE = 1.3`")

        if os.getenv("OPENAI_API_KEY"):
            st.success("OPENAI_API_KEY is set.")
        else:
            st.warning("OPENAI_API_KEY is not set.")

        if st.button("New chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        st.caption("Educational demo only. Not medical advice.")


def replay_chat_history() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            render_chat_message(message)


def install_ime_safe_enter_submit() -> None:
    components.html(
        """
        <script>
        (() => {
            const attachImeSafeEnter = () => {
                const doc = window.parent.document;
                const forms = Array.from(doc.querySelectorAll('div[data-testid="stForm"]'));
                const form = forms[forms.length - 1];

                if (!form) return;

                const textarea = form.querySelector('textarea');
                const button = form.querySelector('button');

                if (!textarea || !button || textarea.dataset.imeSafeEnterInstalled === "true") {
                    return;
                }

                textarea.dataset.imeSafeEnterInstalled = "true";
                let composing = false;

                textarea.addEventListener("compositionstart", () => {
                    composing = true;
                });

                textarea.addEventListener("compositionend", () => {
                    setTimeout(() => {
                        composing = false;
                    }, 0);
                });

                textarea.addEventListener("keydown", (event) => {
                    if (event.key !== "Enter") return;
                    if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return;
                    if (event.isComposing || composing || event.keyCode === 229) return;

                    event.preventDefault();
                    button.click();
                });
            };

            attachImeSafeEnter();

            const observer = new MutationObserver(attachImeSafeEnter);
            observer.observe(window.parent.document.body, {
                childList: true,
                subtree: true,
            });
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def handle_user_question() -> None:
    new_turn_container = st.container()
    with st.form("chat_input_form", clear_on_submit=True):
        input_column, send_column = st.columns([12, 1], vertical_alignment="bottom")

        with input_column:
            question = st.text_area(
                "Message",
                placeholder="Ask a TCM question...",
                height=68,
                label_visibility="collapsed",
            )

        with send_column:
            submitted = st.form_submit_button(
                "Send",
                type="primary",
                icon=":material/send:",
                help="Send message",
                use_container_width=True,
            )

    install_ime_safe_enter_submit()

    if not submitted:
        return

    question = question.strip()
    if not question:
        st.warning("Please enter a question.")
        st.stop()

    chat_history = list(st.session_state.messages)
    user_message = {
        "role": "user",
        "content": question,
    }
    st.session_state.messages.append(user_message)

    with new_turn_container:
        with st.chat_message("user"):
            render_chat_message(user_message)

    with new_turn_container:
        with st.chat_message("assistant"):
            try:
                ask_tcm = load_ask_tcm()
                with st.spinner("Retrieving sources and generating answer..."):
                    result = ask_tcm(question, chat_history=chat_history)

            except Exception as exc:
                st.error("The RAG pipeline failed to run.")
                st.exception(exc)
                st.stop()

            assistant_message = {
                "role": "assistant",
                "content": result["answer"],
                "sources": result.get("sources", []),
                "scores": result.get("scores", []),
                "search_question": result.get("search_question"),
            }
            render_chat_message(assistant_message)
            st.session_state.messages.append(assistant_message)


render_sidebar()
replay_chat_history()
handle_user_question()
