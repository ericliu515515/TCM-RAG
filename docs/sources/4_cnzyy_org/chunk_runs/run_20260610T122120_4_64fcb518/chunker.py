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
    current_pdf_pages = []
    current_chunk = []
    
    for pdf_page, text in cleaned_pages:
        if not text:
            continue
        paragraphs = re.split(r'\n+', text)
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            # Check if the paragraph is a heading and merge with the next paragraph if it's short
            if len(paragraph) < 10 and current_chunk:
                current_chunk[-1] += paragraph
                continue
            
            # If current_chunk is not empty, save it
            if current_chunk:
                chunks.append({
                    'text': ' '.join(current_chunk),
                    'pdf_pages': current_pdf_pages
                })
                current_chunk = []
                current_pdf_pages = []
            
            # Add new paragraph to current chunk
            current_chunk = [paragraph]
            current_pdf_pages = [pdf_page]
        
        # If we reach the end of the page, save the last chunk
        if current_chunk:
            chunks.append({
                'text': ' '.join(current_chunk),
                'pdf_pages': current_pdf_pages
            })
            current_chunk = []
            current_pdf_pages = []
    
    # Step 3: Filter out empty chunks and noise-only chunks
    final_chunks = []
    for chunk in chunks:
        if chunk['text'] and len(chunk['text']) > 10:
            final_chunks.append(chunk)
    
    return final_chunks