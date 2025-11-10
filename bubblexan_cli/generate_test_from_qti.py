#!/usr/bin/env python3
"""
Canvas QTI → Printable Test + Answer Key generator.

Given a Canvas quiz QTI export plus assessment metadata, emit:
  1. A CSV answer key compatible with scan_bubblesheet.py outputs.
  2. A printable PDF of the questions (intended for use with a separate bubble sheet).
"""

from __future__ import annotations

import argparse
import csv
import re
import tempfile
import zipfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import pagesizes
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer
import xml.etree.ElementTree as ET

DEFAULT_PAGE_SIZE = pagesizes.LETTER
QTI_URI = "http://www.imsglobal.org/xsd/ims_qtiasiv1p2"


def qti_tag(tag: str) -> str:
    return f"{{{QTI_URI}}}{tag}"


@dataclass
class Option:
    letter: str
    ident: str
    text: str


@dataclass
class Question:
    number: int
    text: str
    options: List[Option]
    correct_letters: List[str]
    points: float
    multi_select: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an answer key CSV and printable PDF from Canvas QTI exports.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--qti", help="Path to the Canvas QTI XML file (optional when --zip is provided).")
    parser.add_argument(
        "--meta",
        help="Path to assessment_meta.xml (optional when --zip is provided).",
    )
    parser.add_argument(
        "--manifest",
        help="Optional imsmanifest.xml for validation (currently informative only).",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory where the PDF and CSV will be written.",
    )
    parser.add_argument(
        "--output-prefix",
        default="generated_test",
        help="Filename prefix for generated files (e.g., <prefix>_test.pdf).",
    )
    parser.add_argument(
        "--page-size",
        choices=["LETTER", "A4"],
        default="LETTER",
        help="PDF page size.",
    )
    parser.add_argument(
        "--zip",
        help="Optional Canvas QTI export .zip. When supplied, files are auto-detected unless explicitly overridden.",
    )
    return parser.parse_args()


def resolve_input_path(path_arg: Optional[str], base_dir: Optional[Path]) -> Optional[Path]:
    if not path_arg:
        return None
    candidate = Path(path_arg).expanduser()
    if candidate.exists():
        return candidate
    if base_dir is not None:
        inner = (base_dir / path_arg).resolve()
        if inner.exists():
            return inner
    return candidate


def detect_qti_file(base_dir: Path) -> Optional[Path]:
    xml_files = list(base_dir.rglob("*.xml"))
    candidates = [p for p in xml_files if p.name not in {"imsmanifest.xml", "assessment_meta.xml"}]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    for candidate in candidates:
        if candidate.parent.name == candidate.stem:
            return candidate
    return max(candidates, key=lambda p: p.stat().st_size)


def detect_single_file(base_dir: Path, filename: str) -> Optional[Path]:
    return next((p for p in base_dir.rglob(filename)), None)


def strip_html(value: str) -> str:
    text = unescape(value or "")
    text = re.sub(r"(?i)<\s*(br|/p)\s*>", "\n", text)
    text = re.sub(r"(?i)<\s*p[^>]*>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_text(nodes: Sequence[etree._Element]) -> str:
    parts = [strip_html("".join(node.itertext())) for node in nodes]
    combined = " ".join(part for part in parts if part)
    return combined.strip()


def parse_qti_questions(qti_path: Path) -> List[Question]:
    tree = ET.parse(str(qti_path))
    root = tree.getroot()
    items = root.findall(f".//{qti_tag('item')}")
    questions: List[Question] = []
    for index, item in enumerate(items, start=1):
        text_nodes = item.findall(f".//{qti_tag('presentation')}/{qti_tag('material')}/{qti_tag('mattext')}")
        question_text = extract_text(text_nodes)
        response_lid = item.find(f".//{qti_tag('presentation')}/{qti_tag('response_lid')}")
        if response_lid is None:
            continue
        rcardinality = (response_lid.get("rcardinality") or "Single").lower()
        option_nodes = response_lid.findall(f".//{qti_tag('response_label')}")
        options: List[Option] = []
        letter_ord = ord("a")
        for resp in option_nodes:
            ident = resp.get("ident", "")
            mattext_nodes = resp.findall(f".//{qti_tag('mattext')}")
            option_text = extract_text(mattext_nodes)
            options.append(Option(letter=chr(letter_ord), ident=ident, text=option_text))
            letter_ord += 1
        correct_idents = collect_correct_idents(item)
        correct_letters = [opt.letter for opt in options if opt.ident in correct_idents]
        points = extract_points(item)
        multi_select = rcardinality == "multiple" or len(correct_letters) > 1
        questions.append(
            Question(
                number=index,
                text=question_text,
                options=options,
                correct_letters=correct_letters,
                points=points,
                multi_select=multi_select,
            )
        )
    return questions


def collect_correct_idents(item: ET.Element) -> List[str]:
    required: Dict[str, bool] = {}

    def traverse(node: ET.Element, negated: bool = False) -> None:
        tag = node.tag
        if tag == qti_tag("not"):
            for child in list(node):
                traverse(child, not negated)
            return
        if tag == qti_tag("varequal"):
            if node.text:
                ident = node.text.strip()
                if ident:
                    required[ident] = not negated
            return
        for child in list(node):
            traverse(child, negated)

    for resprocessing in item.findall(f".//{qti_tag('resprocessing')}"):
        for condition in resprocessing.findall(f".//{qti_tag('conditionvar')}"):
            traverse(condition, False)

    return [ident for ident, is_required in required.items() if is_required]


def extract_points(item: ET.Element) -> float:
    meta_fields = item.findall(f".//{qti_tag('itemmetadata')}//{qti_tag('qtimetadatafield')}")
    for field in meta_fields:
        label = field.findtext(qti_tag("fieldlabel"))
        if label and label.strip() == "points_possible":
            entry = field.findtext(qti_tag("fieldentry"))
            if entry:
                try:
                    return float(entry.strip())
                except ValueError:
                    pass
    return 1.0


def load_metadata(meta_path: Path) -> Tuple[str, Optional[float]]:
    tree = ET.parse(str(meta_path))
    root = tree.getroot()
    ns = root.tag[root.tag.find("{") + 1 : root.tag.find("}")] if "}" in root.tag else ""

    def meta_findtext(tag: str) -> str:
        if ns:
            return (root.findtext(f".//{{{ns}}}{tag}") or "").strip()
        return (root.findtext(f".//{tag}") or "").strip()

    title = meta_findtext("title") or "Untitled Quiz"
    points_text = meta_findtext("points_possible")
    total_points = None
    if points_text:
        try:
            total_points = float(points_text)
        except ValueError:
            total_points = None
    return title, total_points


def write_answer_key(path: Path, questions: Sequence[Question]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["Question", "Correct_Answer", "Points"])
        for question in questions:
            correct_value = ",".join(question.correct_letters)
            writer.writerow([f"Q{question.number}", correct_value, f"{question.points:.2f}"])


def build_pdf(
    path: Path,
    title: str,
    questions: Sequence[Question],
    page_size: Tuple[float, float],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    question_style = ParagraphStyle(
        "Question",
        parent=styles["BodyText"],
        fontSize=11,
        leading=14,
        spaceAfter=6,
    )
    option_style = ParagraphStyle(
        "Option",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=13,
        leftIndent=18,
        spaceAfter=2,
    )
    note_style = ParagraphStyle(
        "Note",
        parent=styles["Italic"],
        fontSize=10,
        leftIndent=12,
        spaceAfter=4,
    )

    extra_header_padding = 0.4 * inch
    doc = SimpleDocTemplate(
        str(path),
        pagesize=page_size,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch + extra_header_padding,
        bottomMargin=inch,
        title=title,
    )

    story: List = []
    story.append(Paragraph(xml_escape(title), styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Name: ________________________________", styles["Normal"]))
    story.append(Paragraph("Date: ________________________________", styles["Normal"]))
    story.append(Spacer(1, 18))

    for question in questions:
        question_text = xml_escape(question.text or "").replace("\n", "<br/>")
        block: List = []
        block.append(Paragraph(f"{question.number}. {question_text}", question_style))
        if question.multi_select and "select all that apply" not in (question.text or "").lower():
            block.append(Paragraph("Select all that apply.", note_style))
        for option in question.options:
            option_text = xml_escape(option.text or "").replace("\n", "<br/>")
            block.append(Paragraph(f"{option.letter}) {option_text}", option_style))
        block.append(Spacer(1, 12))
        story.append(KeepTogether(block))

    def add_header(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.drawString(doc.leftMargin, doc.height + doc.topMargin - 10, title)
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, doc.height + doc.topMargin - 10, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_header, onLaterPages=add_header)


def validate_points(total_expected: Optional[float], questions: Sequence[Question]) -> Optional[str]:
    if total_expected is None:
        return None
    total_actual = sum(q.points for q in questions)
    if abs(total_actual - total_expected) > 0.01:
        return f"Warning: total points from QTI ({total_actual:.2f}) do not match assessment metadata ({total_expected:.2f})."
    return None


def maybe_print_manifest_info(manifest_path: Optional[Path]) -> None:
    if not manifest_path:
        return
    try:
        tree = ET.parse(str(manifest_path))
        root = tree.getroot()
        resources = root.findall(".//resource")
        if resources:
            print(f"Loaded imsmanifest with {len(resources)} resource reference(s).")
    except Exception as exc:  # noqa: BLE001
        print(f"Note: unable to parse imsmanifest ({exc}).")


def main() -> None:
    args = parse_args()
    temp_dir: Optional[tempfile.TemporaryDirectory] = None
    base_dir: Optional[Path] = None

    try:
        if args.zip:
            temp_dir = tempfile.TemporaryDirectory()
            base_dir = Path(temp_dir.name)
            with zipfile.ZipFile(Path(args.zip).expanduser()) as zf:
                zf.extractall(base_dir)

        qti_path = resolve_input_path(args.qti, base_dir)
        meta_path = resolve_input_path(args.meta, base_dir)
        manifest_path = resolve_input_path(args.manifest, base_dir) if args.manifest else None

        if base_dir and (qti_path is None or not Path(qti_path).exists()):
            qti_detected = detect_qti_file(base_dir)
            if not qti_detected:
                raise FileNotFoundError("Could not auto-detect the QTI XML inside the provided zip.")
            print(f"Detected QTI file: {qti_detected}")
            qti_path = qti_detected
        if base_dir and (meta_path is None or not Path(meta_path).exists()):
            meta_detected = detect_single_file(base_dir, "assessment_meta.xml")
            if not meta_detected:
                raise FileNotFoundError("Could not find assessment_meta.xml inside the provided zip.")
            print(f"Detected assessment metadata: {meta_detected}")
            meta_path = meta_detected
        if base_dir and manifest_path is None:
            manifest_detected = detect_single_file(base_dir, "imsmanifest.xml")
            if manifest_detected:
                print(f"Detected imsmanifest: {manifest_detected}")
                manifest_path = manifest_detected

        if qti_path is None:
            raise FileNotFoundError("Missing --qti argument and unable to detect QTI file.")
        if meta_path is None:
            raise FileNotFoundError("Missing --meta argument and unable to detect assessment metadata file.")

        qti_path = Path(qti_path)
        if not qti_path.exists():
            raise FileNotFoundError(f"QTI file not found: {qti_path}")
        meta_path = Path(meta_path)
        if not meta_path.exists():
            raise FileNotFoundError(f"Assessment metadata file not found: {meta_path}")
        manifest_path = Path(manifest_path) if manifest_path else None
        if manifest_path and not manifest_path.exists():
            raise FileNotFoundError(f"imsmanifest file not found: {manifest_path}")

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        page_size = pagesizes.LETTER if args.page_size == "LETTER" else pagesizes.A4

        questions = parse_qti_questions(qti_path)
        if not questions:
            raise RuntimeError("No questions were parsed from the provided QTI file.")
        title, total_points_expected = load_metadata(meta_path)
        warning = validate_points(total_points_expected, questions)
        maybe_print_manifest_info(manifest_path)

        prefix = Path(args.output_prefix).name
        answer_key_path = output_dir / f"{prefix}_answer_key.csv"
        pdf_path = output_dir / f"{prefix}_test.pdf"

        write_answer_key(answer_key_path, questions)
        build_pdf(pdf_path, title, questions, page_size)

        if warning:
            print(warning)
        print(f"Wrote {answer_key_path}")
        print(f"Wrote {pdf_path}")
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


if __name__ == "__main__":
    main()
