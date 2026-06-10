import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> Dict[str, List[Dict[str, List[int]]]]:
    repeated_noise_candidates = {
        "療", "實", "針", "指", "灸", "床", "治", "引", "臨", "證", "篇", "第", "統", "系", "神", "經", "四", "一", "十"
    }
    
    def clean_text(text: str) -> str:
        # Normalize line endings and trim whitespace
        text = re.sub(r'\r\n|\r|\n', '\n', text).strip()
        return text

    def remove_repeated_noise(text: str) -> str:
        # Remove lines that are considered noise
        lines = text.splitlines()
        unique_lines = []
        seen_lines = set()
        for line in lines:
            if line not in seen_lines and line not in repeated_noise_candidates:
                unique_lines.append(line)
                seen_lines.add(line)
        return "\n".join(unique_lines)

    def split_into_paragraphs(text: str) -> List[str]:
        # Split text into paragraphs based on double newlines
        return [p.strip() for p in text.split('\n\n') if p.strip()]

    chunks = []
    for page in pages:
        pdf_page = page['pdf_page']
        text = clean_text(page['text'])
        text = remove_repeated_noise(text)
        paragraphs = split_into_paragraphs(text)

        for paragraph in paragraphs:
            if paragraph:
                # Check if the paragraph is a heading and merge with the next paragraph if it's short
                if len(paragraph) < 10 and chunks and chunks[-1]['text'].endswith('\n'):
                    chunks[-1]['text'] += ' ' + paragraph
                    chunks[-1]['pdf_pages'].append(pdf_page)
                else:
                    chunks.append({'text': paragraph, 'pdf_pages': [pdf_page]})

    # Remove empty chunks and ensure no heading-only chunks
    chunks = [chunk for chunk in chunks if chunk['text'] and not (len(chunk['text']) < 10 and len(chunk['pdf_pages']) == 1)]

    return {'chunks': chunks}