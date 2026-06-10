import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
    repeated_noise_candidates = {
        "療", "實", "針", "指", "灸", "床", "治", "引", "臨", "證", "篇", "第", "統", "系", "神", "經", "四", "一", "十"
    }
    
    # Step 1: Normalize and clean text
    cleaned_pages = []
    for page in pages:
        text = page['text'].strip()
        # Remove repeated noise lines
        lines = text.splitlines()
        unique_lines = []
        for line in lines:
            if line not in repeated_noise_candidates:
                unique_lines.append(line)
        cleaned_text = "\n".join(unique_lines).strip()
        cleaned_pages.append((page['pdf_page'], cleaned_text))
    
    # Step 2: Chunk by paragraph boundaries
    chunks = []
    current_chunk = []
    current_pages = set()
    
    for pdf_page, text in cleaned_pages:
        if not text:
            continue
        paragraphs = re.split(r'\n\s*\n+', text)  # Split by double newlines
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if len(current_chunk) > 0 and (len(paragraph) < 10 and len(current_chunk) < 10):
                # If current chunk is short, merge with next paragraph
                current_chunk.append(paragraph)
                current_pages.add(pdf_page)
            else:
                if current_chunk:
                    chunks.append({
                        'text': "\n".join(current_chunk),
                        'pdf_pages': list(current_pages)
                    })
                current_chunk = [paragraph]
                current_pages = {pdf_page}
    
    # Final chunk
    if current_chunk:
        chunks.append({
            'text': "\n".join(current_chunk),
            'pdf_pages': list(current_pages)
        })
    
    # Step 3: Filter out empty or noise-only chunks
    final_chunks = []
    for chunk in chunks:
        if chunk['text'].strip() and len(chunk['text']) > 10:
            final_chunks.append(chunk)
    
    return final_chunks