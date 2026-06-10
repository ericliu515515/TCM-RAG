import re
from collections import defaultdict
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
    repeated_noise_candidates = {
        "效能", "組成", "方名", "類別", "出處", "語意解析:"
    }
    
    # Step 1: Normalize and clean text
    cleaned_pages = []
    for page in pages:
        text = re.sub(r'\n+', '\n', page['text']).strip()
        lines = text.splitlines()
        cleaned_lines = []
        for line in lines:
            if line.strip() and line not in repeated_noise_candidates:
                cleaned_lines.append(line.strip())
        cleaned_text = '\n'.join(cleaned_lines)
        if cleaned_text:
            cleaned_pages.append((page['pdf_page'], cleaned_text))
    
    # Step 2: Group by paragraphs
    chunks = []
    current_chunk = []
    current_pages = set()
    
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'\n\s*\n+', text)  # Split by double newlines
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:
                if len(current_chunk) > 0 and (len(paragraph) < 10 and len(current_chunk) < 2):
                    # Attach short heading to the next paragraph
                    current_chunk[-1] += '\n' + paragraph
                else:
                    if current_chunk:
                        chunks.append({
                            'text': '\n'.join(current_chunk),
                            'pdf_pages': list(current_pages)
                        })
                    current_chunk = [paragraph]
                    current_pages = {pdf_page}
    
    # Final chunk
    if current_chunk:
        chunks.append({
            'text': '\n'.join(current_chunk),
            'pdf_pages': list(current_pages)
        })
    
    # Step 3: Filter out empty or noise-only chunks
    final_chunks = []
    for chunk in chunks:
        if chunk['text'].strip() and len(chunk['text']) > 10:
            final_chunks.append(chunk)
    
    return final_chunks