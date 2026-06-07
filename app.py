from __future__ import annotations

import base64
import html
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
CHAT_SESSIONS_DIR = PROJECT_ROOT / "docs" / "chat_sessions"
DOC_SOURCES_DIR = PROJECT_ROOT / "docs" / "sources"
APP_SETTINGS_PATH = PROJECT_ROOT / "docs" / "app_settings.json"
DEFAULT_VECTORSTORE_LABEL = (
    "docs/sources/tcm_basic_theory/vectorstores/faiss_openai_test_embedding_3_small"
)
DEFAULT_MAX_DISTANCE = 1.3
MIN_MAX_DISTANCE = 1.0
MAX_MAX_DISTANCE = 1.5

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

load_dotenv(PROJECT_ROOT / ".env")
CHAT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
DOC_SOURCES_DIR.mkdir(parents=True, exist_ok=True)


@st.cache_resource
def load_ask_tcm():
    from tcmagent.rag import ask_tcm

    return ask_tcm


st.set_page_config(
    page_title="TCM Citation RAG",
    page_icon="",
    layout="centered",
)

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


def clamp_max_distance(value) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_DISTANCE

    return min(max(numeric_value, MIN_MAX_DISTANCE), MAX_MAX_DISTANCE)


def load_app_settings() -> dict:
    try:
        data = json.loads(APP_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"max_distance": DEFAULT_MAX_DISTANCE}

    if not isinstance(data, dict):
        return {"max_distance": DEFAULT_MAX_DISTANCE}

    return {
        "max_distance": clamp_max_distance(data.get("max_distance", DEFAULT_MAX_DISTANCE))
    }


app_settings = load_app_settings()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

if "current_chat_title" not in st.session_state:
    st.session_state.current_chat_title = "Unsaved chat"

if "max_distance" not in st.session_state:
    st.session_state.max_distance = app_settings["max_distance"]


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


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def save_app_settings() -> None:
    st.session_state.max_distance = clamp_max_distance(st.session_state.max_distance)
    payload = {
        "max_distance": st.session_state.max_distance,
        "updated_at": now_iso(),
    }
    APP_SETTINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    return data


def load_document_sources() -> list[dict]:
    sources = []

    for manifest_path in sorted(DOC_SOURCES_DIR.glob("*/source.json")):
        metadata = read_json(manifest_path)
        if metadata is None:
            continue

        source_dir = manifest_path.parent
        source_id = str(metadata.get("id") or source_dir.name)
        chunks_path = source_dir / str(metadata.get("chunks_path") or "chunks.jsonl")
        original_filename = str(metadata.get("original_filename") or "")
        document_files = []

        if original_filename and (source_dir / original_filename).exists():
            document_files.append(original_filename)

        skipped_names = {"source.json", chunks_path.name, *document_files}
        for path in sorted(source_dir.iterdir()):
            if path.is_file() and path.name not in skipped_names:
                document_files.append(path.name)

        sources.append({
            "id": source_id,
            "display_name": str(metadata.get("display_name") or source_id),
            "source_dir": source_dir,
            "chunks_path": chunks_path,
            "document_files": document_files,
            "metadata": metadata,
        })

    return sources


def load_source_chunks(chunks_path: Path) -> list[dict]:
    chunks = []

    try:
        with chunks_path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue

                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if isinstance(chunk, dict):
                    chunks.append(chunk)
    except OSError:
        return []

    return chunks


def source_label(source: dict) -> str:
    return f"{source['display_name']} ({source['id']})"


def chunk_label(chunk: dict, index: int) -> str:
    chunk_id = str(chunk.get("chunk_id") or f"chunk-{index + 1}")
    pages = chunk.get("pdf_pages")

    if isinstance(pages, list) and pages:
        page_label = ", ".join(str(page) for page in pages[:3])
        if len(pages) > 3:
            page_label = f"{page_label}, ..."
    else:
        page_label = str(chunk.get("pdf_page") or "unknown")

    return f"{index + 1}. {chunk_id} p.{page_label}"


def source_pdf_url(source: dict, chunks: list[dict]) -> str:
    metadata = source["metadata"]

    for key in ("viewer_url", "pdf_url", "source_url"):
        url = str(metadata.get(key) or "").strip()
        if url:
            return url

    for chunk in chunks:
        url = str(chunk.get("citation_link") or "").strip()
        if url:
            return url.split("#page=", maxsplit=1)[0]

    return ""


def chunk_pdf_url(source: dict, chunks: list[dict], chunk: dict) -> str:
    url = str(chunk.get("citation_link") or "").strip()
    if url:
        return url

    return source_pdf_url(source, chunks)


def render_pdf_viewer_link(label: str, url: str, new_tab: bool = True) -> None:
    if not url:
        st.caption("No PDF viewer link is available for this document.")
        return

    escaped_label = html.escape(label)
    escaped_url = html.escape(url, quote=True)
    target = "_blank" if new_tab else "_self"
    st.markdown(
        (
            f'<a href="{escaped_url}" target="{target}" rel="noopener noreferrer">'
            f"{escaped_label}</a>"
        ),
        unsafe_allow_html=True,
    )


def pdf_viewer_page_url(source_id: str, page: int | None = None) -> str:
    params = {
        "view": "pdf",
        "source": source_id,
    }

    if page is not None:
        params["page"] = str(page)

    return f"?{urlencode(params)}"


def local_pdf_path(source: dict) -> Path | None:
    source_dir = source["source_dir"]
    metadata = source["metadata"]
    filenames = []
    original_filename = str(metadata.get("original_filename") or "")

    if original_filename:
        filenames.append(original_filename)

    filenames.extend(source["document_files"])

    for filename in filenames:
        path = source_dir / filename
        if path.exists() and path.suffix.lower() == ".pdf":
            return path

    for path in sorted(source_dir.glob("*.pdf")):
        return path

    return None


def page_number_from_chunk(chunk: dict) -> int | None:
    pdf_page = chunk.get("pdf_page")

    if isinstance(pdf_page, int):
        return pdf_page

    pages = chunk.get("pdf_pages")
    if isinstance(pages, list) and pages:
        try:
            return int(pages[0])
        except (TypeError, ValueError):
            return None

    return None


def render_document_viewer() -> None:
    st.divider()
    st.header("Documents")
    sources = load_document_sources()

    if not sources:
        st.info("No uploaded documents found.")
        return

    source_by_id = {source["id"]: source for source in sources}
    source_ids = list(source_by_id)
    current_source_id = st.session_state.get("selected_source_id")
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
    chunks = load_source_chunks(source["chunks_path"])

    st.caption(f"Source id: `{source['id']}`")
    st.caption(f"Chunks: `{len(chunks)}`")

    for filename in source["document_files"]:
        st.write(f"Document: `{filename}`")

    render_pdf_viewer_link(
        "Open PDF viewer in a new window",
        pdf_viewer_page_url(source["id"]),
    )

    with st.expander("Source metadata"):
        st.json(source["metadata"])

    if not chunks:
        st.info("No chunks found for this document.")
        return

    selected_chunk_index = st.selectbox(
        "Chunks",
        list(range(len(chunks))),
        format_func=lambda index: chunk_label(chunks[index], index),
        key=f"selected_chunk_index_{selected_source_id}",
    )
    chunk = chunks[selected_chunk_index]
    citation_markdown = chunk.get("citation_markdown")

    if citation_markdown:
        st.markdown(citation_markdown)

    render_pdf_viewer_link(
        "Open selected chunk in PDF",
        pdf_viewer_page_url(source["id"], page_number_from_chunk(chunk)),
    )

    st.text_area(
        "Chunk text",
        value=str(chunk.get("text", "")),
        height=220,
        disabled=True,
    )

    with st.expander("Chunk metadata"):
        st.json({key: value for key, value in chunk.items() if key != "text"})


def query_param_value(name: str) -> str:
    value = st.query_params.get(name)

    if isinstance(value, list):
        return str(value[0]) if value else ""

    return str(value or "")


def render_pdf_page() -> bool:
    if query_param_value("view") != "pdf":
        return False

    sources = load_document_sources()
    source_by_id = {source["id"]: source for source in sources}
    source_id = query_param_value("source")
    source = source_by_id.get(source_id)

    if source is None:
        st.title("PDF Viewer")
        st.error("The selected document source could not be found.")
        render_pdf_viewer_link("Back to chat", ".", new_tab=False)
        return True

    chunks = load_source_chunks(source["chunks_path"])
    pdf_path = local_pdf_path(source)
    page_text = query_param_value("page")
    page_fragment = ""

    if page_text:
        try:
            page_number = int(page_text)
        except ValueError:
            page_number = None

        if page_number is not None and page_number > 0:
            page_fragment = f"#page={page_number}"

    st.title(source["display_name"])
    st.caption(f"Source id: `{source['id']}`")
    render_pdf_viewer_link("Back to chat", ".", new_tab=False)

    if pdf_path is not None:
        pdf_bytes = pdf_path.read_bytes()
        encoded_pdf = base64.b64encode(pdf_bytes).decode("ascii")
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=pdf_path.name,
            mime="application/pdf",
        )
        components.html(
            (
                '<iframe title="PDF viewer" '
                f'src="data:application/pdf;base64,{encoded_pdf}{page_fragment}" '
                'style="width:100%; height:92vh; border:0;"></iframe>'
            ),
            height=900,
        )
        return True

    pdf_url = source_pdf_url(source, chunks)
    if pdf_url:
        if page_fragment and "#page=" not in pdf_url:
            pdf_url = f"{pdf_url}{page_fragment}"

        render_pdf_viewer_link("Open PDF in a new window", pdf_url)
        components.html(
            (
                '<iframe title="PDF viewer" '
                f'src="{html.escape(pdf_url, quote=True)}" '
                'style="width:100%; height:92vh; border:0;"></iframe>'
            ),
            height=900,
        )
    else:
        st.info("No PDF file or viewer URL is available for this source.")

    return True


def render_chat_header() -> None:
    st.title("TCM Citation RAG")
    st.caption("Ask a Traditional Chinese Medicine question and retrieve cited context.")


def chat_file_path(chat_id: str) -> Path:
    return CHAT_SESSIONS_DIR / f"{chat_id}.json"


def clean_message(message: dict) -> dict:
    role = message.get("role")
    if role not in {"user", "assistant"}:
        role = "assistant"

    cleaned = {
        "role": role,
        "content": str(message.get("content", "")),
    }

    if role == "assistant":
        cleaned["sources"] = message.get("sources", [])
        cleaned["scores"] = message.get("scores", [])

        search_question = message.get("search_question")
        if search_question:
            cleaned["search_question"] = str(search_question)

        max_distance = message.get("max_distance")
        if max_distance is not None:
            cleaned["max_distance"] = clamp_max_distance(max_distance)

    return cleaned


def clean_messages(messages: list[dict]) -> list[dict]:
    cleaned_messages = []

    for message in messages:
        if isinstance(message, dict):
            cleaned_messages.append(clean_message(message))

    return cleaned_messages


def chat_title_from_messages(messages: list[dict]) -> str:
    for message in messages:
        if message.get("role") != "user":
            continue

        title = " ".join(str(message.get("content", "")).split())
        if not title:
            continue

        if len(title) > 42:
            return f"{title[:39]}..."

        return title

    return "Untitled chat"


def read_chat_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    messages = data.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    clean_stored_messages = clean_messages(messages)
    title = str(data.get("title") or chat_title_from_messages(clean_stored_messages))

    return {
        "id": str(data.get("id") or path.stem),
        "title": title,
        "created_at": str(data.get("created_at") or now_iso()),
        "updated_at": str(data.get("updated_at") or data.get("created_at") or now_iso()),
        "messages": clean_stored_messages,
    }


def save_current_chat() -> dict | None:
    messages = clean_messages(list(st.session_state.messages))

    if not messages:
        return None

    chat_id = st.session_state.current_chat_id or uuid.uuid4().hex
    path = chat_file_path(chat_id)
    existing_chat = read_chat_file(path) if path.exists() else None
    created_at = existing_chat["created_at"] if existing_chat else now_iso()
    updated_at = now_iso()
    title = chat_title_from_messages(messages)
    payload = {
        "id": chat_id,
        "title": title,
        "created_at": created_at,
        "updated_at": updated_at,
        "messages": messages,
    }

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    st.session_state.current_chat_id = chat_id
    st.session_state.current_chat_title = title
    st.session_state.messages = messages

    return payload


def load_chat_sessions() -> list[dict]:
    sessions = []

    for path in CHAT_SESSIONS_DIR.glob("*.json"):
        session = read_chat_file(path)
        if session is not None:
            sessions.append(session)

    return sorted(sessions, key=lambda session: session["updated_at"], reverse=True)


def load_chat_session(chat_id: str) -> None:
    session = read_chat_file(chat_file_path(chat_id))

    if session is None:
        st.warning("That saved chat could not be loaded.")
        return

    st.session_state.current_chat_id = session["id"]
    st.session_state.current_chat_title = session["title"]
    st.session_state.messages = session["messages"]
    st.rerun()


def start_new_chat() -> None:
    save_current_chat()
    st.session_state.messages = []
    st.session_state.current_chat_id = None
    st.session_state.current_chat_title = "Unsaved chat"
    st.rerun()


def session_label(session: dict) -> str:
    updated_at = session.get("updated_at", "").replace("T", " ")

    if updated_at:
        return f"{session['title']} - {updated_at}"

    return session["title"]


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
                "The higher it is the more likely to cite and the lower it is "
                "the more unlikely to cite."
            ),
        )
        st.caption(f"Current threshold: `{float(st.session_state.max_distance):.2f}`")
        st.caption(
            "The higher it is the more likely to cite and the lower it is the more "
            "unlikely to cite."
        )

        if os.getenv("OPENAI_API_KEY"):
            st.success("OPENAI_API_KEY is set.")
        else:
            st.warning("OPENAI_API_KEY is not set.")

        render_document_viewer()

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


if render_pdf_page():
    st.stop()

render_chat_header()
replay_chat_history()
handle_user_question()
render_sidebar()
