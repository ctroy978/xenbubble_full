# Bubblexan

## Bubble Sheet Generator

Create a printable bubble sheet PDF and matching JSON guide rail.

```bash
python generate_bubblesheet.py \
  --questions 25 \
  --id-length 6 \
  [--id-orientation vertical|horizontal] \
  [--border] \
  --output exam1 \
  [--paper-size A4] \
  [--output-dir output]
```

- Produces `output/exam1.pdf` and `output/exam1_layout.json` (unless an absolute `--output` path is supplied).
- Questions can range from 1–50, student ID length 4–10 digits.
- `--id-orientation horizontal` arranges each ID digit as a row of bubbles (0–9 left to right) instead of stacked columns.
- Pass `--border` if you specifically need the thick outer frame drawn; it is disabled by default for better alignment detection.
- The PDF automatically prints the output name (e.g., `exam1`) as a centered title near the top margin.

## QTI Test Generator

Convert Canvas QTI exports into a printable test (PDF) plus an answer-key CSV ready for the scanner pipeline:

```bash
python generate_test_from_qti.py \
  --zip ~/Downloads/sample.zip \
  [--qti path/to/custom_qti.xml] \
  [--meta path/to/assessment_meta.xml] \
  [--manifest path/to/imsmanifest.xml] \
  --output-dir output \
  [--page-size LETTER|A4] \
  --output-prefix week2_exam
```

- Emits `output/week2_exam_test.pdf` (questions with lettered a–e options, header/footer, name/date lines) and `output/week2_exam_answer_key.csv` (columns `Question,Correct_Answer,Points`).
- When `--zip` is supplied, the tool automatically extracts the Canvas export, locates the primary QTI XML, `assessment_meta.xml`, and `imsmanifest.xml`; you can still override any of them with explicit `--qti/--meta/--manifest` paths if needed.
- Multi-answer prompts automatically include “Select all that apply.” and the answer key stores comma-separated letters (e.g., `a,c,e`) compatible with `scan_bubblesheet.py`.
- The tool validates total points against `assessment_meta.xml` and can optionally read `imsmanifest.xml` for informational checks.

## Bubble Sheet Scanner

Process scanned bubble sheets (single image, directory, or .zip) using the generator’s layout JSON and emit a CSV plus optional log.

```bash
python scan_bubblesheet.py \
  --image scan1.png | --folder scans/ \
  --json output/exam1_layout.json \
  --output results.csv \
  [--threshold 0.5] \
  [--output-dir output] \
  [--log custom.log]
```

- Use `--image` for one file or `--folder` (directory or .zip) for batches.
- Results land in `output/results.csv` and a log file (defaults to the same prefix with `.log`).

### Visualization Helper

Use `testvision.py` to overlay bubble locations/scores on top of a scanned image when you need to debug alignment or thresholding:

```bash
python testvision.py \
  --image output/png/exam1_page01.png \
  --json output/exam1_layout.json \
  --output output/annotated.png \
  [--threshold 0.35] [--relative-threshold 0.6] [--alpha 0.6]
```

The script emits a blended PNG showing each bubble’s measured fill ratio (color-coded and labeled) plus any transform warnings when `--show-warnings` is passed.

## Question Miss Analyzer

Compare the scanner’s CSV against an answer key to spot questions most students missed (and summarize partial credit on select-all prompts):

```bash
python analyze_misses.py \
  --results output/results.csv \
  --key answer_key.csv \
  --output output/miss_report.csv \
  [--miss-threshold 50] \
  [--partial-threshold 1.0] \
  [--log miss_report.log]
```

- Pass the scanner CSV via `--results` and an answer-key CSV (`Question,Answer`) via `--key`.
- Multi-answer keys can use bracket or comma syntax (e.g., `[A,B,E]`); set `--partial-threshold` < 1.0 to award credit for subsets.
- The tool writes a per-question CSV detailing percent missed, counts, and partial-credit notes, and highlights questions above the miss threshold in the console.

## PDF → PNG Converter

Render generator PDFs into raster images for the scanner or other tools. Requires a Poppler installation accessible on your PATH.

```bash
python convert_pdf_to_png.py \
  --pdf output/exam1.pdf | --folder pdfs/ \
  --output-dir output/png \
  [--dpi 300] \
  [--fmt png|jpg] \
  [--prefix exam1]
```

- Handles single PDFs, folders, or zipped collections.
- Saves numbered images such as `output/png/exam1_page01.png`, ready for OpenCV processing.

## Grading App

Generate per-student totals and question statistics by pairing a response CSV (such as `output/results.csv` or any future `temp_report.csv`) with an answer key (`Question,Correct_Answer,Points`):

```bash
python grade.py \
  output/results.csv \
  output/answer_key.csv \
  --output-dir output
```

This writes `graded_report.csv` plus `graded_report.xlsx` (Grades + Question_Stats sheets) into the requested directory. Provide any CSV with columns `student_id,question_id,selected_answers`; multi-select selections should be comma-separated.

## Give-Back Adjustments

Clone the scanner results, mark specific questions correct for everyone, and re-run grading without touching the original CSV:

```bash
python give_back_questions.py \
  --results results/results.csv \
  --key tests/exam1_answer_key.csv \
  --give-back Q1,Q3 \
  --version adjustment_1 \
  --output-dir adjustments \
  [--log adjustments/adjustment_1.log]
```

- Writes `adjustments/adjustment_1_results.csv` with overridden `selected_answers` for the listed questions (using the answer key’s `Correct_Answer`).
- Chains `grade.py` to emit `adjustments/adjustment_1_graded_report.csv` and `.xlsx`.
- Never mutates the original results or any existing grade exports; pass a new `--version` for each adjustment.
- Optional `--log` records a textual summary of the edits and saved file paths.

## Scoring Details

- **Single-select questions**: a response earns the full point value only when every selected option matches the key exactly; otherwise it earns zero.
- **Multiple-select questions**: let `P` be the point value and `C` the number of correct options. For each response compute `S_c = |selected ∩ correct|` and `S_i = |selected − correct|`. Each correct option is worth `P / C` points and each incorrect option deducts the same amount, so the raw score is `(S_c − S_i) * (P / C)`. The awarded score is `max(0, raw score)` rounded to two decimals (never negative even if the penalty exceeds the reward).
- **Percent grades**: each student’s percent is `(total_score / total_possible_points) * 100`, rounded to two decimals. Question-level “percent_correct” equals the mean score for that question divided by its max points, times 100.
