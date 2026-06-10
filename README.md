# TCM (中醫) Citation RAG

> **Important:** This project is an educational demo and is not for medical advice.

![TCM Citation RAG demo](asset/gif.gif)

One of the main challenges of Traditional Chinese Medicine (TCM) chatbots is hallucination. To address this, our application uses Retrieval-Augmented Generation (RAG), ensuring that responses are grounded in reliable reference materials.

Since TCM answers can vary across different schools of thought, we also provide a "You Decide the Truth" feature. Users can upload trusted text-based PDF documents to build their own RAG knowledge base. An AI tool then generates a Python script to convert these PDFs into JSONL format, allowing the chatbot to answer questions based on the user's chosen sources.

## Model Configuration

- **Embedding model:** `text-embedding-3-small`
  - Used to embed document chunks and build FAISS vectorstores.
- **Chunker script model:** `gpt-4o-mini` by default
  - Generates the Python `chunk_pages(pages)` script that converts extracted PDF
    pages into JSONL chunks.
- **Response generation model:** `gpt-4o-mini`
  - Generates the final chatbot answer from retrieved source context and
    citation links.

## Estimated API Cost

Using the default models and an approximate exchange rate of USD 1 ~= NTD 32:

- **Uploading and processing a 100-page text-based PDF:** usually less than
  **NTD 5**.
  - This includes chunker script generation, chunk quality feedback, chunk
    embeddings, retrieval evaluation, and rebuilding the combined vectorstore.
- **Generating one chatbot response:** usually less than **NTD 1**.
  - This includes retrieval, optional question rewriting for follow-up
    questions, and one `gpt-4o-mini` response over retrieved source context.

Actual cost depends on extracted text length, number of chunker attempts,
answer length, exchange rate, and OpenAI pricing at runtime.

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


## Quick Setup 

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

Then open the local Streamlit URL shown in the terminal.

## Limitations

- The app depends on the quality of extracted PDF text. Unusual PDF
  layout can reduce retrieval quality.
- The app can only read text-based PDF.
