#!/usr/bin/env python3
"""CLI for applying "give back" adjustments to scanner results before grading."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, List, Sequence

import pandas as pd


class AdjustmentError(ValueError):
    """Raised when an adjustment input or operation fails."""


@dataclass(frozen=True)
class AdjustmentRecord:
    """Summarizes how many rows/students a question adjustment touched."""

    question_id: str
    row_count: int
    student_count: int


def parse_args() -> argparse.Namespace:
    """Configure CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Give back specific questions by overriding results and chaining grade.py.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--results", required=True, help="Path to results CSV from scan_bubblesheet.py.")
    parser.add_argument("--key", required=True, help="Answer-key CSV with Question/Correct_Answer/Points columns.")
    parser.add_argument("--give-back", required=True, help="Comma-separated list of question IDs to give back (e.g., Q1,Q3).")
    parser.add_argument("--version", required=True, help="Identifier used to version the adjusted outputs.")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory where <version>_results.csv and graded reports will be written.",
    )
    parser.add_argument("--log", help="Optional log file capturing the adjustment summary.")
    return parser.parse_args()


def normalize_version(version: str) -> str:
    """Ensure the requested version label is filesystem friendly."""
    text = version.strip()
    if not text:
        raise AdjustmentError("Version label cannot be blank.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", text):
        raise AdjustmentError("Version label may only contain letters, numbers, underscores, or hyphens.")
    return text


def parse_question_list(raw: str) -> List[str]:
    """Parse the comma-separated --give-back list into normalized IDs."""
    tokens = [item.strip() for item in raw.split(",")]
    cleaned: List[str] = []
    seen = set()
    for token in tokens:
        if not token:
            continue
        qid = token.upper()
        if qid not in seen:
            seen.add(qid)
            cleaned.append(qid)
    if not cleaned:
        raise AdjustmentError("No valid question IDs were supplied via --give-back.")
    return cleaned


def load_results(results_path: Path) -> pd.DataFrame:
    """Load and validate the scanner results CSV."""
    try:
        df = pd.read_csv(results_path)
    except FileNotFoundError as exc:
        raise AdjustmentError(f"Results CSV not found: {results_path}") from exc
    except Exception as exc:  # pragma: no cover - pandas specific errors
        raise AdjustmentError(f"Failed to read results CSV '{results_path}': {exc}") from exc

    expected = {"student_id", "question_id", "selected_answers"}
    missing = expected - set(df.columns)
    if missing:
        raise AdjustmentError(f"Results CSV missing column(s): {', '.join(sorted(missing))}")

    df = df.copy()
    df["student_id"] = df["student_id"].astype(str).str.strip()
    df["question_id"] = df["question_id"].astype(str).str.strip().str.upper()
    df["selected_answers"] = df["selected_answers"].fillna("").astype(str)
    return df


def load_answer_key(answer_key_path: Path) -> pd.DataFrame:
    """Load and validate the answer-key CSV."""
    try:
        df = pd.read_csv(answer_key_path)
    except FileNotFoundError as exc:
        raise AdjustmentError(f"Answer-key CSV not found: {answer_key_path}") from exc
    except Exception as exc:  # pragma: no cover
        raise AdjustmentError(f"Failed to read answer-key CSV '{answer_key_path}': {exc}") from exc

    expected = {"Question", "Correct_Answer", "Points"}
    missing = expected - set(df.columns)
    if missing:
        raise AdjustmentError(f"Answer-key CSV missing column(s): {', '.join(sorted(missing))}")

    df = df.copy()
    df["Question"] = df["Question"].astype(str).str.strip().str.upper()
    df["Correct_Answer"] = df["Correct_Answer"].fillna("").astype(str)

    duplicates = df["Question"].duplicated(keep=False)
    if duplicates.any():
        dup_ids = ", ".join(sorted(df.loc[duplicates, "Question"].unique()))
        raise AdjustmentError(f"Answer-key CSV contains duplicate Question entries: {dup_ids}")

    return df


def ensure_questions_exist(question_ids: Sequence[str], answer_key: pd.DataFrame) -> None:
    """Verify every requested question exists in the answer key."""
    answer_questions = set(answer_key["Question"].tolist())
    missing = [qid for qid in question_ids if qid not in answer_questions]
    if missing:
        raise AdjustmentError(
            f"The following questions were not found in the answer key: {', '.join(missing)}"
        )


def apply_give_backs(
    results_df: pd.DataFrame,
    answer_key: pd.DataFrame,
    question_ids: Sequence[str],
) -> List[AdjustmentRecord]:
    """Override selected_answers for each requested question."""
    answer_lookup = dict(zip(answer_key["Question"], answer_key["Correct_Answer"]))
    records: List[AdjustmentRecord] = []
    for qid in question_ids:
        mask = results_df["question_id"] == qid
        row_count = int(mask.sum())
        student_count = 0
        if row_count > 0:
            results_df.loc[mask, "selected_answers"] = answer_lookup[qid]
            student_count = results_df.loc[mask, "student_id"].nunique()
        records.append(AdjustmentRecord(question_id=qid, row_count=row_count, student_count=student_count))
    return records


def ensure_outputs_available(paths: Iterable[Path]) -> None:
    """Refuse to overwrite existing output files."""
    conflicts = [str(path) for path in paths if path.exists()]
    if conflicts:
        joined = ", ".join(conflicts)
        raise AdjustmentError(f"Refusing to overwrite existing file(s): {joined}")


def run_grade_pipeline(
    adjusted_results_path: Path,
    answer_key_path: Path,
    final_csv: Path,
    final_xlsx: Path,
) -> None:
    """Call grade.py using a temporary directory, then move outputs to versioned names."""
    grade_script = Path(__file__).with_name("grade.py")
    if not grade_script.exists():
        raise AdjustmentError(f"grade.py not found alongside this script: {grade_script}")

    with TemporaryDirectory(prefix="give_back_", dir=final_csv.parent) as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        cmd = [
            sys.executable or "python3",
            str(grade_script),
            str(adjusted_results_path),
            str(answer_key_path),
            "--output-dir",
            str(tmp_dir_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            combined = "\n".join(part for part in [stdout, stderr] if part)
            raise AdjustmentError(f"grade.py failed (exit code {result.returncode}). Details:\n{combined}")

        tmp_csv = tmp_dir_path / "graded_report.csv"
        tmp_xlsx = tmp_dir_path / "graded_report.xlsx"
        if not tmp_csv.exists() or not tmp_xlsx.exists():
            raise AdjustmentError("grade.py did not produce the expected graded_report outputs.")

        shutil.move(tmp_csv, final_csv)
        shutil.move(tmp_xlsx, final_xlsx)


def write_log(log_path: Path, lines: Sequence[str]) -> None:
    """Persist the optional log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines).strip() + "\n"
    log_path.write_text(content, encoding="utf-8")


def format_record(record: AdjustmentRecord) -> str:
    """Return a human-readable description for console/log output."""
    if record.row_count == 0:
        return f"{record.question_id}: no matching responses found."
    suffix = "student" if record.student_count == 1 else "students"
    return f"{record.question_id}: updated {record.student_count} {suffix} ({record.row_count} rows)."


def main() -> None:
    """Entry point."""
    args = parse_args()
    results_path = Path(args.results)
    answer_key_path = Path(args.key)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    version = normalize_version(args.version)
    question_ids = parse_question_list(args.give_back)

    adjusted_results_path = output_dir / f"{version}_results.csv"
    final_csv_path = output_dir / f"{version}_graded_report.csv"
    final_xlsx_path = output_dir / f"{version}_graded_report.xlsx"

    ensure_outputs_available([adjusted_results_path, final_csv_path, final_xlsx_path])

    log_path = Path(args.log) if args.log else None

    results_df = load_results(results_path)
    answer_key_df = load_answer_key(answer_key_path)
    ensure_questions_exist(question_ids, answer_key_df)

    records = apply_give_backs(results_df, answer_key_df, question_ids)
    results_df.to_csv(adjusted_results_path, index=False)

    run_grade_pipeline(adjusted_results_path, answer_key_path, final_csv_path, final_xlsx_path)

    summary_lines = [
        f"Version: {version}",
        f"Results source: {results_path}",
        f"Answer key: {answer_key_path}",
        f"Adjusted results: {adjusted_results_path}",
        "Question adjustments:",
        *["  - " + format_record(record) for record in records],
        f"Graded CSV: {final_csv_path}",
        f"Graded XLSX: {final_xlsx_path}",
    ]

    for record in records:
        print(format_record(record))

    print(f"Saved {adjusted_results_path}")
    print(f"Saved {final_csv_path}")
    print(f"Saved {final_xlsx_path}")

    if log_path:
        write_log(log_path, summary_lines)
        print(f"Wrote log {log_path}")


if __name__ == "__main__":
    try:
        main()
    except AdjustmentError as exc:
        print(f"Adjustment failed: {exc}", file=sys.stderr)
        sys.exit(1)
