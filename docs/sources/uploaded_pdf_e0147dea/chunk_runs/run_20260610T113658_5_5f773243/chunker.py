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
    current_pages = set()

    for page in pages:
        pdf_page = page['pdf_page']
        text = page['text'].strip()
        if not text:
            continue
        
        # Normalize line endings and trim whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        
        # Remove repeated noise lines
        filtered_lines = [line for line in lines if line not in repeated_noise_candidates]
        
        for line in filtered_lines:
            # Check for paragraph boundaries
            if re.match(r'^[\u4e00-\u9fa5]+$', line):  # Assuming headings are in Chinese characters
                if current_chunk:
                    chunks.append({
                        'text': ' '.join(current_chunk).strip(),
                        'pdf_pages': list(current_pages)
                    })
                    current_chunk = []
                    current_pages = set()
            
            current_chunk.append(line)
            current_pages.add(pdf_page)

        # If there's remaining text after processing the page
        if current_chunk:
            chunks.append({
                'text': ' '.join(current_chunk).strip(),
                'pdf_pages': list(current_pages)
            })
            current_chunk = []
            current_pages = set()

    # Filter out empty chunks
    chunks = [chunk for chunk in chunks if chunk['text']]

    return chunks