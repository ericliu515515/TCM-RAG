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

    def clean_text(text: str) -> str:
        lines = text.splitlines()
        cleaned_lines = [line.strip() for line in lines if line.strip() and line.strip() not in repeated_noise_candidates]
        return "\n".join(cleaned_lines)

    def split_into_paragraphs(text: str) -> List[str]:
        return [para.strip() for para in re.split(r'\n\s*\n', text) if para.strip()]

    chunks = []
    current_paragraph = ""
    current_pages = []

    for page in pages:
        pdf_page = page['pdf_page']
        text = clean_text(page['text'])
        paragraphs = split_into_paragraphs(text)

        for para in paragraphs:
            if current_paragraph:
                if len(current_paragraph) + len(para) + 1 <= 1000:  # Assuming a max chunk size
                    current_paragraph += "\n" + para
                    current_pages.append(pdf_page)
                else:
                    if current_paragraph:
                        chunks.append({"text": current_paragraph, "pdf_pages": current_pages})
                    current_paragraph = para
                    current_pages = [pdf_page]
            else:
                current_paragraph = para
                current_pages = [pdf_page]

    if current_paragraph:
        chunks.append({"text": current_paragraph, "pdf_pages": current_pages})

    # Filter out empty chunks and those that are only noise
    chunks = [chunk for chunk in chunks if chunk['text'] and len(chunk['text']) > 10]

    return chunks