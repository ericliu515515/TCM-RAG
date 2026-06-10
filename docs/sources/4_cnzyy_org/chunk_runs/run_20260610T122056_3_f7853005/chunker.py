import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
    repeated_noise_candidates = {
        "化。", "（二）生理功能", "（一）生理特性", "用。", "（三）系统联系",
        "2.生理功能", "（二）相关脏腑", "1.生成与分布", "病机变化。", "2.津液代谢"
    }
    
    def clean_text(text: str) -> str:
        # Normalize line endings and trim whitespace
        return re.sub(r'\s+', ' ', text).strip()

    def remove_repeated_noise(text: str) -> str:
        # Remove repeated noise lines
        lines = text.splitlines()
        unique_lines = [line for line in lines if line not in repeated_noise_candidates]
        return "\n".join(unique_lines)

    def split_into_paragraphs(text: str) -> List[str]:
        # Split text into paragraphs based on double newlines
        return [p.strip() for p in text.split('\n\n') if p.strip()]

    chunks = []
    current_pdf_pages = []
    current_chunk = []

    for page in pages:
        pdf_page = page['pdf_page']
        text = clean_text(page['text'])
        cleaned_text = remove_repeated_noise(text)
        
        if not cleaned_text:
            continue
        
        paragraphs = split_into_paragraphs(cleaned_text)
        
        for paragraph in paragraphs:
            if paragraph:
                if len(current_chunk) == 0:
                    current_chunk.append(paragraph)
                    current_pdf_pages.append(pdf_page)
                else:
                    # Check if the current paragraph is a heading and merge if it's short
                    if len(paragraph) < 10 and re.match(r'^[（\d]+.*', paragraph):
                        current_chunk[-1] += ' ' + paragraph
                    else:
                        # Save the current chunk
                        chunks.append({
                            'text': '\n'.join(current_chunk),
                            'pdf_pages': current_pdf_pages
                        })
                        # Start a new chunk
                        current_chunk = [paragraph]
                        current_pdf_pages = [pdf_page]

    # Save the last chunk if it exists
    if current_chunk:
        chunks.append({
            'text': '\n'.join(current_chunk),
            'pdf_pages': current_pdf_pages
        })

    # Filter out empty chunks
    return [chunk for chunk in chunks if chunk['text']]