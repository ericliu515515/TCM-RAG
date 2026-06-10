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
        return any(noise in line for noise in repeated_noise_candidates)

    chunks = []
    current_chunk = []
    current_pages = set()

    for page in pages:
        pdf_page = page['pdf_page']
        text = clean_text(page['text'])
        lines = text.splitlines()

        for line in lines:
            if is_noise_line(line):
                continue
            
            if line:  # Non-empty line
                if current_chunk and (line[0].isupper() and len(current_chunk[-1]) < 10):
                    # Merge short heading with the next paragraph
                    current_chunk[-1] += ' ' + line
                else:
                    if current_chunk:
                        chunks.append({'text': ' '.join(current_chunk), 'pdf_pages': list(current_pages)})
                    current_chunk = [line]
                    current_pages = {pdf_page}
            else:
                if current_chunk:
                    chunks.append({'text': ' '.join(current_chunk), 'pdf_pages': list(current_pages)})
                    current_chunk = []
                    current_pages = set()

        if current_chunk:
            chunks.append({'text': ' '.join(current_chunk), 'pdf_pages': list(current_pages)})
            current_chunk = []
            current_pages = set()

    # Filter out empty chunks
    chunks = [chunk for chunk in chunks if chunk['text']]

    return chunks