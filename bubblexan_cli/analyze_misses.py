#!/usr/bin/env python3
"""
Question Miss Analyzer

Processes the CSV emitted by scan_bubblesheet.py plus an answer-key CSV and
reports how many students missed each question (including partial-credit stats
for select-all style prompts).
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict, OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

VALID_OPTIONS = {"A", "B", "C", "D", "E"}


@dataclass(frozen=True)
class AnswerSpec:
    question_label: str  # Display label, e.g., Q1
    column_name: str  # Column in results CSV
    correct_options: Set[str]
    answer_display: str  # String to echo in the report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze bubble-sheet results and report per-question miss percentages.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--results", required=True, help="CSV produced by scan_bubblesheet.py.")
    parser.add_argument("--key", required=True, help="Answer-key CSV with Question/Answer columns.")
    parser.add_argument("--output", required=True, help="Destination CSV for the miss report.")
    parser.add_argument(
        "--miss-threshold",
        type=float,
        default=50.0,
        help="Percent threshold for flagging high-miss questions in console output.",
    )
    parser.add_argument(
        "--partial-threshold",
        type=float,
        default=1.0,
        help="Minimum ratio of correct options selected (0-1] for multi-answer questions "
        "to count as correct.",
    )
    parser.add_argument("--log", help="Optional log file for warnings (invalid answers, etc.).")
    return parser.parse_args()


def read_csv_rows(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if reader.fieldnames is None:
            raise ValueError(f"{path} is missing a header row.")
        rows: List[Dict[str, str]] = []
        for row in reader:
            if row is None:
                continue
            if None in row and row[None]:
                last_field = reader.fieldnames[-1]
                base = (row.get(last_field) or "").strip()
                extra_values = [str(item).strip() for item in row[None] if item]
                combined_parts = [part for part in [base, ",".join(extra_values)] if part]
                row[last_field] = ",".join(combined_parts) if combined_parts else ""
                row.pop(None)
            cleaned: Dict[str, str] = {}
            for key, value in row.items():
                if key is None:
                    continue
                if value is None:
                    text = ""
                elif isinstance(value, list):
                    text = ",".join(value)
                else:
                    text = str(value)
                cleaned[str(key)] = text.strip()
            if not any(cleaned.values()):
                continue
            rows.append(cleaned)
        if not rows:
            raise ValueError(f"{path} has no data rows.")
        return rows, reader.fieldnames


def build_column_lookup(fieldnames: Sequence[str]) -> Dict[str, str]:
    return {name.lower(): name for name in fieldnames}


def normalize_question_label(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    if text.lower().startswith("q") and len(text) > 1:
        suffix = text[1:].strip()
    else:
        suffix = text
    suffix = suffix or text
    return f"Q{suffix}"


def convert_results_to_wide(
    rows: List[Dict[str, str]],
    fieldnames: Sequence[str],
) -> Tuple[List[Dict[str, str]], List[str]]:
    lookup = build_column_lookup(fieldnames)
    question_col = lookup.get("question_id")
    answer_col = lookup.get("selected_answers")
    student_col = lookup.get("student_id")

    if not question_col or not answer_col:
        return rows, list(fieldnames)

    students: "OrderedDict[str, Dict[str, str]]" = OrderedDict()
    question_order: List[str] = []
    seen_questions: Set[str] = set()

    for idx, row in enumerate(rows, start=1):
        student_id = (row.get(student_col, "").strip() if student_col else "").strip()
        if not student_id:
            student_id = f"row_{idx}"
        container = students.setdefault(student_id, {"Student_ID": student_id})

        question_raw = row.get(question_col, "").strip()
        if not question_raw:
            continue
        label = normalize_question_label(question_raw)
        if not label:
            continue
        if label not in seen_questions:
            seen_questions.add(label)
            question_order.append(label)

        container[label] = row.get(answer_col, "").strip()

    wide_rows = list(students.values())
    wide_fields = ["Student_ID"] + question_order
    return wide_rows, wide_fields if question_order else list(fieldnames)


def resolve_question_column(label: str, column_lookup: Dict[str, str]) -> Tuple[str, str]:
    raw = label.strip()
    if not raw:
        raise ValueError("Encountered a blank question label in the answer key.")
    suffix = raw[1:].strip() if raw.lower().startswith("q") else raw
    display = f"Q{suffix or raw}"
    candidates = {raw, raw.lower(), raw.upper(), suffix, suffix.lower(), suffix.upper(), display, display.lower(), display.upper()}
    for candidate in candidates:
        if not candidate:
            continue
        actual = column_lookup.get(candidate.lower())
        if actual:
            return display, actual
    raise ValueError(f"Question '{raw}' not found in results CSV columns ({', '.join(column_lookup.values())}).")


def parse_answer_value(value: str) -> Set[str]:
    tokens = tokenize_options(value)
    if not tokens:
        raise ValueError("Answer entry is empty.")
    invalid = [token for token in tokens if token not in VALID_OPTIONS]
    if invalid:
        raise ValueError(f"Answer contains invalid option(s): {', '.join(invalid)}")
    return set(tokens)


def tokenize_options(value: str) -> List[str]:
    text = (value or "").strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    text = text.replace(";", ",")
    parts = [part.strip().upper() for part in re.split(r"[,\s]+", text) if part.strip()]
    return parts


def _get_field(row: Dict[str, str], *candidates: str) -> str:
    lowered = {key.lower(): value for key, value in row.items()}
    for candidate in candidates:
        value = lowered.get(candidate.lower())
        if value is not None:
            return value
    return ""


def load_answer_key(key_path: Path, column_lookup: Dict[str, str]) -> List[AnswerSpec]:
    rows, _ = read_csv_rows(key_path)
    specs: List[AnswerSpec] = []
    seen_questions: Set[str] = set()
    for row in rows:
        question_label = _get_field(row, "Question").strip()
        answer_value = _get_field(row, "Correct_Answer", "Correct Answer", "Answer").strip()
        if not question_label or not answer_value:
            raise ValueError("Each answer-key row must include Question and Correct_Answer values.")
        display_label, column_name = resolve_question_column(question_label, column_lookup)
        if display_label in seen_questions:
            raise ValueError(f"Duplicate question '{display_label}' in answer key.")
        correct_set = parse_answer_value(answer_value)
        if not correct_set:
            raise ValueError(f"Question '{display_label}' has no valid answers.")
        answer_display = answer_value if answer_value.startswith("[") else (
            f"[{','.join(sorted(correct_set))}]" if len(correct_set) > 1 else next(iter(correct_set))
        )
        specs.append(AnswerSpec(display_label, column_name, correct_set, answer_display))
        seen_questions.add(display_label)
    return specs


def parse_student_response(raw: str) -> Tuple[Set[str], Optional[str]]:
    tokens = tokenize_options(raw)
    if not tokens:
        return set(), None
    invalid = [token for token in tokens if token not in VALID_OPTIONS]
    if invalid:
        return set(), f"Invalid option(s): {', '.join(sorted(set(invalid)))}"
    return set(tokens), None


def format_partial_notes(total_correct: int, partial_counts: Dict[int, int]) -> str:
    if total_correct <= 1 or not partial_counts:
        return ""
    parts: List[str] = []
    for hits in sorted(partial_counts.keys(), reverse=True):
        count = partial_counts[hits]
        fraction = f"{hits}/{total_correct}"
        label = "student" if count == 1 else "students"
        parts.append(f"{count} {label} selected {fraction} correct")
    return ", ".join(parts)


def analyze_question(
    spec: AnswerSpec,
    results: List[Dict[str, str]],
    partial_threshold: float,
    log_entries: List[str],
) -> Tuple[int, Dict[int, int]]:
    total_correct = len(spec.correct_options)
    partial_counts: Dict[int, int] = defaultdict(int)
    missed = 0
    column = spec.column_name
    for idx, row in enumerate(results, start=1):
        student_id = row.get("Student_ID", "").strip() or f"row {idx}"
        response_raw = row.get(column, "")
        selected, parse_warning = parse_student_response(response_raw)
        if parse_warning:
            log_entries.append(f"{spec.question_label} / {student_id}: {parse_warning}")
            missed += 1
            continue
        if not selected:
            missed += 1
            continue
        if len(spec.correct_options) == 1:
            if selected == spec.correct_options:
                continue
            if len(selected) > 1:
                log_entries.append(f"{spec.question_label} / {student_id}: multiple marks for single-choice question.")
            missed += 1
            continue

        extra = selected - spec.correct_options
        hits = len(selected & spec.correct_options)
        if extra:
            log_entries.append(
                f"{spec.question_label} / {student_id}: selected incorrect option(s) {', '.join(sorted(extra))}."
            )
            missed += 1
            continue
        if hits == 0:
            missed += 1
            continue

        if 0 < hits < total_correct:
            partial_counts[hits] += 1
        ratio = hits / total_correct
        if ratio + 1e-9 < partial_threshold:
            missed += 1
    return missed, partial_counts


def write_report(
    path: Path,
    rows: Sequence[Tuple[str, float, int, int, str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(
            ["Question", "Percent_Missed", "Missed_Count", "Total_Students", "Correct_Answer", "Partial_Credit_Notes"]
        )
        for row in rows:
            writer.writerow(row)


def write_log(path: Path, entries: Iterable[str]) -> None:
    data = list(entries)
    if not data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for entry in data:
            fp.write(entry + "\n")


def main() -> None:
    args = parse_args()
    if not (0.0 < args.partial_threshold <= 1.0):
        raise ValueError("partial-threshold must be between 0 and 1.")
    if args.miss_threshold < 0.0:
        raise ValueError("miss-threshold cannot be negative.")

    results_path = Path(args.results)
    key_path = Path(args.key)
    output_path = Path(args.output)
    rows, fieldnames = read_csv_rows(results_path)
    rows, fieldnames = convert_results_to_wide(rows, fieldnames)
    if not any((name or "").strip().lower() == "student_id" for name in fieldnames):
        raise ValueError("Results CSV must include a 'Student_ID' column.")

    column_lookup = build_column_lookup(fieldnames)
    specs = load_answer_key(key_path, column_lookup)
    total_students = len(rows)
    log_entries: List[str] = []
    report_rows: List[Tuple[str, float, int, int, str, str]] = []
    high_miss: List[Tuple[str, float]] = []

    for spec in specs:
        missed, partial_counts = analyze_question(spec, rows, args.partial_threshold, log_entries)
        percent = (missed / total_students) * 100 if total_students else 0.0
        percent_display = f"{percent:.2f}"
        partial_notes = format_partial_notes(len(spec.correct_options), partial_counts)
        report_rows.append(
            (
                spec.question_label,
                percent_display,
                missed,
                total_students,
                spec.answer_display,
                partial_notes,
            )
        )
        if percent >= args.miss_threshold:
            high_miss.append((spec.question_label, percent))

    write_report(output_path, report_rows)
    if args.log:
        write_log(Path(args.log), log_entries)
    elif log_entries:
        print(f"Note: {len(log_entries)} warning(s) generated. Use --log to capture them.")

    if high_miss:
        warnings = ", ".join(f"{label} ({percent:.2f}%)" for label, percent in high_miss)
        print(f"Warning: {warnings} missed by >= {args.miss_threshold:.2f}% of students.")
    print(f"Wrote miss report to {output_path}")


if __name__ == "__main__":
    main()
