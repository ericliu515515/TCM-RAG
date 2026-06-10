import re
from typing import List, Dict

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, List]]:
    repeated_noise_candidates = {
        "中醫傷科實證臨床治療指引",
        "參考文獻",
        "GRADE",
        "臨床建議內容",
        "建議等級",
        "證據等級",
        "第二篇 指引發展方法學",
        "職稱",
        "姓名",
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
    current_paragraph = []
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
            if re.match(r'^[─]+$', line):  # Skip decorative lines
                continue
            
            if re.match(r'^[第|第二篇|第三篇|第五篇].*$', line):  # Heading lines
                if current_paragraph:
                    chunks.append({
                        'text': ' '.join(current_paragraph).strip(),
                        'pdf_pages': list(current_pages)
                    })
                    current_paragraph = []
                    current_pages = set()
            
            current_paragraph.append(line)
            current_pages.add(pdf_page)
        
        # At the end of the page, if there's a paragraph, add it
        if current_paragraph:
            chunks.append({
                'text': ' '.join(current_paragraph).strip(),
                'pdf_pages': list(current_pages)
            })
            current_paragraph = []
            current_pages = set()
    
    # Filter out empty chunks
    chunks = [chunk for chunk in chunks if chunk['text']]
    
    # Remove heading-only chunks
    chunks = [chunk for chunk in chunks if not (len(chunk['text']) < 10 and all(line in repeated_noise_candidates for line in chunk['text'].split()))]
    
    return chunks