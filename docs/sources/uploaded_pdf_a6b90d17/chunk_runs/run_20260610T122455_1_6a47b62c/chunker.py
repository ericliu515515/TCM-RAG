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
    
    cleaned_pages = []
    
    for page in pages:
        text = page['text'].strip()
        # Normalize line endings and trim whitespace
        text = re.sub(r'\n+', '\n', text)
        lines = text.splitlines()
        
        # Remove repeated noise lines
        unique_lines = []
        for line in lines:
            if line.strip() and line not in repeated_noise_candidates:
                unique_lines.append(line.strip())
        
        cleaned_text = '\n'.join(unique_lines)
        if cleaned_text:
            cleaned_pages.append((page['pdf_page'], cleaned_text))
    
    chunks = []
    current_chunk = []
    current_pages = set()
    
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'\n\s*\n+', text)
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            # Check if the paragraph is a heading and merge with the next paragraph if it's short
            if len(paragraph) < 10 and chunks and current_chunk:
                current_chunk[-1] += ' ' + paragraph
                continue
            
            # If current_chunk is not empty, save it
            if current_chunk:
                chunks.append({
                    'text': '\n'.join(current_chunk),
                    'pdf_pages': list(current_pages)
                })
                current_chunk = []
                current_pages = set()
            
            current_chunk = [paragraph]
            current_pages.add(pdf_page)
        
        # If there's any remaining chunk after the loop
        if current_chunk:
            chunks.append({
                'text': '\n'.join(current_chunk),
                'pdf_pages': list(current_pages)
            })
    
    # Filter out empty chunks
    return [chunk for chunk in chunks if chunk['text']]