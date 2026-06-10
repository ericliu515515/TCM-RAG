import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
    repeated_noise_candidates = {
        "效能", "組成", "方名", "類別", "出處", "語意解析:"
    }
    
    def clean_text(text: str) -> str:
        # Normalize line endings and trim whitespace
        return re.sub(r'\s+', ' ', text.strip())

    def is_noise_line(line: str) -> bool:
        # Check if the line is a repeated noise candidate
        return any(noise in line for noise in repeated_noise_candidates)

    # Step 1: Remove repeated page noise
    cleaned_pages = []
    for page in pages:
        lines = clean_text(page['text']).splitlines()
        filtered_lines = [line for line in lines if not is_noise_line(line)]
        cleaned_text = ' '.join(filtered_lines)
        if cleaned_text:
            cleaned_pages.append((page['pdf_page'], cleaned_text))

    # Step 2: Split by paragraph boundaries
    chunks = []
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'\n+', text)
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:
                # Step 3: Keep a short heading with the paragraph immediately after it
                if len(paragraph) < 10 and chunks and chunks[-1]['text'][-1] in repeated_noise_candidates:
                    chunks[-1]['text'] += ' ' + paragraph
                    chunks[-1]['pdf_pages'].append(pdf_page)
                else:
                    chunks.append({'text': paragraph, 'pdf_pages': [pdf_page]})

    # Step 4: Remove empty or noise-only chunks
    final_chunks = []
    for chunk in chunks:
        if chunk['text'] and not all(is_noise_line(line) for line in chunk['text'].splitlines()):
            final_chunks.append(chunk)

    return final_chunks