import re
from typing import List, Dict, Any

def chunk_pages(pages: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    repeated_noise_candidates = {
        "效能", "組成", "方名", "類別", "出處", "語意解析:", 
        "Glycyrrhizae Radix et Rhizoma", "茯苓", "Poria;", "炙甘草", 
        "甘草", "Praeparatum cum Melle;", "生薑", "當歸", "人參", 
        "Angelicae Sinensis Radix;", "白芍", "Glycyrrhizae Radix et Rhizoma;", 
        "Paeoniae Alba Radix;", "Zingiberis Rhizoma Recens;"
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
    current_chunk = []
    current_pdf_pages = set()
    
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'\n\s*\n+', text)
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:
                current_chunk.append(paragraph)
                current_pdf_pages.add(pdf_page)
                # If the paragraph is short, check if it can be merged with the next
                if len(paragraph) < 10 and current_chunk:
                    continue
                # If we have a complete chunk, save it
                if current_chunk:
                    chunks.append({
                        "text": '\n\n'.join(current_chunk),
                        "pdf_pages": sorted(current_pdf_pages)
                    })
                    current_chunk = []
                    current_pdf_pages = set()
    
    # Step 3: Finalize any remaining chunk
    if current_chunk:
        chunks.append({
            "text": '\n\n'.join(current_chunk),
            "pdf_pages": sorted(current_pdf_pages)
        })
    
    # Step 4: Remove empty or noise-only chunks
    chunks = [chunk for chunk in chunks if chunk['text'].strip() and len(chunk['text']) > 10]
    
    return {"chunks": chunks}