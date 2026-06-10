import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
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
        cleaned_lines = [line.strip() for line in lines if line.strip() and line.strip() not in repeated_noise_candidates]
        cleaned_text = '\n'.join(cleaned_lines)
        cleaned_pages.append((page['pdf_page'], cleaned_text))
    
    # Step 2: Chunk by paragraph
    chunks = []
    current_chunk = []
    current_pages = set()
    
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'\n\s*\n+', text)
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:
                if len(current_chunk) > 0 and (len(current_chunk) == 1 and len(paragraph) < 10):
                    # Merge short heading with the next paragraph
                    current_chunk.append(paragraph)
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
    final_chunks = [chunk for chunk in chunks if chunk['text'].strip()]
    
    return final_chunks