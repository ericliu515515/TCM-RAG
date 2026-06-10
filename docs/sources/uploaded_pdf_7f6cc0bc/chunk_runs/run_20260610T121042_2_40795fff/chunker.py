import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
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
    
    # Step 2: Split into paragraphs
    chunks = []
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'\n\s*\n+', text)  # Split by double newlines
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:
                # Check if the paragraph is a heading and attach it to the next paragraph if it's short
                if len(paragraph) < 10 and not any(char.isalnum() for char in paragraph):
                    continue  # Skip heading-only chunks
                chunks.append((paragraph, [pdf_page]))
    
    # Step 3: Merge consecutive paragraphs that belong together
    final_chunks = []
    current_chunk = None
    
    for paragraph, pdf_pages in chunks:
        if current_chunk is None:
            current_chunk = (paragraph, pdf_pages)
        else:
            # Check if the current paragraph is a continuation of the previous one
            if current_chunk[0].endswith('.') or current_chunk[0].endswith(':'):
                current_chunk = (current_chunk[0] + "\n" + paragraph, current_chunk[1] + pdf_pages)
            else:
                final_chunks.append(current_chunk)
                current_chunk = (paragraph, pdf_pages)
    
    if current_chunk:
        final_chunks.append(current_chunk)
    
    # Step 4: Create output structure
    output_chunks = []
    for text, pdf_pages in final_chunks:
        if len(text) > 0:
            output_chunks.append({"text": text, "pdf_pages": list(set(pdf_pages))})
    
    return output_chunks