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
    current_pages = []
    
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
        paragraphs = []
        current_paragraph = []
        
        for line in lines:
            if re.match(r'^[\u4e00-\u9fa5]+$', line):  # Check if line is a heading
                if current_paragraph:
                    paragraphs.append(' '.join(current_paragraph))
                    current_paragraph = []
                current_paragraph.append(line)
            elif line:  # Non-empty line
                current_paragraph.append(line)
        
        if current_paragraph:
            paragraphs.append(' '.join(current_paragraph))
        
        # Create chunks from paragraphs
        for paragraph in paragraphs:
            if paragraph:
                if len(paragraph) < 10 and len(chunks) >= len(pages) * 0.9:
                    continue  # Skip very short chunks if they exceed 10% of total
                if current_chunk and (len(current_chunk[-1]) + len(paragraph) + 1) < 10:
                    current_chunk[-1] += ' ' + paragraph
                else:
                    if current_chunk:
                        chunks.append({'text': current_chunk[-1], 'pdf_pages': current_pages})
                    current_chunk = [paragraph]
                    current_pages = [pdf_page]
                if pdf_page not in current_pages:
                    current_pages.append(pdf_page)
    
    if current_chunk:
        chunks.append({'text': current_chunk[-1], 'pdf_pages': current_pages})
    
    # Remove empty chunks
    chunks = [chunk for chunk in chunks if chunk['text']]
    
    return chunks