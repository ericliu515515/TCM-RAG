# tcmrag

`tcmrag` is a Streamlit citation RAG app for Traditional Chinese Medicine
documents. It lets users ask TCM questions, retrieves relevant context from
embedded PDF chunks, and returns answers with clickable citations that open the
source PDF page.

This is an educational demo only. It is not medical advice.

## Features

- Chat UI for TCM questions and cited answers.
- PDF citation links routed back into the app's PDF viewer.
- Saved local chat sessions.
- Uploaded PDF workflow:
  - extract PDF text,
  - generate chunks,
  - embed chunks with OpenAI embeddings,
  - rebuild the combined FAISS vectorstore.
- Retrieval quality checks with good/bad question separation scoring.
- Adjustable retrieval distance threshold. The default threshold is `1.3`.

## Local Setup

Create and activate a virtual environment from the repo root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Create a local `.env` file:

```bash
OPENAI_API_KEY=sk-your-key-here
```

Run the app:

```bash
.venv/bin/streamlit run app.py
```

Then open the Streamlit URL shown in the terminal, usually
`http://localhost:8501`.

## Secrets

Do not commit `.env`. It is ignored by Git and should stay local.

For hosted deployments, set `OPENAI_API_KEY` in the hosting platform's secrets
manager instead of storing it in the repository. If an API key is ever committed
or shown publicly, rotate it immediately.

## Streamlit Community Cloud

Use these settings when deploying:

- Repository: your GitHub repo.
- Main file path: `app.py`.
- Python dependencies: `requirements.txt`.
- Secret:

```toml
OPENAI_API_KEY = "sk-your-key-here"
```

Streamlit Cloud runtime storage should be treated as app/runtime state, not as a
durable database. If you want the deployed app to start with a prepared corpus,
commit the needed source documents, chunks, and vectorstores intentionally. If
you do not commit them, users can upload and process PDFs through the app.

## Document Processing

The document page has one processing action for uploaded PDFs. It runs these
steps in order:

1. Extract PDF text into page records.
2. Generate chunks with the AI chunker.
3. Embed the selected chunk set.
4. Rebuild the combined vectorstore.

Chunk runs are evaluated by retrieval separation score. Deterministic chunk
validation is reported as a warning signal, but it does not by itself decide
whether a chunk run succeeds.

## Project Layout

```text
app.py                         Streamlit entrypoint
src/tcmrag/rag.py              RAG chain, vectorstore loading, answer prompt
src/tcmrag/source_embeddings.py Embedding, FAISS, and evaluation helpers
src/tcmrag/ai_chunking.py      AI chunker generation and chunk-run selection
src/tcmrag/chunk_quality.py    Deterministic chunk validation helpers
src/tcmrag/web/                Streamlit support modules
docs/sources/                  Source PDFs, chunks, manifests, chunk runs
docs/vectorstores/             Combined FAISS vectorstore output
docs/chat_sessions/            Saved local chat sessions
```

## Development Checks

Run a quick syntax check:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q app.py src/tcmrag
```

If the app is already running, check its health endpoint:

```bash
curl -fsS http://localhost:8501/_stcore/health
```

Expected output:

```text
ok
```
