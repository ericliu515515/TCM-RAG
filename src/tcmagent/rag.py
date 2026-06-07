# src/tcmagent/rag.py
from functools import lru_cache
from pathlib import Path 

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI, OpenAIEmbeddings


# Location of the saved FAISS index used for retrieval.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = PROJECT_ROOT / "docs" / "sources" / "tcm_basic_theory"
VECTORSTORE_DIR = SOURCE_DIR / "vectorstores" / "faiss_openai_test_embedding_3_small"


@lru_cache(maxsize=1)
def get_embedding_model():
    # Create the embedding model used for vector search.
    return OpenAIEmbeddings(
        model = "text-embedding-3-small",
    )


@lru_cache(maxsize=1)
def get_vectorstore():
    # Loading FAISS from disk is expensive, so do it only on first use.
    return FAISS.load_local(
        str(VECTORSTORE_DIR),
        get_embedding_model(),
        allow_dangerous_deserialization = True
    )


# Retrieval threshold from the notebook score test.
# FAISS scores are distances here, so lower means more related.
MAX_DISTANCE = 1.3 


# -----------------------------------------------------------------------------
# Block 1: Final Answer Chain
# -----------------------------------------------------------------------------
# This chain receives:
# - the user's original question,
# - recent chat history,
# - the standalone retrieval question,
# - retrieved source chunks from FAISS.
#
# Its job is to write the final answer with citations. It should not decide what
# to retrieve; retrieval already happened before this chain runs.
@lru_cache(maxsize=1)
def get_chain():
    # Build the prompt/model/parser chain once, then reuse it for later calls.
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "你是一名中醫諮詢師\n"
            """你是一名中醫諮詢師。

請根據 Context 回答使用者問題，不要使用 Context 以外的資料。

回答風格請模仿以下範例：
- 先用一小段話解釋名詞或概念。
- 接著用幾個重點段落說明功能、意義或相關病理。
- 每個重點段落後面都要附上引用。
- 最後用一小段話做總結。

非常重要的引用規則：
1. Context 中每個 Source 都會提供一個 Markdown citation hyperlink，例如：
   [TCM Basic Theory p.140](https://example.com)
2. 你引用資料時，必須直接複製 Context 中提供的完整 Markdown hyperlink。
3. 不可以只寫純文字 citation，例如「TCM Basic Theory p.140」。
4. 如果你想寫「TCM Basic Theory p.140」，必須改成 Context 中對應的 Markdown hyperlink 格式：
   [TCM Basic Theory p.140](實際連結)
5. 不可以寫 [Source 1]、Source 1、頁碼，或沒有 hyperlink 的 citation。
6. 若同一段使用多個來源，可以放多個 Markdown hyperlinks。
7. 回答中至少要出現一個可點擊的 Markdown citation hyperlink。

回答範例，只模仿格式，不要複製內容或頁碼：

肝血是指肝臟所貯藏和調節的血液。根據中醫理論，肝不僅負責儲存血液，還會影響血量調節與相關生理功能。

貯藏血液：肝內所藏之血可以滋養肝臟本身，也支持筋、爪、眼睛等部位的正常功能。若肝血不足，可能出現肢體麻木、視物不清等表現。[TCM Basic Theory p.xxx](請使用 Context 中的實際 citation hyperlink)

經血生成之源：肝血充足與女性月經的正常來潮有關，若肝血不足，可能影響月經量與週期。[TCM Basic Theory p.xxx](請使用 Context 中的實際 citation hyperlink)

防止出血：肝的藏血與調節血量功能，也和防止血液異常外溢有關。[TCM Basic Theory p.xxx](請使用 Context 中的實際 citation hyperlink)

總結來說，肝血不只是「儲存在肝中的血」，也代表肝對血液濡養、調節與維持身體功能的作用。

現在請回答：
"""
        ),
        (
            "user",
            "Chat history:\n{chat_history}\n\n"
            "Standalone retrieval question:\n{search_question}\n\n"
            "問題：\n{question}\n\n"
            "Context:\n{context}"
        )
    ])

    llm = ChatOpenAI(
        model = "gpt-4o-mini",
        temperature = 1.2,
    )

    return prompt | llm | StrOutputParser()


# -----------------------------------------------------------------------------
# Block 2: Question Rewriter Chain
# -----------------------------------------------------------------------------
# This is the extra LangChain chain that makes the app conversational.
#
# Problem:
#   A follow-up like "那腎呢？" is bad for vector search because it is too short.
#
# Solution:
#   Use chat history to rewrite it into a standalone retrieval question like:
#   "腎在中醫理論中的主要生理功能是什麼？"
#
# Important:
#   This chain must not answer the user. It only rewrites the search query.
@lru_cache(maxsize=1)
def get_question_rewriter_chain():
    # This chain does not answer the user. It only rewrites short follow-up
    # questions into standalone questions that work better for vector search.
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "你負責把使用者的最新問題改寫成可獨立用於向量搜尋的中文問題。\n"
            "不要回答問題，只輸出改寫後的問題。\n"
            "如果最新問題本身已經清楚完整，就原樣輸出。\n"
            "如果最新問題依賴前文，例如「那腎呢？」或「再詳細一點」，"
            "請根據 Chat history 補足主詞與上下文。\n"
            "保留中醫專有名詞，不要加入 Chat history 中沒有的病症或治療建議。"
        ),
        (
            "user",
            "Chat history:\n{chat_history}\n\nLatest question:\n{question}"
        )
    ])

    llm = ChatOpenAI(
        model = "gpt-4o-mini",
        temperature = 0,
    )

    return prompt | llm | StrOutputParser()


# -----------------------------------------------------------------------------
# Block 3: Retrieved Context Formatter
# -----------------------------------------------------------------------------
# FAISS returns LangChain Document objects. Each Document has:
# - page_content: the text chunk that was embedded,
# - metadata: source fields such as citation_markdown and pdf_page.
#
# The answer chain sees one big Context string, so this function turns the kept
# Documents into readable source blocks.
def format_context (docs):
    blocks = []

    for i, doc in enumerate(docs, start = 1):
        # citation_markdown is already in clickable Markdown format, for example:
        # [TCM Basic Theory p.132](https://...)
        citation = doc.metadata["citation_markdown"]
        text = doc.page_content 

        blocks.append(
            f"[Source {i}] {citation}\n {text}"
        )
    
    return "\n\n".join(blocks)


# -----------------------------------------------------------------------------
# Block 4: Chat History Formatter
# -----------------------------------------------------------------------------
# app.py stores messages as dictionaries like:
#   {"role": "user", "content": "..."}
#   {"role": "assistant", "content": "..."}
#
# LangChain prompts need plain text, so this function converts the recent
# messages into a compact transcript.
def format_chat_history(chat_history: list[dict] | None, max_messages: int = 6) -> str:
    # If this is the first user message, there is no previous conversation.
    if not chat_history:
        return "No previous messages."

    lines = []

    # Keep only the last few messages so the rewriter prompt stays short.
    # Older messages are usually less relevant to the newest follow-up.
    recent_messages = chat_history[-max_messages:]

    for message in recent_messages:
        role = message.get("role")
        content = str(message.get("content", "")).strip()

        # Skip empty messages so they do not confuse the rewriter.
        if not content:
            continue

        # Convert Streamlit-style roles into readable labels for the LLM.
        if role == "user":
            speaker = "User"
        elif role == "assistant":
            speaker = "Assistant"
        else:
            speaker = "Message"

        lines.append(f"{speaker}: {content}")

    # If every message was empty, treat it the same as no history.
    if not lines:
        return "No previous messages."

    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Block 5: History Presence Check
# -----------------------------------------------------------------------------
# We only call the question rewriter when there is real previous conversation.
# This saves one OpenAI call on the first turn and avoids unnecessary rewriting.
def has_chat_history(chat_history: list[dict] | None) -> bool:
    if not chat_history:
        return False

    return any(str(message.get("content", "")).strip() for message in chat_history)


# -----------------------------------------------------------------------------
# Block 6: Standalone Search Question Builder
# -----------------------------------------------------------------------------
# This function decides what text should go into FAISS retrieval.
#
# First turn:
#   Use the user's question directly.
#
# Follow-up turn:
#   Ask the rewriter chain to make the question standalone.
def rewrite_search_question(question: str, chat_history: list[dict] | None) -> str:
    # No history means the latest question is already all we have.
    if not has_chat_history(chat_history):
        return question

    # Use the rewriter chain to produce a retrieval-friendly query.
    rewritten_question = get_question_rewriter_chain().invoke({
        "chat_history": format_chat_history(chat_history),
        "question": question,
    }).strip()

    # If the model somehow returns an empty string, fall back to the original
    # question instead of breaking retrieval.
    if not rewritten_question:
        return question

    return rewritten_question


# -----------------------------------------------------------------------------
# Block 7: Main RAG Function For The App/API Layer
# -----------------------------------------------------------------------------
# ask_tcm() is the main public function used by app.py and test_app.py.
#
# Flow:
# 1. Receive the latest user question and optional previous chat history.
# 2. Rewrite the latest question into a standalone retrieval question if needed.
# 3. Retrieve matching chunks from FAISS.
# 4. Drop weak matches using the selected max_distance threshold.
# 5. Send original question, rewritten question, chat history, and retrieved
#    context into the final answer chain.
# 6. Return answer text plus debugging metadata for the UI.
def ask_tcm(
    question: str,
    chat_history: list[dict] | None = None,
    max_distance: float = MAX_DISTANCE,
) -> dict:
    # Load cached shared resources. These are expensive to create repeatedly.
    vectorstore = get_vectorstore()
    chain = get_chain()
    threshold = float(max_distance)

    # Convert previous messages to text for the final answer prompt.
    chat_history_text = format_chat_history(chat_history)

    # This is the question used for FAISS search. It may be different from the
    # user's original message when the user asks a follow-up question.
    search_question = rewrite_search_question(question, chat_history)

    # Retrieve the top candidate chunks with the standalone search question.
    results = vectorstore.similarity_search_with_score(search_question, k=5)
    scores = [float(score) for _, score in results]

    # Keep only chunks that are close enough to the question.
    kept_results = [(doc, score) for doc, score in results if score < threshold]

    # If nothing passes the threshold, avoid answering from weak context.
    if not kept_results:
        return {
            "answer": "This question does not look related to the TCM source material.",
            "sources": [],
            "scores": scores,
            "search_question": search_question,
            "max_distance": threshold,
        }

    # Format retrieved chunks as context and generate the final answer.
    context = format_context([doc for doc, _ in kept_results])

    # The final answer chain sees both:
    # - question: what the user actually typed,
    # - search_question: what we used for retrieval.
    #
    # This lets the answer sound natural while retrieval stays accurate.
    answer = chain.invoke({
        "chat_history": chat_history_text,
        "question": question,
        "search_question": search_question,
        "context": context,
    })

    # Return the answer, citation metadata, and raw scores for debugging.
    return {
        "answer": answer,
        "sources": [doc.metadata for doc, _ in kept_results],
        "scores": scores,
        "search_question": search_question,
        "max_distance": threshold,
    }
