from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_QUESTION = "脾胃在中醫理論中負責哪些功能？"


def display_markdown(markdown: str) -> None:
    try:
        from IPython import get_ipython
    except ImportError:
        ipython_shell = None
    else:
        ipython_shell = get_ipython()

    if ipython_shell is not None:
        from IPython.display import Markdown, display

        display(Markdown(markdown))
        return

    try:
        from rich.console import Console
        from rich.markdown import Markdown
    except ImportError:
        sys.stdout.write(markdown + "\n")
        return

    Console().print(Markdown(markdown))


def format_json_block(value) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    return f"```json\n{text}\n```"


def format_result_markdown(question: str, result: dict) -> str:
    return "\n\n".join([
        "# TCM RAG Smoke Test",
        "## Question",
        question,
        "## Answer",
        result["answer"],
        "## Retrieval Scores",
        format_json_block(result["scores"]),
        "## Sources",
        format_json_block(result.get("sources", [])),
    ])


def load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(PROJECT_ROOT / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test the TCM RAG pipeline without starting Streamlit.",
    )
    parser.add_argument(
        "question",
        nargs="?",
        default=DEFAULT_QUESTION,
        help="Question to send to ask_tcm().",
    )
    args = parser.parse_args()

    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    load_environment()

    if not os.getenv("OPENAI_API_KEY"):
        display_markdown(
            "**OPENAI_API_KEY is not set.** Add it to `.env` or export it first."
        )
        return 1

    from tcmagent.rag import ask_tcm

    question = args.question.strip()
    result = ask_tcm(question)
    display_markdown(format_result_markdown(question, result))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
