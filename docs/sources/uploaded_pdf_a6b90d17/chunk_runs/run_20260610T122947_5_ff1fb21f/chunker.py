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
    
    def clean_text(text: str) -> str:
        lines = text.splitlines()
        cleaned_lines = [line.strip() for line in lines if line.strip() and line.strip() not in repeated_noise_candidates]
        return "\n".join(cleaned_lines)

    chunks = []
    current_chunk = []
    current_pages = []
    
    for page in pages:
        pdf_page = page['pdf_page']
        text = clean_text(page['text'])
        
        if not text:
            continue
        
        paragraphs = re.split(r'\n\s*\n+', text)
        
        for paragraph in paragraphs:
            if paragraph.strip():
                if len(current_chunk) == 0:
                    current_chunk.append(paragraph)
                    current_pages.append(pdf_page)
                else:
                    if len(current_chunk) == 1 and len(current_chunk[0]) < 10:
                        current_chunk[0] += "\n" + paragraph
                    else:
                        chunks.append({"text": current_chunk[0], "pdf_pages": current_pages})
                        current_chunk = [paragraph]
                        current_pages = [pdf_page]
    
    if current_chunk:
        chunks.append({"text": current_chunk[0], "pdf_pages": current_pages})
    
    return [chunk for chunk in chunks if chunk['text'].strip()]