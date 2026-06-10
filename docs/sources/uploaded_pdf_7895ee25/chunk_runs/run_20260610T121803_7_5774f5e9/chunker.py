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
        lines = [line for line in lines if line not in repeated_noise_candidates]
        
        # Group lines into paragraphs
        paragraph = []
        for line in lines:
            if re.match(r'^[─]*$', line):  # Skip decorative lines
                continue
            if re.match(r'^[第|第二篇|第三篇|第四篇|第五篇].*$', line):  # Heading lines
                if paragraph:
                    # Emit the current paragraph as a chunk
                    chunks.append({
                        'text': ' '.join(paragraph),
                        'pdf_pages': list(current_pages)
                    })
                    paragraph = []
                    current_pages = set()
            paragraph.append(line)
            current_pages.add(pdf_page)

        # Emit any remaining paragraph
        if paragraph:
            chunks.append({
                'text': ' '.join(paragraph),
                'pdf_pages': list(current_pages)
            })

    # Filter out empty chunks
    chunks = [chunk for chunk in chunks if chunk['text']]

    # Remove heading-only chunks
    chunks = [chunk for chunk in chunks if not (len(chunk['text'].strip()) < 10 and len(chunk['text'].strip().split()) == 1)]

    return chunks