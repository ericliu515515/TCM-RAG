
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

chunker_path = Path('/Users/ericliuuuuuuuu/Personal/tcmrag/docs/sources/uploaded_pdf_7895ee25/chunk_runs/run_20260610T121529_2_5b7e1ab6/chunker.py')
pages_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])

spec = importlib.util.spec_from_file_location("generated_chunker", chunker_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

pages = json.loads(pages_path.read_text(encoding="utf-8"))["pages"]
chunks = module.chunk_pages(pages)

if isinstance(chunks, dict) and isinstance(chunks.get("chunks"), list):
    chunks = chunks["chunks"]

if not isinstance(chunks, list):
    raise TypeError("chunk_pages must return a list, or a dict with a list under the 'chunks' key.")

with output_path.open("w", encoding="utf-8") as file:
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise TypeError("Every chunk must be a dict.")
        file.write(json.dumps(chunk, ensure_ascii=False) + "\n")
