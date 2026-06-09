from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tcmagent.ai_chunking import run_ai_chunking  # noqa: E402
from tcmagent.web.chat_sessions import (  # noqa: E402
    chat_file_path,
    load_chat_sessions,
    read_chat_file,
    save_chat_session,
    session_label,
)
from tcmagent.web.config import (  # noqa: E402
    DEFAULT_VECTORSTORE_LABEL,
    MAX_MAX_DISTANCE,
    MIN_MAX_DISTANCE,
    clamp_max_distance,
    ensure_app_environment,
    load_app_settings,
    write_app_settings,
)
from tcmagent.web.documents import (  # noqa: E402
    chunks_window_id,
    delete_document_source,
    format_chunk_texts,
    is_uploaded_source,
    load_document_sources,
    load_source_chunks,
    local_pdf_path,
    pdf_page_count,
    pdf_window_id,
    render_pdf_page_image,
    save_uploaded_pdf,
    source_for_id,
    source_label,
)
from tcmagent.web.styles import apply_global_styles  # noqa: E402


ensure_app_environment()


@st.cache_resource
def load_ask_tcm():
    from tcmagent.rag import ask_tcm

    return ask_tcm


st.set_page_config(
    page_title="TCM Citation RAG",
    page_icon="",
    layout="centered",
)

apply_global_styles()

app_settings = load_app_settings()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

if "current_chat_title" not in st.session_state:
    st.session_state.current_chat_title = "Unsaved chat"

if "max_distance" not in st.session_state:
    st.session_state.max_distance = app_settings["max_distance"]

if "app_windows" not in st.session_state:
    st.session_state.app_windows = []

if "active_top_panel" not in st.session_state:
    st.session_state.active_top_panel = "chat"

if "top_panel_selection" not in st.session_state:
    st.session_state.top_panel_selection = st.session_state.active_top_panel

if "pending_top_panel_selection" not in st.session_state:
    st.session_state.pending_top_panel_selection = None

if "active_document_window_id" not in st.session_state:
    st.session_state.active_document_window_id = "documents"

if "pending_selected_source_id" not in st.session_state:
    st.session_state.pending_selected_source_id = None

if "chunking_notice" not in st.session_state:
    st.session_state.chunking_notice = None


def request_top_panel(panel_id: str) -> None:
    st.session_state.active_top_panel = panel_id
    st.session_state.pending_top_panel_selection = panel_id


def request_selected_source(source_id: str | None) -> None:
    st.session_state.pending_selected_source_id = source_id or ""


def render_assistant_details(message: dict) -> None:
    search_question = message.get("search_question")
    scores = message.get("scores")
    sources = message.get("sources")
    max_distance = message.get("max_distance")

    if search_question:
        with st.expander("Standalone retrieval question"):
            st.write(search_question)

    if scores is not None:
        with st.expander("Retrieval scores"):
            st.caption("FAISS distance score: lower means more related.")
            if max_distance is not None:
                st.caption(
                    f"Threshold used: threshold = {clamp_max_distance(max_distance):.2f}"
                )
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


def save_app_settings() -> None:
    st.session_state.max_distance = clamp_max_distance(st.session_state.max_distance)
    write_app_settings(st.session_state.max_distance)


def open_chunks_window(source: dict) -> None:
    window_id = chunks_window_id(source["id"])
    windows = list(st.session_state.app_windows)

    if not any(window.get("id") == window_id for window in windows):
        windows.append({
            "id": window_id,
            "title": f"{source['display_name']} chunks",
            "type": "chunks",
            "source_id": source["id"],
        })

    st.session_state.app_windows = windows
    request_top_panel("documents")
    st.session_state.active_document_window_id = window_id


def open_pdf_window(source: dict) -> None:
    window_id = pdf_window_id(source["id"])
    windows = list(st.session_state.app_windows)

    if not any(window.get("id") == window_id for window in windows):
        windows.append({
            "id": window_id,
            "title": f"{source['display_name']} PDF",
            "type": "pdf",
            "source_id": source["id"],
        })

    st.session_state.app_windows = windows
    request_top_panel("documents")
    st.session_state.active_document_window_id = window_id


def close_window(window_id: str) -> None:
    st.session_state.app_windows = [
        window for window in st.session_state.app_windows if window.get("id") != window_id
    ]

    if st.session_state.active_document_window_id == window_id:
        st.session_state.active_document_window_id = "documents"


def close_source_windows(source_id: str) -> None:
    closed_window_ids = {
        window.get("id")
        for window in st.session_state.app_windows
        if window.get("source_id") == source_id
    }
    st.session_state.app_windows = [
        window
        for window in st.session_state.app_windows
        if window.get("source_id") != source_id
    ]

    if st.session_state.active_document_window_id in closed_window_ids:
        st.session_state.active_document_window_id = "documents"


def render_pdf_upload() -> None:
    uploaded_pdf = st.file_uploader(
        "Upload PDF",
        type=["pdf"],
        accept_multiple_files=False,
    )
    submitted = st.button("Save uploaded PDF", use_container_width=True)

    if not submitted:
        return

    if uploaded_pdf is None:
        st.warning("Choose a PDF before saving.")
        return

    try:
        metadata = save_uploaded_pdf(uploaded_pdf)
    except Exception as exc:
        st.error("Could not save the uploaded PDF.")
        st.exception(exc)
        return

    request_selected_source(metadata["id"])
    request_top_panel("documents")
    st.session_state.active_document_window_id = "documents"
    st.success("PDF saved. Chunking has not been run yet.")
    st.rerun()


def render_delete_document_control(source: dict, remaining_source_ids: list[str]) -> None:
    if not is_uploaded_source(source):
        return

    with st.expander("Delete uploaded document"):
        st.warning("This removes the uploaded PDF folder from docs/sources.")
        confirm_key = f"confirm_delete_source_{source['id']}"
        confirmed = st.checkbox(
            f"Delete {source['display_name']}",
            key=confirm_key,
        )

        if st.button(
            "Delete uploaded document",
            disabled=not confirmed,
            use_container_width=True,
        ):
            try:
                delete_document_source(source)
            except Exception as exc:
                st.error("Could not delete this uploaded document.")
                st.exception(exc)
                return

            close_source_windows(source["id"])
            request_selected_source(remaining_source_ids[0] if remaining_source_ids else None)
            request_top_panel("documents")
            st.success("Uploaded document deleted.")
            st.rerun()


def render_chunking_notice(source: dict) -> None:
    notice = st.session_state.get("chunking_notice")
    if not notice or notice.get("source_id") != source["id"]:
        return

    if notice.get("kind") == "success":
        st.success(notice["message"])
    else:
        st.error(notice["message"])

    st.session_state.chunking_notice = None


def render_chunking_status(source: dict) -> None:
    chunking = source["metadata"].get("chunking")
    if not isinstance(chunking, dict):
        return

    status = str(chunking.get("status") or "unknown")
    latest_run_id = str(chunking.get("latest_run_id") or "unknown")
    st.caption(f"Chunking status: `{status}` from `{latest_run_id}`")

    judge_report = chunking.get("judge_report")
    if isinstance(judge_report, dict):
        score = judge_report.get("score", "unknown")
        passed = judge_report.get("pass", False)
        st.caption(f"Judge: `{'pass' if passed else 'fail'}` score `{score}`")


def render_ai_chunking_control(source: dict, chunks: list[dict], pdf_path: Path | None) -> None:
    if not is_uploaded_source(source):
        return

    label = "Regenerate chunks" if chunks else "Generate chunks"
    if st.button(label, disabled=pdf_path is None, use_container_width=True):
        if not os.getenv("OPENAI_API_KEY"):
            st.session_state.chunking_notice = {
                "source_id": source["id"],
                "kind": "error",
                "message": "OPENAI_API_KEY is required to generate and judge chunks.",
            }
            st.rerun()

        try:
            with st.spinner("Generating, validating, and judging chunks..."):
                result = run_ai_chunking(source)
        except Exception as exc:
            st.session_state.chunking_notice = {
                "source_id": source["id"],
                "kind": "error",
                "message": f"Chunking failed: {exc}",
            }
            st.rerun()

        if result.get("accepted"):
            st.session_state.chunking_notice = {
                "source_id": source["id"],
                "kind": "success",
                "message": f"Chunks accepted from `{result['run_id']}`.",
            }
        else:
            st.session_state.chunking_notice = {
                "source_id": source["id"],
                "kind": "error",
                "message": (
                    "Chunking did not pass quality review. "
                    f"Latest run: `{result.get('run_id', 'unknown')}`."
                ),
            }

        st.rerun()


def render_document_window() -> None:
    st.title("Documents")
    sources = load_document_sources()

    if not sources:
        st.info("No uploaded documents found.")
        render_pdf_upload()
        return

    source_by_id = {source["id"]: source for source in sources}
    source_ids = list(source_by_id)

    pending_source_id = st.session_state.get("pending_selected_source_id")
    current_source_id = st.session_state.get("selected_source_id")

    if pending_source_id is not None:
        if "selected_source_id" in st.session_state:
            del st.session_state["selected_source_id"]

        current_source_id = pending_source_id if pending_source_id in source_by_id else None
        st.session_state.pending_selected_source_id = None

    selected_index = 0

    if current_source_id in source_by_id:
        selected_index = source_ids.index(current_source_id)

    selected_source_id = st.selectbox(
        "Uploaded documents",
        source_ids,
        index=selected_index,
        format_func=lambda source_id: source_label(source_by_id[source_id]),
        key="selected_source_id",
    )
    source = source_by_id[selected_source_id]
    remaining_source_ids = [
        source_id for source_id in source_ids if source_id != selected_source_id
    ]
    chunks = load_source_chunks(source["chunks_path"])
    pdf_path = local_pdf_path(source)

    render_chunking_notice(source)
    render_chunking_status(source)

    st.caption(f"Chunks: `{len(chunks)}`")

    for filename in source["document_files"]:
        st.write(f"Document: `{filename}`")

    if st.button("Open PDF window", disabled=pdf_path is None, use_container_width=True):
        open_pdf_window(source)
        st.rerun()

    if st.button(
        "Open chunk texts window",
        disabled=not chunks,
        use_container_width=True,
    ):
        open_chunks_window(source)
        st.rerun()

    if not chunks:
        st.info("No chunks found for this document.")

    render_ai_chunking_control(source, chunks, pdf_path)
    render_delete_document_control(source, remaining_source_ids)

    st.divider()
    render_pdf_upload()


def render_chat_header() -> None:
    st.title("TCM Citation RAG")
    st.caption("Ask a Traditional Chinese Medicine question and retrieve cited context.")


def top_panel_options() -> list[str]:
    return ["chat", "documents"]


def top_panel_label(panel_id: str) -> str:
    return {
        "chat": "Chat",
        "documents": "Document",
    }[panel_id]


def render_top_panel() -> None:
    pending_panel = st.session_state.get("pending_top_panel_selection")

    if pending_panel in top_panel_options():
        st.session_state.active_top_panel = pending_panel
        st.session_state.top_panel_selection = pending_panel
        st.session_state.pending_top_panel_selection = None

    with st.container(border=True):
        selected_panel = st.segmented_control(
            "Main navigation",
            top_panel_options(),
            format_func=top_panel_label,
            key="top_panel_selection",
            label_visibility="collapsed",
            width="stretch",
        )

    if selected_panel and selected_panel != st.session_state.active_top_panel:
        st.session_state.active_top_panel = selected_panel


def document_window_items() -> list[dict]:
    return [{"id": "documents", "title": "Documents", "type": "documents"}] + list(
        st.session_state.app_windows
    )


def active_document_window() -> dict:
    windows = document_window_items()

    for window in windows:
        if window["id"] == st.session_state.active_document_window_id:
            return window

    st.session_state.active_document_window_id = "documents"
    return windows[0]


def document_window_label(window_id: str) -> str:
    for window in document_window_items():
        if window["id"] == window_id:
            return window["title"]

    return "Documents"


def render_document_window_bar() -> None:
    windows = document_window_items()

    if len(windows) <= 1:
        return

    active_id = active_document_window()["id"]
    column_widths = []

    for index, window in enumerate(windows):
        if window["id"] == "documents":
            column_widths.append(2.2)
        else:
            column_widths.extend([4.2, 0.55])

        if index < len(windows) - 1:
            column_widths.append(0.25)

    with st.container(
        key="doc_window_panel",
    ):
        columns = st.columns(column_widths, gap=None, vertical_alignment="center")
        column_index = 0

        for window in windows:
            window_id = window["id"]
            key_suffix = re.sub(r"[^a-zA-Z0-9_]+", "_", window_id)

            if window_id == "documents":
                with columns[column_index]:
                    if st.button(
                        window["title"],
                        key=f"select_window_single_{key_suffix}",
                        type="primary" if window_id == active_id else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state.active_document_window_id = window_id
                        st.rerun()

                column_index += 1
            else:
                button_type = "primary" if window_id == active_id else "secondary"

                with columns[column_index]:
                    if st.button(
                        window["title"],
                        key=f"select_window_close_{key_suffix}",
                        type=button_type,
                        use_container_width=True,
                    ):
                        st.session_state.active_document_window_id = window_id
                        st.rerun()

                column_index += 1

                with columns[column_index]:
                    st.button(
                        "X",
                        key=f"close_window_{key_suffix}",
                        help=f"Close {window['title']}",
                        type=button_type,
                        on_click=close_window,
                        args=(window_id,),
                        use_container_width=True,
                    )

                column_index += 1

            if column_index < len(columns):
                column_index += 1


def render_chunks_window(window: dict) -> None:
    source = source_for_id(str(window.get("source_id") or ""))

    if source is None:
        st.title("Chunk texts")
        st.error("The selected source could not be found.")
        return

    chunks = load_source_chunks(source["chunks_path"])
    st.title(f"{source['display_name']} chunk texts")
    st.caption(f"Chunks: `{len(chunks)}`")

    st.text_area(
        "Chunk texts",
        value=format_chunk_texts(chunks),
        height=650,
        disabled=True,
    )


def render_pdf_window(window: dict) -> None:
    source = source_for_id(str(window.get("source_id") or ""))

    if source is None:
        st.title("PDF")
        st.error("The selected source could not be found.")
        return

    pdf_path = local_pdf_path(source)
    st.title(f"{source['display_name']} PDF")

    if pdf_path is None:
        st.info("No PDF file found for this document.")
        return

    try:
        page_count = pdf_page_count(str(pdf_path))
    except Exception as exc:
        st.error("Could not open this PDF.")
        st.exception(exc)
        return

    page_key = f"pdf_page_{source['id']}"
    st.session_state[page_key] = min(
        max(int(st.session_state.get(page_key, 1)), 1),
        page_count,
    )

    page_controls_key = re.sub(r"[^a-zA-Z0-9_]+", "_", source["id"])
    with st.container(key=f"pdf_page_controls_{page_controls_key}"):
        page_controls = st.columns(
            [1.55, 1.15, 2.1, 5.2],
            gap="small",
            vertical_alignment="center",
        )
        with page_controls[0]:
            if st.button(
                "Previous",
                key=f"previous_pdf_page_{page_controls_key}",
                disabled=st.session_state[page_key] <= 1,
                use_container_width=True,
            ):
                st.session_state[page_key] -= 1
                st.rerun()

        with page_controls[1]:
            if st.button(
                "Next",
                key=f"next_pdf_page_{page_controls_key}",
                disabled=st.session_state[page_key] >= page_count,
                use_container_width=True,
            ):
                st.session_state[page_key] += 1
                st.rerun()

        with page_controls[2]:
            st.number_input(
                "Page",
                min_value=1,
                max_value=page_count,
                step=1,
                key=page_key,
                label_visibility="collapsed",
            )

    st.caption(f"Page `{st.session_state[page_key]}` of `{page_count}`")

    try:
        page_image = render_pdf_page_image(str(pdf_path), int(st.session_state[page_key]))
    except Exception as exc:
        st.error("Could not render this PDF page.")
        st.exception(exc)
        return

    st.image(page_image, width="stretch")


def render_document_panel() -> None:
    render_document_window_bar()
    window = active_document_window()

    if window["type"] == "documents":
        render_document_window()
        return

    if window["type"] == "chunks":
        render_chunks_window(window)
        return

    if window["type"] == "pdf":
        render_pdf_window(window)
        return


def render_active_panel() -> None:
    if st.session_state.active_top_panel == "documents":
        render_document_panel()
        return

    render_chat_header()
    replay_chat_history()
    handle_user_question()


def save_current_chat() -> dict | None:
    saved_chat = save_chat_session(
        list(st.session_state.messages),
        st.session_state.current_chat_id,
    )

    if saved_chat is None:
        return None

    st.session_state.current_chat_id = saved_chat["id"]
    st.session_state.current_chat_title = saved_chat["title"]
    st.session_state.messages = saved_chat["messages"]

    return saved_chat


def load_chat_session(chat_id: str) -> None:
    session = read_chat_file(chat_file_path(chat_id))

    if session is None:
        st.warning("That saved chat could not be loaded.")
        return

    st.session_state.current_chat_id = session["id"]
    st.session_state.current_chat_title = session["title"]
    st.session_state.messages = session["messages"]
    request_top_panel("chat")
    st.rerun()


def start_new_chat() -> None:
    save_current_chat()
    st.session_state.messages = []
    st.session_state.current_chat_id = None
    st.session_state.current_chat_title = "Unsaved chat"
    request_top_panel("chat")
    st.rerun()


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Status")
        st.write(f"Vector store: `{DEFAULT_VECTORSTORE_LABEL}`")
        st.slider(
            "threshold",
            min_value=MIN_MAX_DISTANCE,
            max_value=MAX_MAX_DISTANCE,
            step=0.05,
            key="max_distance",
            on_change=save_app_settings,
            help=(
                "Threshold 越高，RAG 越容易將文件判定為相關；"
                "Threshold 越低，則判定標準越嚴格。如果 RAG 經常回答"
                "與問題無關的內容，可以適當降低 Threshold；反之，如果 RAG "
                "無法回答與中醫（TCM）相關的問題，則可以適當提高 Threshold，"
                "以增加檢索到相關資料的機會。"
            ),
        )

        st.divider()
        st.header("Chats")
        st.caption(f"Current: {st.session_state.current_chat_title}")

        if st.button("Save chat", use_container_width=True):
            saved_chat = save_current_chat()
            if saved_chat is None:
                st.info("No messages to save yet.")
            else:
                st.success("Chat saved.")

        if st.button("New chat", use_container_width=True):
            start_new_chat()

        sessions = load_chat_sessions()

        if sessions:
            session_by_id = {session["id"]: session for session in sessions}
            session_ids = list(session_by_id)
            current_chat_id = st.session_state.current_chat_id
            selected_index = 0

            if current_chat_id in session_by_id:
                selected_index = session_ids.index(current_chat_id)

            selected_chat_id = st.selectbox(
                "Saved chats",
                session_ids,
                index=selected_index,
                format_func=lambda chat_id: session_label(session_by_id[chat_id]),
            )

            if st.button("Open selected chat", use_container_width=True):
                if selected_chat_id != st.session_state.current_chat_id:
                    save_current_chat()

                load_chat_session(selected_chat_id)
        else:
            st.info("No saved chats yet.")

        st.caption("Educational demo only. Not medical advice.")


def replay_chat_history() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            render_chat_message(message)


def install_ime_safe_enter_submit() -> None:
    st.html(
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
        unsafe_allow_javascript=True,
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
                max_distance = clamp_max_distance(st.session_state.max_distance)
                st.session_state.max_distance = max_distance
                save_app_settings()
                with st.spinner("Retrieving sources and generating answer..."):
                    result = ask_tcm(
                        question,
                        chat_history=chat_history,
                        max_distance=max_distance,
                    )

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
                "max_distance": result.get("max_distance", max_distance),
            }
            render_chat_message(assistant_message)
            st.session_state.messages.append(assistant_message)
            save_current_chat()


render_top_panel()
render_active_panel()
render_sidebar()
