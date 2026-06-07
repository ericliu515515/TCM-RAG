# PDF Source Layout

Each uploaded or built-in PDF source should get one folder:

```text
docs/sources/<source_id>/
  source.json
  <original PDF file>
  chunks.jsonl
  vectorstores/
    <vectorstore_id>/
      index.faiss
      index.pkl
```

`source.json` stores the source id, display name, original file name, chunk path, and vectorstore paths. The app can later list these folders to let users choose which uploaded PDFs to include in RAG.
