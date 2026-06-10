# TCM (中醫) Citation RAG

> **Important:** This project is an educational demo and is not for medical advice.

One of the main challenges of Traditional Chinese Medicine (TCM) chatbots is hallucination. To address this, our application uses Retrieval-Augmented Generation (RAG), ensuring that responses are grounded in reliable reference materials.

Since TCM answers can vary across different schools of thought, we also provide a "You Decide the Truth" feature. Users can upload trusted text-based PDF documents to build their own RAG knowledge base. An AI tool then generates a Python script to convert these PDFs into JSONL format, allowing the chatbot to answer questions based on the user's chosen sources.

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

Then open the local Streamlit URL, usually `http://localhost:8501`.

## Limitations

- The app depends on the quality of extracted PDF text. Unusual PDF
  layout can reduce retrieval quality.


