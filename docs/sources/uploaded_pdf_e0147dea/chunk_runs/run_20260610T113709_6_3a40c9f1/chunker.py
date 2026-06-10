import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
    repeated_noise_candidates = {
        "中醫傷科實證臨床治療指引",
        "參考文獻",
        "GRADE",
        "臨床建議內容",
        "建議等級",
        "證據等級",
        "第二篇 指引發展方法學",
        "姓名",
        "職稱",
        "單位",
        "強建議",
        "篇",
        "第",
        "1B",
        "B 級",
        "[2]",
        "主治醫師",
        "[1-5]",
        "醫師",
        "1C"
    }

    # Step 1: Normalize and clean text
    cleaned_pages = []
    for page in pages:
        text = re.sub(r'\s+', ' ', page['text'].strip())
        lines = text.splitlines()
        filtered_lines = [line for line in lines if line not in repeated_noise_candidates and line]
        cleaned_text = ' '.join(filtered_lines)
        cleaned_pages.append((page['pdf_page'], cleaned_text))

    # Step 2: Chunk by paragraphs
    chunks = []
    current_chunk = []
    current_pages = set()

    for pdf_page, text in cleaned_pages:
        if not text:
            continue
        paragraphs = re.split(r'(?<=\S)\n+', text)  # Split by newlines that follow non-whitespace
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if len(current_chunk) > 0 and (len(paragraph) < 10 and len(current_chunk[-1]) < 10):
                # If the current chunk is short and the new paragraph is also short, skip it
                continue
            if len(current_chunk) > 0 and (len(current_chunk[-1]) + len(paragraph) + 1 > 1000):
                # Emit the current chunk if it exceeds size limit
                chunks.append({'text': ' '.join(current_chunk), 'pdf_pages': list(current_pages)})
                current_chunk = []
                current_pages = set()
            current_chunk.append(paragraph)
            current_pages.add(pdf_page)

    # Emit any remaining chunk
    if current_chunk:
        chunks.append({'text': ' '.join(current_chunk), 'pdf_pages': list(current_pages)})

    # Step 3: Filter out empty or noise-only chunks
    final_chunks = [chunk for chunk in chunks if chunk['text'] and len(chunk['text']) >= 10]

    return final_chunks