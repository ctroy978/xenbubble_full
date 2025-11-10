#!/usr/bin/env python3
"""Grading app that applies Canvas-style scoring to bubble-sheet exports."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pandas as pd


@dataclass(frozen=True)
class QuestionSpec:
    question_id: str
    correct_options: Set[str]
    points: float

    @property
    def is_multiple(self) -> bool:
        return len(self.correct_options) > 1

    @property
    def num_correct(self) -> int:
        return len(self.correct_options)


class GradingError(ValueError):
    """Raised when an input file is malformed."""


def parse_args() -> argparse.Namespace:
    """Configure and parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Grade student responses using Canvas multiple-select scoring.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("responses_csv", help="Path to report.csv or temp_report.csv with student answers.")
    parser.add_argument("answer_key_csv", help="Path to week2_ziptest_answer_key.csv.")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory where graded_report.csv and graded_report.xlsx will be written.",
    )
    return parser.parse_args()


def _tokenize_answers(value: object) -> List[str]:
    """Return a normalized list of answer option tokens from a CSV cell."""
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    tokens = [part.strip().lower() for part in text.split(",") if part.strip()]
    return tokens


def load_answer_key(path: Path) -> Tuple[Dict[str, QuestionSpec], float, List[str]]:
    """Read the answer key and return a mapping plus total points and question order."""
    try:
        key_df = pd.read_csv(path)
    except FileNotFoundError as exc:
        raise GradingError(f"Answer-key CSV not found: {path}") from exc
    except Exception as exc:  # pragma: no cover - pandas can raise many subclasses
        raise GradingError(f"Failed to read answer-key CSV '{path}': {exc}") from exc

    expected_cols = {"Question", "Correct_Answer", "Points"}
    missing = expected_cols - set(key_df.columns)
    if missing:
        raise GradingError(f"Answer-key CSV missing columns: {', '.join(sorted(missing))}")

    question_map: Dict[str, QuestionSpec] = {}
    total_points = 0.0
    order: List[str] = []

    for _, row in key_df.iterrows():
        raw_question = str(row["Question"]).strip()
        if not raw_question:
            raise GradingError("Answer-key row is missing a Question value.")
        question_id = raw_question.upper()
        tokens = _tokenize_answers(row["Correct_Answer"])
        if not tokens:
            raise GradingError(f"Question '{question_id}' has no valid correct answers.")
        points = float(row["Points"])
        if points < 0:
            raise GradingError(f"Question '{question_id}' has negative point value {points}.")
        if question_id in question_map:
            raise GradingError(f"Duplicate question '{question_id}' in answer key.")
        spec = QuestionSpec(question_id=question_id, correct_options=set(tokens), points=points)
        question_map[question_id] = spec
        total_points += points
        order.append(question_id)
    if total_points <= 0:
        raise GradingError("Total possible points must be positive.")
    return question_map, total_points, order


def score_multiple_select(
    total_points: float,
    correct_options: int,
    selected_correct: int,
    selected_incorrect: int,
) -> Tuple[float, str]:
    """Score a multiple-select response using the Canvas formula."""
    if total_points < 0:
        raise ValueError("total_points cannot be negative.")
    if correct_options <= 0:
        return 0.0, "Invalid question: No correct options."
    if selected_correct < 0 or selected_incorrect < 0:
        raise ValueError("Selection counts cannot be negative.")
    if selected_correct > correct_options:
        raise ValueError("selected_correct cannot exceed number of correct options.")

    point_per_option = total_points / correct_options
    raw_score = (selected_correct - selected_incorrect) * point_per_option
    score = max(0.0, raw_score)
    score = round(score + 1e-12, 2)
    pos = round(selected_correct * point_per_option + 1e-12, 2)
    neg = round(selected_incorrect * point_per_option + 1e-12, 2)
    explanation = (
        f"{selected_correct} correct (+{pos:.2f}), "
        f"{selected_incorrect} incorrect (-{neg:.2f}), Total: {score:.2f}/{total_points:.2f}"
    )
    return score, explanation


def _score_row(row: pd.Series, answer_map: Dict[str, QuestionSpec]) -> Tuple[float, str]:
    """Score a single response row and provide a short explanation."""
    question_id = str(row["question_id"]).strip().upper()
    if question_id not in answer_map:
        raise GradingError(f"Question '{question_id}' not found in answer key.")
    spec = answer_map[question_id]
    selected_tokens = set(_tokenize_answers(row.get("selected_answers")))

    if not spec.is_multiple:
        correct = spec.correct_options
        score = spec.points if selected_tokens == correct else 0.0
        explanation = (
            f"Single-select: {'correct' if score else 'incorrect'} (" f"{score:.2f}/{spec.points:.2f})"
        )
        return round(score, 2), explanation

    hits = len(selected_tokens & spec.correct_options)
    extras = len(selected_tokens - spec.correct_options)
    score, explanation = score_multiple_select(spec.points, spec.num_correct, hits, extras)
    return score, explanation


def grade_responses(responses_path: Path, answer_path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Produce the graded results table and question stats table."""
    answer_map, total_points, question_order = load_answer_key(answer_path)

    try:
        responses_df = pd.read_csv(responses_path)
    except FileNotFoundError as exc:
        raise GradingError(f"Responses CSV not found: {responses_path}") from exc
    except Exception as exc:  # pragma: no cover
        raise GradingError(f"Failed to read responses CSV '{responses_path}': {exc}") from exc

    expected_cols = {"student_id", "question_id", "selected_answers"}
    missing = expected_cols - set(responses_df.columns)
    if missing:
        raise GradingError(f"Responses CSV missing columns: {', '.join(sorted(missing))}")

    responses_df = responses_df.copy()
    responses_df["student_id"] = responses_df["student_id"].astype(str).str.strip()
    responses_df["question_id"] = responses_df["question_id"].astype(str).str.strip().str.upper()
    responses_df["selected_answers"] = responses_df["selected_answers"].fillna("")

    scores: List[float] = []
    explanations: List[str] = []
    for _, row in responses_df.iterrows():
        score, explanation = _score_row(row, answer_map)
        scores.append(score)
        explanations.append(explanation)
    responses_df["score_per_question"] = scores
    responses_df["explanation"] = explanations

    totals = responses_df.groupby("student_id")["score_per_question"].sum().rename("total_score")
    responses_df = responses_df.merge(totals, on="student_id", how="left")
    responses_df["percent_grade"] = responses_df["total_score"].apply(lambda x: round((x / total_points) * 100, 2))

    responses_df["score_per_question"] = responses_df["score_per_question"].round(2)
    responses_df["total_score"] = responses_df["total_score"].round(2)

    # Question stats
    question_scores = (
        responses_df.groupby("question_id")["score_per_question"].mean().reindex(question_order)
    )
    stats_records = []
    for qid in question_order:
        spec = answer_map[qid]
        value = question_scores.get(qid)
        mean_score = float(value) if value is not None and pd.notna(value) else 0.0
        percent_correct = round((mean_score / spec.points) * 100 if spec.points else 0.0, 2)
        stats_records.append({
            "question_id": qid,
            "mean_score": round(mean_score, 2),
            "percent_correct": percent_correct,
        })
    stats_df = pd.DataFrame(stats_records)

    output_cols = [
        "student_id",
        "question_id",
        "selected_answers",
        "score_per_question",
        "total_score",
        "percent_grade",
    ]
    graded_df = responses_df[output_cols].copy()
    graded_df = graded_df.sort_values(["student_id", "question_id"]).reset_index(drop=True)
    graded_df["percent_grade"] = graded_df["percent_grade"].round(2)

    return graded_df, stats_df


def write_outputs(graded_df: pd.DataFrame, stats_df: pd.DataFrame, output_dir: Path) -> None:
    """Persist CSV/XLSX outputs in the requested directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "graded_report.csv"
    graded_df.to_csv(csv_path, index=False)

    xlsx_path = output_dir / "graded_report.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        graded_df.to_excel(writer, sheet_name="Grades", index=False)
        stats_df.to_excel(writer, sheet_name="Question_Stats", index=False)

    print(f"Wrote {csv_path} and {xlsx_path}")


def main() -> None:
    """Entry point for the grading CLI."""
    args = parse_args()
    responses_path = Path(args.responses_csv)
    answer_path = Path(args.answer_key_csv)
    output_dir = Path(args.output_dir)

    graded_df, stats_df = grade_responses(responses_path, answer_path)
    write_outputs(graded_df, stats_df, output_dir)


if __name__ == "__main__":
    main()
