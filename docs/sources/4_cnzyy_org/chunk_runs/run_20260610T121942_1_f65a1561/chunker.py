import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List]]:
    repeated_noise_candidates = {
        "化。": 9,
        "（二）生理功能": 9,
        "（一）生理特性": 9,
        "用。": 8,
        "（三）系统联系": 8,
        "2.生理功能": 6,
        "（二）相关脏腑": 6,
        "1.生成与分布": 6,
        "病机变化。": 5,
        "2.津液代谢": 5
    }
    
    # Step 1: Normalize line endings and trim whitespace
    cleaned_pages = []
    for page in pages:
        text = re.sub(r'\s+', ' ', page['text'].strip())
        cleaned_pages.append((page['pdf_page'], text))
    
    # Step 2: Remove repeated noise lines
    noise_set = set(repeated_noise_candidates.keys())
    filtered_texts = []
    
    for pdf_page, text in cleaned_pages:
        lines = text.split('。')
        filtered_lines = [line.strip() + '。' for line in lines if line.strip() and line.strip() not in noise_set]
        filtered_texts.append((pdf_page, filtered_lines))
    
    # Step 3: Split by paragraph boundaries
    chunks = []
    
    for pdf_page, lines in filtered_texts:
        paragraph = []
        for line in lines:
            if re.match(r'^[（\d]+.*', line):  # Heading detected
                if paragraph:
                    chunks.append({'text': ' '.join(paragraph).strip(), 'pdf_pages': [pdf_page]})
                    paragraph = []
            paragraph.append(line)
        
        if paragraph:
            chunks.append({'text': ' '.join(paragraph).strip(), 'pdf_pages': [pdf_page]})
    
    # Step 4: Merge short headings with the following paragraph
    final_chunks = []
    for i in range(len(chunks)):
        if len(chunks[i]['text']) < 10 and i > 0:
            final_chunks[-1]['text'] += ' ' + chunks[i]['text']
            final_chunks[-1]['pdf_pages'].extend(chunks[i]['pdf_pages'])
        else:
            final_chunks.append(chunks[i])
    
    # Step 5: Remove empty or noise-only chunks
    final_chunks = [chunk for chunk in final_chunks if chunk['text']]
    
    return final_chunks