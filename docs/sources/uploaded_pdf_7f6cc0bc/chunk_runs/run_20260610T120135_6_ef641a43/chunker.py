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
                # Check if the paragraph is a heading and merge with the next paragraph if it's short
                if len(paragraph) < 10 and chunks:
                    chunks[-1]['text'] += ' ' + paragraph
                else:
                    chunks.append({'text': paragraph, 'pdf_pages': [pdf_page]})
    
    # Step 3: Merge paragraphs that span across pages
    merged_chunks = []
    for i in range(len(chunks)):
        if i > 0 and chunks[i]['pdf_pages'][0] == chunks[i-1]['pdf_pages'][-1] + 1:
            merged_chunks[-1]['text'] += ' ' + chunks[i]['text']
            merged_chunks[-1]['pdf_pages'].extend(chunks[i]['pdf_pages'])
        else:
            merged_chunks.append(chunks[i])
    
    # Step 4: Filter out empty or noise-only chunks
    final_chunks = []
    for chunk in merged_chunks:
        if chunk['text'] and len(chunk['text']) > 10:
            final_chunks.append(chunk)
    
    return final_chunks