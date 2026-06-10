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

    def clean_text(text: str) -> str:
        lines = text.splitlines()
        cleaned_lines = [line.strip() for line in lines if line.strip() and line.strip() not in repeated_noise_candidates]
        return "\n".join(cleaned_lines)

    def split_into_paragraphs(text: str) -> List[str]:
        return [para.strip() for para in re.split(r'\n{2,}', text) if para.strip()]

    chunks = []
    current_chunk = []
    current_pages = []

    for page in pages:
        pdf_page = page['pdf_page']
        text = clean_text(page['text'])
        paragraphs = split_into_paragraphs(text)

        for paragraph in paragraphs:
            if paragraph:
                if len(current_chunk) == 0:
                    current_chunk.append(paragraph)
                    current_pages.append(pdf_page)
                else:
                    # Check if the current paragraph is a heading and the previous one is short
                    if len(current_chunk[-1]) < 10 and re.match(r'^[^\n]+$', current_chunk[-1]):
                        current_chunk[-1] += "\n" + paragraph
                    else:
                        chunks.append({"text": "\n".join(current_chunk), "pdf_pages": current_pages})
                        current_chunk = [paragraph]
                        current_pages = [pdf_page]

    if current_chunk:
        chunks.append({"text": "\n".join(current_chunk), "pdf_pages": current_pages})

    # Filter out empty chunks
    return [chunk for chunk in chunks if chunk['text']]