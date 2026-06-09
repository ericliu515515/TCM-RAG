from functools import lru_cache
from pathlib import Path 

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI, OpenAIEmbeddings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = PROJECT_ROOT / "docs" / "sources" / "tcm_basic_theory"
VECTORSTORE_DIR = SOURCE_DIR / "vectorstores" / "faiss_openai_test_embedding_3_small"


@lru_cache(maxsize=1)
def get_embedding_model():
    return OpenAIEmbeddings(
        model = "text-embedding-3-small",
    )


@lru_cache(maxsize=1)
def get_vectorstore():
    return FAISS.load_local(
        str(VECTORSTORE_DIR),
        get_embedding_model(),
        allow_dangerous_deserialization = True
    )


MAX_DISTANCE = 1.3 


@lru_cache(maxsize=1)
def get_chain():
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


@lru_cache(maxsize=1)
def get_question_rewriter_chain():
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


def format_context (docs):
    blocks = []

    for i, doc in enumerate(docs, start = 1):
        citation = doc.metadata["citation_markdown"]
        text = doc.page_content 

        blocks.append(
            f"[Source {i}] {citation}\n {text}"
        )
    
    return "\n\n".join(blocks)


def format_chat_history(chat_history: list[dict] | None, max_messages: int = 6) -> str:
    if not chat_history:
        return "No previous messages."

    lines = []

    recent_messages = chat_history[-max_messages:]

    for message in recent_messages:
        role = message.get("role")
        content = str(message.get("content", "")).strip()

        if not content:
            continue

        if role == "user":
            speaker = "User"
        elif role == "assistant":
            speaker = "Assistant"
        else:
            speaker = "Message"

        lines.append(f"{speaker}: {content}")

    if not lines:
        return "No previous messages."

    return "\n".join(lines)


def has_chat_history(chat_history: list[dict] | None) -> bool:
    if not chat_history:
        return False

    return any(str(message.get("content", "")).strip() for message in chat_history)


def rewrite_search_question(question: str, chat_history: list[dict] | None) -> str:
    if not has_chat_history(chat_history):
        return question

    rewritten_question = get_question_rewriter_chain().invoke({
        "chat_history": format_chat_history(chat_history),
        "question": question,
    }).strip()

    if not rewritten_question:
        return question

    return rewritten_question


def ask_tcm(
    question: str,
    chat_history: list[dict] | None = None,
    max_distance: float = MAX_DISTANCE,
) -> dict:
    vectorstore = get_vectorstore()
    chain = get_chain()
    threshold = float(max_distance)

    chat_history_text = format_chat_history(chat_history)

    search_question = rewrite_search_question(question, chat_history)

    results = vectorstore.similarity_search_with_score(search_question, k=5)
    scores = [float(score) for _, score in results]

    kept_results = [(doc, score) for doc, score in results if score < threshold]

    if not kept_results:
        return {
            "answer": "This question does not look related to the TCM source material.",
            "sources": [],
            "scores": scores,
            "search_question": search_question,
            "max_distance": threshold,
        }

    context = format_context([doc for doc, _ in kept_results])

    answer = chain.invoke({
        "chat_history": chat_history_text,
        "question": question,
        "search_question": search_question,
        "context": context,
    })

    return {
        "answer": answer,
        "sources": [doc.metadata for doc, _ in kept_results],
        "scores": scores,
        "search_question": search_question,
        "max_distance": threshold,
    }
