"""Test parsing: parse sample files and output full structured result (dict/JSON) to console.

Run from project root:
  python scripts/test_parsing.py
  python scripts/test_parsing.py --path ingestion/sample_files/pdf/sample.pdf
  python scripts/test_parsing.py --ocr
"""

import argparse
import json
import sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion import (  # noqa: E402
    IngestionConfig,
    get_input_handler,
    parse_and_prepare,
)
from ingestion.ocr import TesseractOCRProvider  # noqa: E402

SAMPLE_FILES_DIR = PROJECT_ROOT / "ingestion" / "sample_files"

# Max character length per block content in output (0 = no truncation)
TRUNCATE_BLOCK_CONTENT = 400


def collect_sample_files() -> list[Path]:
    exts = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".py", ".txt", ".md"}
    files = [
        p
        for p in SAMPLE_FILES_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in exts
    ]
    return sorted(files)


def structure_for_output(doc_dict: dict) -> dict:
    """Optionally truncate block content for readable console output."""
    if TRUNCATE_BLOCK_CONTENT <= 0:
        return doc_dict
    out = dict(doc_dict)
    blocks = out.get("blocks") or []
    for b in blocks:
        c = b.get("content") or ""
        if len(c) > TRUNCATE_BLOCK_CONTENT:
            b["content"] = c[:TRUNCATE_BLOCK_CONTENT]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test ingestion parsing; output structure (dict/JSON) per file"
    )
    parser.add_argument(
        "--ocr", action="store_true", help="Enable OCR (requires pytesseract)"
    )
    parser.add_argument("--path", type=str, help="Single file path")
    parser.add_argument(
        "--no-truncate", action="store_true", help="Do not truncate block content"
    )
    args = parser.parse_args()

    global TRUNCATE_BLOCK_CONTENT
    if args.no_truncate:
        TRUNCATE_BLOCK_CONTENT = 0

    config = IngestionConfig(ocr_enabled=args.ocr)
    ocr_provider = None
    if args.ocr:
        try:
            ocr_provider = TesseractOCRProvider()
        except ImportError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    if args.path:
        path = Path(args.path).resolve()
        if not path.exists():
            print(f"File not found: {args.path}", file=sys.stderr)
            return 1
        paths = [path]
    else:
        paths = collect_sample_files()
        if not paths:
            print("No sample files in ingestion/sample_files/", file=sys.stderr)
            return 1

    for path in paths:
        try:
            handler = get_input_handler(path)
            doc = parse_and_prepare(
                handler,
                path,
                ocr_provider=ocr_provider,
                config=config,
                base_path=PROJECT_ROOT,
            )
            doc_dict = doc.to_dict()
            out = structure_for_output(doc_dict)
            print("\n" + "=" * 80)
            try:
                file_label = path.relative_to(PROJECT_ROOT)
            except ValueError:
                file_label = path
            print(f"FILE: {file_label}")
            print("=" * 80)
            print(json.dumps(out, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"ERROR {path}: {e}", file=sys.stderr)
            raise
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
