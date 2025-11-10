#!/usr/bin/env python3
"""
PDF → PNG converter for bubble sheet workflows.

Takes individual PDFs or entire folders/zip archives of PDFs and renders each
page to a PNG image (default 300 DPI) so scan_bubblesheet.py can consume them.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path
from typing import Iterator, List, Tuple

from pdf2image import convert_from_bytes, convert_from_path

PDF_EXTENSIONS = {".pdf"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert PDF bubble sheets into PNG images.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf", help="Path to a single PDF file.")
    group.add_argument("--folder", help="Path to a folder or .zip containing PDFs.")
    parser.add_argument(
        "--output-dir",
        default="output/png",
        help="Destination directory for PNG files (created if missing).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Render DPI (higher = larger images).",
    )
    parser.add_argument(
        "--fmt",
        default="png",
        choices=["png", "jpg", "jpeg"],
        help="Output image format.",
    )
    parser.add_argument(
        "--prefix",
        help="Optional filename prefix; defaults to PDF stem name.",
    )
    return parser.parse_args()


def iter_pdf_sources(pdf_path: Path | None, folder_path: Path | None) -> Iterator[Tuple[str, bytes | Path]]:
    if pdf_path:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        yield pdf_path.name, pdf_path
        return

    assert folder_path is not None
    if folder_path.is_file() and folder_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(folder_path) as zf:
            for info in zf.infolist():
                if info.is_dir() or Path(info.filename).suffix.lower() not in PDF_EXTENSIONS:
                    continue
                yield info.filename, zf.read(info.filename)
    else:
        if not folder_path.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")
        for pdf in sorted(folder_path.rglob("*.pdf")):
            if pdf.is_file():
                yield str(pdf.relative_to(folder_path)), pdf


def render_pdf_to_images(source: bytes | Path, dpi: int) -> List:
    if isinstance(source, Path):
        return convert_from_path(str(source), dpi=dpi)
    return convert_from_bytes(source, dpi=dpi)


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = Path(args.pdf) if args.pdf else None
    folder_path = Path(args.folder) if args.folder else None

    total_pages = 0
    for name, source in iter_pdf_sources(pdf_path, folder_path):
        prefix = args.prefix or Path(name).stem.replace(" ", "_")
        try:
            images = render_pdf_to_images(source, args.dpi)
        except Exception as exc:  # noqa: BLE001
            print(f"Skipping {name}: {exc}")
            continue
        for page_index, image in enumerate(images, start=1):
            suffix = f"{prefix}_page{page_index:02d}.{args.fmt}"
            dest = output_dir / suffix
            image.save(dest, args.fmt.upper())
            total_pages += 1
            print(f"Saved {dest}")

    if total_pages == 0:
        raise RuntimeError("No PDF pages were converted. Check your inputs.")
    print(f"Converted {total_pages} page(s).")


if __name__ == "__main__":
    main()
