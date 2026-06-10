import re
from collections import defaultdict
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
        cleaned_lines = [line.strip() for line in lines if line.strip() and line.strip() not in repeated_noise_candidates]
        cleaned_text = '\n'.join(cleaned_lines)
        cleaned_pages.append((page['pdf_page'], cleaned_text))
    
    # Step 2: Group by paragraphs
    chunks = []
    current_chunk = []
    current_pages = set()
    
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'\n\s*\n+', text)
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:
                if len(current_chunk) > 0 and (len(current_chunk[-1]) + len(paragraph) + 1) > 4096:
                    # Emit current chunk
                    chunks.append({
                        'text': '\n\n'.join(current_chunk),
                        'pdf_pages': list(current_pages)
                    })
                    current_chunk = []
                    current_pages = set()
                
                current_chunk.append(paragraph)
                current_pages.add(pdf_page)
    
    # Emit any remaining chunk
    if current_chunk:
        chunks.append({
            'text': '\n\n'.join(current_chunk),
            'pdf_pages': list(current_pages)
        })
    
    # Step 3: Filter out empty or noise-only chunks
    final_chunks = []
    for chunk in chunks:
        if chunk['text'].strip() and len(chunk['text']) > 10:
            final_chunks.append(chunk)
    
    return final_chunks