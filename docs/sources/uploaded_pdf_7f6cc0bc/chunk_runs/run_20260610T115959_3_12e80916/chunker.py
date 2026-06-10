import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> Dict[str, List[Dict[str, List[int]]]]:
    repeated_noise_candidates = {
        "療", "實", "針", "指", "灸", "床", "治", "引", "臨", "證", "篇", "第", "統", "系", "神", "經", "四", "一", "十"
    }
    
    # Step 1: Normalize and clean text
    cleaned_pages = []
    for page in pages:
        pdf_page = page['pdf_page']
        text = page['text'].strip()
        # Remove repeated noise lines
        lines = text.splitlines()
        unique_lines = []
        for line in lines:
            if line.strip() and not any(noise in line for noise in repeated_noise_candidates):
                unique_lines.append(line.strip())
        cleaned_text = "\n".join(unique_lines)
        cleaned_pages.append((pdf_page, cleaned_text))
    
    # Step 2: Split by paragraph boundaries
    chunks = []
    current_chunk = []
    current_pages = set()
    
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'\n\s*\n+', text)  # Split by double newlines
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            # Check if the paragraph is a heading
            if len(paragraph) < 10 and current_chunk:
                # Attach short heading to the last chunk
                current_chunk[-1]['text'] += "\n" + paragraph
                current_chunk[-1]['pdf_pages'].add(pdf_page)
            else:
                # Create a new chunk
                chunks.append({'text': paragraph, 'pdf_pages': {pdf_page}})
    
    # Step 3: Finalize chunks
    final_chunks = []
    for chunk in chunks:
        if chunk['text']:
            final_chunks.append({
                'text': chunk['text'],
                'pdf_pages': list(chunk['pdf_pages'])
            })
    
    return {'chunks': final_chunks}