import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
    repeated_noise_candidates = {
        "療", "實", "針", "指", "灸", "床", "治", "引", "臨", "證", "篇", "第", "統", "系", "神", "經", "四", "一", "十"
    }
    
    def clean_text(text: str) -> str:
        # Normalize line endings and trim whitespace
        text = re.sub(r'\r\n|\r|\n', '\n', text).strip()
        # Remove repeated noise lines
        lines = text.split('\n')
        unique_lines = []
        seen_lines = set()
        for line in lines:
            if line not in seen_lines and not any(noise in line for noise in repeated_noise_candidates):
                unique_lines.append(line)
                seen_lines.add(line)
        return '\n'.join(unique_lines)

    def split_into_paragraphs(text: str) -> List[str]:
        # Split text into paragraphs based on double newlines
        return [p.strip() for p in text.split('\n\n') if p.strip()]

    chunks = []
    current_chunk = []
    current_pages = []

    for page in pages:
        pdf_page = page['pdf_page']
        text = clean_text(page['text'])
        paragraphs = split_into_paragraphs(text)

        for paragraph in paragraphs:
            if paragraph:
                # Check if the paragraph is a heading
                if len(paragraph) < 10 and current_chunk:
                    # Merge short heading with the last paragraph
                    current_chunk[-1] += ' ' + paragraph
                else:
                    # Save the current chunk if it exists
                    if current_chunk:
                        chunks.append({'text': '\n'.join(current_chunk), 'pdf_pages': current_pages})
                    # Start a new chunk
                    current_chunk = [paragraph]
                    current_pages = [pdf_page]
        
        # If the last paragraph continues from the previous page, keep it in the same chunk
        if current_chunk and pdf_page not in current_pages:
            current_pages.append(pdf_page)

    # Add the last chunk if it exists
    if current_chunk:
        chunks.append({'text': '\n'.join(current_chunk), 'pdf_pages': current_pages})

    # Filter out empty chunks
    return [chunk for chunk in chunks if chunk['text']]