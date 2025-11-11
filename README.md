# Bubblexan

Bubblexan helps non-technical instructors turn online tests into paper-and-pencil exams, scan and grade bubble sheets, and analyze results. The project has two parts:

- **CLI tools** in `bubblexan_cli/`
- **PyQt6 GUI** in `bubblexan_gui/`

## Test Folder Structure

To keep every exam organized, Bubblexan stores files inside `test_build/<test_name>/`. Create this structure using the **Test Manager** tab in the GUI:

1. Run the GUI (see Setup).
2. Open **Test Manager**.
3. Enter a test name (e.g., `exam_1_class2`).
4. Click **Create Test Folder**.

This generates:

```
test_build/
└── exam_1_class2/
    ├── inputs/
    │   └── scans/
    ├── bubble_sheets/
    ├── tests/
    ├── scanned_images/
    ├── results/
    ├── grades/
    ├── miss_analysis/
    └── adjustments/
```

- `inputs/`: Canvas QTI ZIP files, other raw materials.
- `inputs/scans/`: Scanned images or ZIPs for the scanner/converter.
- `bubble_sheets/`: PDFs + JSON layouts from the Bubble Sheet Generator.
- `tests/`: Test PDFs + answer keys from the QTI Test Generator.
- `scanned_images/`: PNGs from the PDF → PNG Converter.
- `results/`: CSV/logs from the Bubble Sheet Scanner.
- `grades/`: `graded_report.csv/.xlsx` from the Grading tab.
- `miss_analysis/`: `miss_report.csv` + optional log.
- `adjustments/`: `report_adjusted.csv` + optional log.

Point each GUI tab to the matching folder to keep inputs/outputs neat.

## Setup

Install system deps first (e.g., Poppler for PDF conversion: `sudo apt install poppler-utils`, `brew install poppler`).

### CLI env
```bash
cd xenbubble_full/bubblexan_cli
python -m venv .venv
source .venv/bin/activate      # .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### GUI env
```bash
cd xenbubble_full/bubblexan_gui
python -m venv .venv
source .venv/bin/activate
pip install PyQt6>=6.7.0
```

### Run GUI
```bash
cd xenbubble_full/bubblexan_gui/src
python main.py
```

## GUI Tabs & CLI Tools

| Tab / CLI | Inputs | Outputs | Purpose |
|-----------|--------|---------|---------|
| **Test Manager** | Test name | Folder tree in `test_build/<name>/` | Creates structured folders |
| **Bubble Sheet Generator** (`generate_bubblesheet.py`) | Options (questions, id length, etc.) | `bubble_sheets/<name>.pdf` + `<name>_layout.json` | Builds blank bubble sheets |
| **QTI Test Generator** (`generate_test_from_qti.py`) | QTI ZIP in `inputs/`, optional XML overrides | `tests/<name>_test.pdf`, `<name>_answer_key.csv` | Converts Canvas exports |
| **PDF → PNG Converter** (`convert_pdf_to_png.py`) | PDF/folder/ZIP from `inputs/scans/` or `tests/` | PNG/JPG files in `scanned_images/` | Preps scans for the scanner |
| **Bubble Sheet Scanner** (`scan_bubblesheet.py`) | Images from `scanned_images/`, layout JSON from `bubble_sheets/` | `results/results.csv` (+ log) | Turns filled sheets into data |
| **Visualization Helper** (`testvision.py`) | Image + JSON | Annotated PNG in `scanned_images/` | Debugs scanner alignment |
| **Grading** (`grade.py`) | `results/results.csv`, `tests/<name>_answer_key.csv` | `grades/graded_report.csv/.xlsx` | Computes student grades |
| **Question Miss Analyzer** (`analyze_misses.py`) | `results/results.csv`, `tests/<name>_answer_key.csv` | `miss_analysis/miss_report.csv` (+ log) | Finds frequently missed questions |
| **Grade Adjustment** (`adjust_grades.py`) | `grades/graded_report.csv`, question IDs | `adjustments/report_adjusted.csv` (+ log) | Simulates zeroing out questions |

> ℹ️ The Grade Adjustment tab is wired up, but `bubblexan_cli/adjust_grades.py` does not exist yet. Add it to the CLI and re-enable validation in `bubblexan_gui/config.py` when ready.

## Workflow Tips

1. **Create folder** via Test Manager (`test_build/exam_1_class2/`).
2. **Generate** bubble sheets & tests (`bubble_sheets/`, `tests/`).
3. **Print & scan** bubble sheets; place scans in `inputs/scans/`.
4. **Convert + scan** to produce `results/results.csv`.
5. **Grade**, **analyze**, and **adjust** using the dedicated tabs.

Keep each tab pointed at the right subfolder so new files stay grouped by test.

## Manual Answer Key Import

Instructors can manually create an answer key for custom tests (instead of using a Canvas QTI export) and import it via the **Answer Key Import** tab in the Bubblexan GUI. Create your CSV file anywhere on your computer (naming it `answer_key.csv` is fine—the app renames it automatically) and follow the format below. When imported, the file is stored as `<test_name>_answer_key.csv` inside the selected test folder (e.g., `exam1_answer_key.csv`).

### Answer Key CSV Format

- **File Type**: CSV (`.csv`).
- **Headers**: `Question,Correct_Answer,Points` (case-sensitive, required).
- **Columns**:
  - `Question`: Unique question identifier (e.g., `Q1`, `Question_2`). Use alphanumeric characters, underscores, or hyphens.
  - `Correct_Answer`: Correct answer(s) as a single letter (e.g., `a`) or comma-separated letters for multi-answer questions (e.g., `"b,c,d"`). Use lowercase letters `a`–`e`, with no spaces in multi-answer entries.
  - `Points`: Positive number (e.g., `2.00`, `4.0`) representing the question’s point value.
- **Constraints**:
  - Headers must be present.
  - No empty rows or missing values.
  - Multi-answer entries must include commas only (e.g., `"a,c,e"`).

**Example**

```csv
Question,Correct_Answer,Points
Q1,"b,c,d",4.00
Q2,a,2.00
Q3,b,2.00
```

### Importing the Answer Key

1. In the **Test Manager** tab, create or select a test (e.g., `exam1`).
2. In the **Answer Key Import** tab:
   - Click **Browse** to select your CSV file (e.g., `answer_key.csv` from your computer).
   - Click **Show Instructions** to view formatting requirements.
   - Click **Import Answer Key** to validate and save the file.
3. The file is saved to `test_build/<test_name>_<timestamp>/tests/<test_name>_answer_key.csv` (e.g., `test_build/exam1_20251110_1743/tests/exam1_answer_key.csv`).
4. Use the **Review Answer Key** button to verify the imported file.

### Notes

- The CSV is validated for correct headers, question IDs, answer formats, and point values.
- Invalid files trigger an error message (e.g., “Missing header ‘Points’.”).
- The imported answer key is compatible with the Grading App (`grade.py`) for scoring bubble sheets.

## Scanning Bubble Sheets

1. Use your scanner’s automatic document feeder to batch-scan student sheets into a single multi-page PDF (one page per student) at **300 DPI grayscale**.
2. Save the PDF inside `test_build/<test_name>_<timestamp>/inputs/scans/` so it stays organized with the rest of the test assets.
3. Open the **PDF to PNG Conversion** tab:
   - Select the PDF, folder, or ZIP file.
   - Keep the DPI at 300 unless you have a special requirement (100–600 supported).
   - Click **Convert to Images** to produce `scanned_images/<prefix>_page01.png`, `<prefix>_page02.png`, etc.
4. Confirm the PNGs with **Review Images**, then process them with the **Bubble Sheet Scanner** tab.

### Conversion Tips

- Ensure the entire border and alignment markers are visible on each scan.
- Ask students to use #2 pencils and fully fill bubbles.
- Avoid stapling, taping, or laminating sheets before scanning.
- Large PDFs (hundreds of pages) may take several minutes to convert—keep the GUI open until completion.
