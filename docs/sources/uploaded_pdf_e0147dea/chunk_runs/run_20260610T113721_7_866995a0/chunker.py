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
        return re.split(r'\n\s*\n', text.strip())

    chunks = []
    current_paragraph = ""
    current_pages = []

    for page in pages:
        pdf_page = page['pdf_page']
        text = clean_text(page['text'])
        paragraphs = split_into_paragraphs(text)

        for paragraph in paragraphs:
            if paragraph:
                if current_paragraph:
                    # Check if the current paragraph is a heading and the next is a paragraph
                    if len(current_paragraph) < 50 and not re.search(r'\n', current_paragraph):
                        current_paragraph += "\n" + paragraph
                    else:
                        chunks.append({"text": current_paragraph, "pdf_pages": current_pages})
                        current_paragraph = paragraph
                        current_pages = [pdf_page]
                else:
                    current_paragraph = paragraph
                    current_pages = [pdf_page]

        if current_paragraph:
            chunks.append({"text": current_paragraph, "pdf_pages": current_pages})
            current_paragraph = ""
            current_pages = []

    # Filter out empty chunks and ensure no chunk is just noise
    final_chunks = [chunk for chunk in chunks if chunk['text'].strip()]

    return final_chunks