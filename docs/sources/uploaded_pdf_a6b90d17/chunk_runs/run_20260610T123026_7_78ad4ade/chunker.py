import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
    repeated_noise_candidates = {
        "效能", "組成", "方名", "類別", "出處", "語意解析:"
    }
    
    # Step 1: Normalize and clean text
    cleaned_pages = []
    for page in pages:
        pdf_page = page['pdf_page']
        text = page['text'].strip()
        # Normalize line endings and remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove repeated noise lines
        lines = text.split(' ')
        unique_lines = []
        for line in lines:
            if line not in repeated_noise_candidates or line not in unique_lines:
                unique_lines.append(line)
        cleaned_text = ' '.join(unique_lines).strip()
        if cleaned_text:
            cleaned_pages.append((pdf_page, cleaned_text))
    
    # Step 2: Split by paragraph boundaries
    chunks = []
    current_chunk = []
    current_pages = set()
    
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'(?<=。|！|？)\s*', text)  # Split by Chinese punctuation
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:
                if len(current_chunk) > 0 and (len(paragraph) < 10 and len(current_chunk) < 2):
                    # Attach short heading to the next paragraph
                    current_chunk[-1] += ' ' + paragraph
                else:
                    if current_chunk:
                        chunks.append({
                            'text': ' '.join(current_chunk),
                            'pdf_pages': list(current_pages)
                        })
                    current_chunk = [paragraph]
                    current_pages = {pdf_page}
    
    # Final chunk
    if current_chunk:
        chunks.append({
            'text': ' '.join(current_chunk),
            'pdf_pages': list(current_pages)
        })
    
    # Step 3: Filter out empty or noise-only chunks
    final_chunks = []
    for chunk in chunks:
        if chunk['text'] and len(chunk['text']) >= 10:
            final_chunks.append(chunk)
    
    return final_chunks