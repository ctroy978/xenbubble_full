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
