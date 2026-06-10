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
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line and line not in repeated_noise_candidates:
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    def split_into_paragraphs(text: str) -> List[str]:
        return [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    chunks = []
    for page in pages:
        pdf_page = page['pdf_page']
        text = clean_text(page['text'])
        paragraphs = split_into_paragraphs(text)

        for paragraph in paragraphs:
            if paragraph:
                chunks.append({
                    "text": paragraph,
                    "pdf_pages": [pdf_page]
                })

    # Merge short headings with the following paragraph
    for i in range(len(chunks) - 1):
        if len(chunks[i]['text']) < 10 and re.match(r'^[^\n]+$', chunks[i]['text']):
            chunks[i]['text'] += "\n" + chunks[i + 1]['text']
            chunks[i]['pdf_pages'].extend(chunks[i + 1]['pdf_pages'])
            del chunks[i + 1]

    # Remove empty chunks
    chunks = [chunk for chunk in chunks if chunk['text']]

    return chunks