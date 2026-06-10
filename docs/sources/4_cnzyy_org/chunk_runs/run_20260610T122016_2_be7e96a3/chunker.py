import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
    repeated_noise_candidates = {
        "化。", "（二）生理功能", "（一）生理特性", "用。", "（三）系统联系",
        "2.生理功能", "（二）相关脏腑", "1.生成与分布", "病机变化。", "2.津液代谢"
    }
    
    # Normalize line endings and trim whitespace
    cleaned_pages = []
    for page in pages:
        text = re.sub(r'\s+', ' ', page['text'].strip())
        cleaned_pages.append((page['pdf_page'], text))
    
    # Remove repeated noise lines
    def is_noise_line(line: str) -> bool:
        return any(noise in line for noise in repeated_noise_candidates)
    
    cleaned_texts = []
    for pdf_page, text in cleaned_pages:
        lines = text.split('。')
        filtered_lines = [line for line in lines if not is_noise_line(line)]
        cleaned_texts.append((pdf_page, filtered_lines))
    
    # Split by paragraph boundaries
    chunks = []
    for pdf_page, paragraphs in cleaned_texts:
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:
                chunks.append({"text": paragraph, "pdf_pages": [pdf_page]})
    
    # Merge short headings with the following paragraph
    final_chunks = []
    for i in range(len(chunks)):
        if i < len(chunks) - 1 and len(chunks[i]['text']) < 10:
            # Merge with the next chunk
            chunks[i + 1]['text'] = chunks[i]['text'] + ' ' + chunks[i + 1]['text']
            chunks[i + 1]['pdf_pages'].insert(0, chunks[i]['pdf_pages'][0])
        else:
            final_chunks.append(chunks[i])
    
    # Remove empty chunks and ensure no chunk is just noise
    final_chunks = [chunk for chunk in final_chunks if chunk['text'] and not is_noise_line(chunk['text'])]
    
    return final_chunks