import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List]]:
    repeated_noise_candidates = {
        "化。": 9,
        "（二）生理功能": 9,
        "（一）生理特性": 9,
        "用。": 8,
        "（三）系统联系": 8,
        "2.生理功能": 6,
        "（二）相关脏腑": 6,
        "1.生成与分布": 6,
        "病机变化。": 5,
        "2.津液代谢": 5
    }
    
    # Step 1: Normalize and clean text
    cleaned_pages = []
    for page in pages:
        text = page['text'].strip()
        # Remove repeated noise lines
        for noise in repeated_noise_candidates.keys():
            text = re.sub(r'\b' + re.escape(noise) + r'\b', '', text)
        cleaned_pages.append((page['pdf_page'], text))
    
    # Step 2: Split text into paragraphs
    chunks = []
    current_chunk = []
    current_pdf_pages = set()
    
    for pdf_page, text in cleaned_pages:
        if not text:
            continue
        paragraphs = re.split(r'\n+', text)
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            current_pdf_pages.add(pdf_page)
            if len(current_chunk) > 0 and (len(paragraph) < 10 or paragraph[0].isdigit()):
                # If the current paragraph is a heading or very short, merge with the last chunk
                current_chunk[-1]['text'] += ' ' + paragraph
            else:
                # Create a new chunk
                chunks.append({'text': paragraph, 'pdf_pages': [pdf_page]})
                current_chunk.append(chunks[-1])
    
    # Step 3: Merge chunks that are on the same page
    final_chunks = []
    for chunk in chunks:
        if final_chunks and set(chunk['pdf_pages']) == set(final_chunks[-1]['pdf_pages']):
            final_chunks[-1]['text'] += ' ' + chunk['text']
        else:
            final_chunks.append(chunk)
    
    # Step 4: Remove empty chunks and ensure no chunk is just noise
    final_chunks = [chunk for chunk in final_chunks if chunk['text'].strip() and len(chunk['text'].strip()) > 10]
    
    return final_chunks