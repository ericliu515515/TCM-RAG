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
        text = re.sub(r'\n+', '\n', page['text']).strip()  # Normalize line endings
        lines = text.splitlines()
        # Remove repeated noise lines
        unique_lines = []
        for line in lines:
            if line.strip() and line not in repeated_noise_candidates:
                unique_lines.append(line.strip())
        cleaned_text = '\n'.join(unique_lines)
        cleaned_pages.append((page['pdf_page'], cleaned_text))
    
    # Step 2: Split by paragraph boundaries
    chunks = []
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'\n\s*\n+', text)  # Split by double newlines
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:  # Only non-empty paragraphs
                chunks.append({'text': paragraph, 'pdf_pages': [pdf_page]})
    
    # Step 3: Merge short headings with following paragraphs
    final_chunks = []
    for i in range(len(chunks)):
        current_chunk = chunks[i]
        if len(current_chunk['text']) < 10 and i > 0:
            # Merge with previous chunk if it's a short heading
            final_chunks[-1]['text'] += '\n' + current_chunk['text']
            final_chunks[-1]['pdf_pages'].append(current_chunk['pdf_pages'][0])
        else:
            final_chunks.append(current_chunk)
    
    # Step 4: Remove empty or noise-only chunks
    final_chunks = [chunk for chunk in final_chunks if chunk['text'].strip()]
    
    return final_chunks