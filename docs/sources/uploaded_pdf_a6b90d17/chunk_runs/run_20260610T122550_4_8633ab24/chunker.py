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
        text = re.sub(r'\n+', '\n', page['text'].strip())
        lines = text.splitlines()
        # Remove repeated noise lines
        unique_lines = []
        for line in lines:
            if line.strip() and line not in repeated_noise_candidates:
                unique_lines.append(line.strip())
        cleaned_pages.append((page['pdf_page'], unique_lines))
    
    # Step 2: Chunk by paragraphs
    chunks = []
    current_chunk = []
    current_pages = set()
    
    for pdf_page, lines in cleaned_pages:
        for line in lines:
            if line.endswith(':') and len(current_chunk) > 0:
                # If it's a heading, attach it to the next paragraph
                current_chunk[-1] += f" {line}"
            elif line.strip() == "":
                # Empty line indicates a paragraph break
                if current_chunk:
                    chunks.append({"text": "\n".join(current_chunk).strip(), "pdf_pages": list(current_pages)})
                    current_chunk = []
                    current_pages = set()
            else:
                current_chunk.append(line)
                current_pages.add(pdf_page)
        
        # If there's any remaining text after the last line
        if current_chunk:
            chunks.append({"text": "\n".join(current_chunk).strip(), "pdf_pages": list(current_pages)})
            current_chunk = []
            current_pages = set()
    
    # Step 3: Filter out empty chunks and noise-only chunks
    final_chunks = []
    for chunk in chunks:
        if chunk['text'] and len(chunk['text']) > 10:
            final_chunks.append(chunk)
    
    return final_chunks