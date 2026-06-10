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
            text = re.sub(r'(?<!\S)'+re.escape(noise)+r'(?!\S)', '', text)
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
            
            # Check if the paragraph is a heading
            if len(paragraph) < 10 and current_chunk:
                # Attach short heading to the last chunk
                current_chunk[-1]['text'] += ' ' + paragraph
                current_chunk[-1]['pdf_pages'].append(pdf_page)
            else:
                # Create a new chunk
                chunks.append({'text': paragraph, 'pdf_pages': [pdf_page]})
    
    # Step 3: Merge consecutive chunks with the same pdf_page
    final_chunks = []
    for chunk in chunks:
        if final_chunks and final_chunks[-1]['pdf_pages'][-1] == chunk['pdf_pages'][0]:
            final_chunks[-1]['text'] += ' ' + chunk['text']
            final_chunks[-1]['pdf_pages'].extend(chunk['pdf_pages'])
        else:
            final_chunks.append(chunk)
    
    # Step 4: Filter out empty chunks and noise-only chunks
    final_chunks = [chunk for chunk in final_chunks if chunk['text'].strip()]
    
    return final_chunks