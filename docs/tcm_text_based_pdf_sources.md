# 中醫 Text-Based PDF Sources

Checked on 2026-06-09 with `pdfinfo` and `pdftotext -f 1 -l 5`. `chars_first5` is the number of characters extracted from the first five pages; nonzero/high values indicate the PDF has a usable text layer rather than being image-only.

## Best first sources for TCMagent

| Priority | Source | Direct PDF | Why use it first |
| --- | --- | --- | --- |
| 1 | WHO international standard terminologies on traditional Chinese medicine | https://iris.who.int/server/api/core/bitstreams/02be07cf-ef55-4ae2-9184-ded49210aa05/content | Strong controlled vocabulary for terms, synonyms, and citation-grounded definitions. |
| 2 | WHO international standard terminologies on traditional medicine in the Western Pacific Region | https://iris.who.int/server/api/core/bitstreams/24400634-2d52-4dde-bbb1-d28ee2c6fd42/content | Older but broad bilingual terminology reference; useful for fallback term matching. |
| 3 | 中藥常用方劑效能、適應症語意解析及英譯彙編 | https://www.mohw.gov.tw/dl-69997-92bcd2d5-5987-48d1-a15e-ffb2185fb1e7.html | Taiwan MOHW formula/indication wording; useful for formula search and Chinese-English mapping. |
| 4 | 針灸實證臨床治療指引 | https://www.mohw.gov.tw/dl-99494-bfb3dac9-4bf1-4848-82a7-4c0cac7611c0.html | Evidence-based acupuncture guideline in Traditional Chinese; good for clinical question retrieval with citations. |
| 5 | 中醫傷科實證臨床治療指引 | https://www.mohw.gov.tw/dl-99495-e624b6af-2224-4588-bbe8-96e70a02f7f0.html | Evidence-based traumatology/orthopedics guideline in Traditional Chinese. |
| 6 | WHO Benchmarks for training in traditional Chinese medicine | https://iris.who.int/server/api/core/bitstreams/4585ae8f-6bf7-4aeb-924a-942f4e9eee77/content | Concise overview of TCM origins, principles, training, dispensers, and safety. |

## Verified downloadable text PDFs

| Title | Publisher / source page | Language | Pages checked | chars_first5 | Notes |
| --- | --- | --- | ---: | ---: | --- |
| WHO international standard terminologies on traditional Chinese medicine | https://www.who.int/publications/i/item/9789240042322 | English + Chinese terms | 468 | 4789 | Best terminology source. Use for term normalization before retrieval. |
| WHO international standard terminologies on traditional medicine in the Western Pacific Region | https://iris.who.int/handle/10665/206952 | English + Chinese/Japanese/Korean terms | 366 | 2711 | Older terminology standard. Useful for cross-checking variants. |
| Benchmarks for training in traditional Chinese medicine | https://iris.who.int/handle/10665/44353 | English | 43 | 4908 | WHO training/safety benchmark; concise and clean text layer. |
| WHO benchmarks for the training of acupuncture | https://www.who.int/publications/i/item/9789240017962 | English | 28 | 4396 | Good acupuncture training/scope source. |
| Benchmarks for training in tuina | https://www.who.int/publications/i/item/9789241599689 | English | 36 | 4044 | Good tuina training/scope source. |
| Medicinal plants in China: a selection of 150 commonly used species | https://www.who.int/publications/i/item/9290611022 | English | 339 | 6004 | Large 79.9 MB PDF; useful for materia medica/herbal entries. |
| 中藥常用方劑效能、適應症語意解析及英譯彙編 | https://dep.mohw.gov.tw/DOCMAP/np-5207-108.html | Traditional Chinese + English | 99 | 5573 | Taiwan MOHW formula reference. Strong for formula names and approved wording. |
| 針灸實證臨床治療指引 | https://dep.mohw.gov.tw/DOCMAP/cp-6488-85760-108.html | Traditional Chinese | 104 | 4025 | Evidence-based guideline; source page lists both guideline PDFs. |
| 中醫傷科實證臨床治療指引 | https://dep.mohw.gov.tw/DOCMAP/cp-6488-85760-108.html | Traditional Chinese | 178 | 2660 | Evidence-based guideline; source page lists both guideline PDFs. |
| Recent Advances in Theories and Practice of Chinese Medicine | https://www.intechopen.com/books/643 | English | 510 | 3857 | Open-access edited volume; broad research-oriented chapters. |
| Routledge Handbook of Chinese Medicine | https://pure.mpg.de/pubman/faces/ViewItemFullPage.jsp?itemId=item_3332340_7 | English | 797 | 4719 | Open-access Routledge handbook; historical/anthropological, less clinical. Direct PDF: https://pure.mpg.de/pubman/item/item_3332340_7/component/file_3527809/9780203740262_webpdf.pdf |

## Bonus non-PDF text corpus

| Source | URL | Why it matters |
| --- | --- | --- |
| 中醫藥典籍全文下載 | https://dep.mohw.gov.tw/DOCMAP/lp-830-108.html | Not PDF, but likely better than PDF for RAG because it provides downloadable full-text classic TCM material. Use this separately from PDF ingestion. |

## Import notes

- Start with the first six sources before adding large open-access handbooks. The terminology and guideline PDFs are cleaner for a citation RAG workflow than broad historical chapters.
- For WHO pages, use the direct `server/api/core/bitstreams/.../content` PDF URLs above. Some old `iris.who.int/bitstream/handle/...pdf` links return the DSpace HTML shell to command-line downloaders.
- Re-run `pdftotext` over a page sample before indexing the whole PDF. The WHO `Medicinal plants in China` file is large and should be chunked/tested separately.
- Do not treat these sources as permission to generate diagnosis or treatment plans. They are suitable for retrieval-grounded answers with citations and conservative medical safety wording.
