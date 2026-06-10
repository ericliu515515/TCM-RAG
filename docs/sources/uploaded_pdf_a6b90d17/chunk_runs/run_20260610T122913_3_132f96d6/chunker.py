import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
    repeated_noise_candidates = {
        "效能", "組成", "方名", "類別", "出處", "語意解析:", 
        "Glycyrrhizae Radix et Rhizoma", "茯苓", "Poria;", "炙甘草", 
        "甘草", "Praeparatum cum Melle;", "生薑", "當歸", "人參", 
        "Angelicae Sinensis Radix;", "白芍", "Paeoniae Alba Radix;", 
        "Zingiberis Rhizoma Recens;"
    }
    
    # Step 1: Normalize and clean text
    cleaned_pages = []
    for page in pages:
        text = re.sub(r'\n+', '\n', page['text']).strip()
        lines = text.splitlines()
        filtered_lines = [line for line in lines if line.strip() and line.strip() not in repeated_noise_candidates]
        cleaned_text = '\n'.join(filtered_lines)
        cleaned_pages.append((page['pdf_page'], cleaned_text))
    
    # Step 2: Split into paragraphs
    chunks = []
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'\n\s*\n+', text)
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:
                # Check if the paragraph is a heading and attach it to the next paragraph if it's short
                if len(paragraph) < 10 and not any(char.isalnum() for char in paragraph):
                    continue
                chunks.append({'text': paragraph, 'pdf_pages': [pdf_page]})
    
    # Step 3: Merge paragraphs that are split across pages
    final_chunks = []
    current_chunk = None
    
    for chunk in chunks:
        if current_chunk is None:
            current_chunk = chunk
        else:
            if current_chunk['text'].endswith('.') or current_chunk['text'].endswith('。'):
                final_chunks.append(current_chunk)
                current_chunk = chunk
            else:
                current_chunk['text'] += '\n' + chunk['text']
                current_chunk['pdf_pages'].extend(chunk['pdf_pages'])
    
    if current_chunk:
        final_chunks.append(current_chunk)
    
    # Step 4: Remove empty or noise-only chunks
    final_chunks = [chunk for chunk in final_chunks if chunk['text'].strip()]

    return final_chunks