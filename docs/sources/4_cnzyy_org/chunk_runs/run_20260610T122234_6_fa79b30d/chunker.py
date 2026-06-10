import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
    repeated_noise_candidates = {
        "化。", "（二）生理功能", "（一）生理特性", "用。", "（三）系统联系",
        "2.生理功能", "（二）相关脏腑", "1.生成与分布", "病机变化。", "2.津液代谢"
    }
    
    # Step 1: Normalize and clean text
    cleaned_pages = []
    for page in pages:
        text = re.sub(r'\s+', ' ', page['text'].strip())
        lines = text.splitlines()
        # Remove repeated noise lines
        unique_lines = []
        for line in lines:
            if line not in repeated_noise_candidates:
                unique_lines.append(line)
        cleaned_text = ' '.join(unique_lines)
        cleaned_pages.append((page['pdf_page'], cleaned_text))
    
    # Step 2: Split into paragraphs
    chunks = []
    for pdf_page, text in cleaned_pages:
        paragraphs = re.split(r'(?<=[。])\s*', text)  # Split by Chinese period
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph:  # Only non-empty paragraphs
                chunks.append({'text': paragraph, 'pdf_pages': [pdf_page]})
    
    # Step 3: Merge short headings with following paragraphs
    final_chunks = []
    for i in range(len(chunks)):
        if i < len(chunks) - 1 and len(chunks[i]['text']) < 10:
            # Merge with next paragraph
            chunks[i + 1]['text'] = chunks[i]['text'] + ' ' + chunks[i + 1]['text']
            chunks[i + 1]['pdf_pages'].append(chunks[i]['pdf_pages'][0])
        else:
            final_chunks.append(chunks[i])
    
    # Step 4: Remove empty or noise-only chunks
    final_chunks = [chunk for chunk in final_chunks if chunk['text'] and len(chunk['text']) > 10]
    
    return final_chunks