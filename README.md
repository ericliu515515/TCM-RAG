# TCM Citation RAG

A Streamlit retrieval-augmented generation app for answering Traditional Chinese
Medicine questions with grounded PDF citations.

The app lets a user upload TCM reference PDFs, process them into searchable
chunks, build a FAISS vectorstore, and ask questions through a chat interface.
Answers include clickable citations that route back to the relevant source PDF
page inside the app.

This project is an educational demo and is not medical advice.

## Why I Built This

Traditional Chinese Medicine content is often locked inside long PDFs, scanned
books, or mixed Chinese/English references. I built this project to explore how
to make that material queryable while keeping answers auditable through source
citations instead of returning unsupported model output.

The main engineering focus is not just "chat with a PDF." The app includes a
full ingestion workflow, chunk quality checks, embedding rebuilds, citation
routing, session persistence, and deployment-safe API key handling.

## Key Features

- Citation-first RAG chat interface for TCM questions.
- Clickable source links that open the cited PDF page in the app.
- PDF upload and processing pipeline:
  1. extract page text,
  2. generate chunks,
  3. embed chunks,
  4. rebuild the combined vectorstore.
- FAISS vector search with OpenAI `text-embedding-3-small` embeddings.
- Chunk-run evaluation using good/bad query separation scoring.
- Deterministic chunk validation warnings for debugging chunk quality.
- Saved chat sessions stored as local JSON files.
- Streamlit UI with separate Chat and Document views.
- Local `.env` support and hosted secret configuration for deployment.

## Architecture

```text
PDF sources
   |
   v
PDF text extraction
   |
   v
AI chunk generation + deterministic validation warnings
   |
   v
OpenAI embeddings
   |
   v
FAISS vectorstores
   |
   v
Retriever + prompt assembly
   |
   v
Chat answer with markdown citations
   |
   v
In-app PDF citation viewer
```

## Technical Highlights

- **RAG pipeline:** Uses LangChain, FAISS, and OpenAI models to retrieve source
  chunks and generate grounded answers.
- **Citation routing:** Rewrites citation links into app query parameters so a
  clicked answer citation opens the correct PDF and page.
- **Chunk selection:** Runs multiple chunker attempts and accepts the first run
  that passes retrieval separation. If none pass, it selects the evaluated run
  with the strongest separation score.
- **Quality feedback:** Deterministic chunk validation is treated as a warning
  system, not a hard failure gate, so useful chunks are not discarded only
  because of formatting issues.
- **Background workflow:** Long document-processing steps run as tracked jobs
  with progress state shown in the UI.
- **Reviewable structure:** Streamlit UI logic lives in `app.py`, while storage,
  citation rewriting, document helpers, styles, RAG, embeddings, and chunking
  are split into focused modules under `src/tcmrag`.

## Tech Stack

- Python
- Streamlit
- LangChain
- OpenAI API
- FAISS
- PyMuPDF / pypdf
- pandas, numpy, matplotlib for notebook evaluation work

## Repository Layout

```text
app.py                          Streamlit entrypoint
src/tcmrag/rag.py               RAG chain and vectorstore loading
src/tcmrag/source_embeddings.py  Embedding, FAISS, and evaluation helpers
src/tcmrag/ai_chunking.py        AI chunk generation and chunk-run selection
src/tcmrag/chunk_quality.py      Deterministic chunk validation
src/tcmrag/web/                 Streamlit support modules
docs/sources/                   PDF sources, manifests, chunks, chunk runs
docs/vectorstores/              Combined FAISS vectorstore output
docs/chat_sessions/             Saved local chat sessions
```

## Running Locally

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Create a local `.env` file:

```bash
OPENAI_API_KEY=sk-your-key-here
```

Start the app:

```bash
.venv/bin/streamlit run app.py
```

Then open the local Streamlit URL, usually `http://localhost:8501`.

## Deployment Notes

For Streamlit Community Cloud:

- Main file path: `app.py`
- Dependencies: `requirements.txt`
- Secret:

```toml
OPENAI_API_KEY = "sk-your-key-here"
```

The API key should be configured in the hosting platform's secret manager, not
committed to Git. Local `.env` files and `.streamlit/secrets.toml` are ignored.

## Limitations

- The app depends on the quality of extracted PDF text. Poor OCR or unusual PDF
  layout can reduce retrieval quality.
- Runtime uploads and generated vectorstores are local app state unless they are
  intentionally committed or backed by persistent storage.
- The medical domain requires expert review. This app is designed for retrieval
  and citation exploration, not diagnosis or treatment recommendations.

## Development Check

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q app.py src/tcmrag
```
