import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List[int]]]:
    repeated_noise_candidates = {
        "中醫傷科實證臨床治療指引",
        "參考文獻",
        "GRADE",
        "臨床建議內容",
        "建議等級",
        "證據等級",
        "第二篇 指引發展方法學",
        "姓名",
        "職稱",
        "單位",
        "強建議",
        "篇",
        "第",
        "1B",
        "B 級",
        "[2]",
        "主治醫師",
        "[1-5]",
        "醫師",
        "1C"
    }

    chunks = []
    current_chunk = []
    current_pages = []

    for page in pages:
        pdf_page = page['pdf_page']
        text = page['text'].strip()
        if not text:
            continue
        
        # Normalize line endings and trim whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        
        # Remove repeated noise lines
        filtered_lines = [line for line in lines if line not in repeated_noise_candidates]
        
        # Group lines into paragraphs
        paragraph = []
        for line in filtered_lines:
            if re.match(r'^[\u4e00-\u9fa5]+$', line):  # Check if line is a heading
                if paragraph:
                    # Emit the current paragraph as a chunk
                    chunks.append({'text': ' '.join(paragraph), 'pdf_pages': current_pages})
                    paragraph = []
                    current_pages = []
            paragraph.append(line)
            current_pages.append(pdf_page)

        if paragraph:
            chunks.append({'text': ' '.join(paragraph), 'pdf_pages': current_pages})

    # Clean up chunks: remove empty or noise-only chunks
    final_chunks = []
    for chunk in chunks:
        if chunk['text'] and len(chunk['text']) > 10:
            final_chunks.append(chunk)

    return final_chunks