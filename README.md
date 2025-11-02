# Credit Card Statement Parser Suite

This workspace contains individual PDF parsers for major Indian credit-card issuers
( Axis Bank, HDFC Bank, ICICI Bank, IDFC FIRST Bank, and RBL Bank ). Each parser
extracts key billing metadata, card identifiers, and transactional information from the
statement PDFs located in the `pdfs/` directory.

## Project Structure

- `helper.py` – shared utility helpers (PDF page traversal, last-four-digit extraction).
- `axis_parser.py` – Axis Bank statement parser.
- `hdfc_parser.py` – HDFC Bank statement parser.
- `icici_parser.py` – ICICI Bank statement parser.
- `idfc_parser.py` – IDFC FIRST Bank statement parser.
- `rbl_parser.py` – RBL Bank statement parser.
- `test.py` – scratch script for experimentation / debugging.
- `pdfs/` – sample statement PDFs used by the parsers.

Every parser exposes a `parse_<issuer>_statement(file_path: str) -> dict` function
returning a JSON-serialisable structure containing the extracted details. Most parsers
also provide a `display_pdf_text` helper to dump the raw text of a PDF—useful when
crafting new parsing rules.

---

## Common Requirements

- Python 3.10+ recommended.
- Dependencies are managed via `pip`; key packages include `pdfplumber`, `PyMuPDF`
  (via `fitz`), and `spacy` (with `en_core_web_sm`).

### Installing Dependencies

From the `python/` directory:

```bash
pip install -r requirements.txt  # if available
# or install manually
pip install pdfplumber pymupdf pandas
```

Replace or augment with other dependencies as your environment requires.

---

## Axis Bank Parser (`axis_parser.py`)

**Key Outputs**
- `name`: Cardholder name (first prominent uppercase line after heading).
- `statement_period`, `payment_due_date`, `statement_generated_date`.
- `total_payment_due`, `minimum_payment_due` (normalized as `Decimal`).
- `transactions`: List of `{date, description, amount, type}` entries.
- `card_last4_digits`: List of unique last-four digits recovered from the PDF.

**Usage**
```python
from axis_parser import parse_axis_statement

data = parse_axis_statement("pdfs/axis-1.pdf")
print(data["name"], data["payment_due_date"])
```

Running the file directly executes the parser against `pdfs/axis-1.pdf` and prints
 the structured result.

---

## HDFC Bank Parser (`hdfc_parser.py`)

**Key Points**
- Uses `PyMuPDF` to target specific layout rectangles for summary details.
- Extracts name, statement date, payment due date, total dues, minimum amount due.
- Builds a list of transactions across the whole document.

**Usage**
```python
from hdfc_parser import parse_hdfc_statement

result = parse_hdfc_statement("pdfs/hdfc-1.pdf")
print(result["statement_info"]["payment_due_date"])
```

### Helper Functions
- `extract_text_from_rect(...)` – returns text from a specified PDF rectangle (supports relative coordinates).
- `extract_transactions(...)` – standalone helper to transform text blocks into transactions.

Running `python hdfc_parser.py` parses `pdfs/hdfc-1.pdf` and prints the output.

---

## ICICI Bank Parser (`icici_parser.py`)

**Features**
- Extracts customer name and masked card number from statement header.
- Captures statement date, billing period, payment due date, total/minimum dues.
- Gathers all transactions between `SPENDS OVERVIEW / Account Summary` and the following informational sections.

**Usage**
```python
from icici_parser import parse_icici_statement

parsed = parse_icici_statement("pdfs/icici-3.pdf")
print(parsed["transactions"][:3])
```

Ensure the `pdfplumber` output is clean; adjust regexes if the statement layout differs.

---

## IDFC FIRST Bank Parser (`idfc_parser.py`)

**Outputs**
- `name`, `masked_card_number`, `card_last4_digits`.
- `statement_period`, `statement_date`, `payment_due_date` (handles multiple layouts).
- `total_amount_due`, `minimum_amount_due`, `credit_limit`, `available_credit_limit`, `cash_limit`, `available_cash`.
- `transactions`: Normalized debit/credit list.

**Usage**
```python
from idfc_parser import parse_idfc_statement

summary = parse_idfc_statement("pdfs/idfc-2.pdf")
print(summary["name"], summary["total_amount_due"])
```

---

## RBL Bank Parser (`rbl_parser.py`)

**Capabilities**
- Extracts cardholder name from the header (filters out metadata lines).
- Retrieves masked card number, last-four digits, statement period/due date, total/minimum dues.
- Parses transaction history with `Cr/Dr` handling.

**Usage**
```python
from rbl_parser import parse_rbl_statement

rbl_data = parse_rbl_statement("pdfs/rbl-1.pdf")
print(rbl_data["name"], rbl_data["transactions"])
```

---

## Developing New Parsers

1. Add a new `*_parser.py` file.
2. Replicate the pattern: `display_pdf_text`, `get_document_text`, helper extraction functions, and a top-level `parse_<issuer>_statement` entry point.
3. Place sample PDFs in `pdfs/` for testing.
4. Optional: unify output schema to match existing dictionaries for easier API integration.

---

## API Integration (Future Work)

To expose these parsers via a REST API (e.g., FastAPI):

1. Install `fastapi` and `uvicorn`.
2. Implement a dispatcher module that maps issuer codes to parser functions.
3. Write a FastAPI application that accepts file uploads, saves them to a temporary location, dispatches to the proper parser, and returns the structured JSON.

Example skeleton for the dispatcher:
```python
from axis_parser import parse_axis_statement
from hdfc_parser import parse_hdfc_statement
# ... other imports

PARSERS = {
    "axis": parse_axis_statement,
    "hdfc": parse_hdfc_statement,
    "icici": parse_icici_statement,
    "idfc": parse_idfc_statement,
    "rbl": parse_rbl_statement,
}

def parse_statement(issuer: str, file_path: str) -> dict:
    try:
        parser = PARSERS[issuer.lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported issuer: {issuer}") from exc
    return parser(file_path)
```

---

## Tips & Best Practices

- Parse PDFs incrementally: inspect raw text via `display_pdf_text(...)` to identify stable anchors.
- Use regex cautiously; test on multiple statement samples to catch edge cases (e.g., amounts listed before dates, multi-line descriptions, optional “Cr” suffix).
- Normalize output types to ensure JSON serialization (convert `Decimal` to `float`/`str` if needed when returning via API).
- Maintain clean separation between extraction logic and file IO to enable easier unit testing.

---

## Running Parsers from the CLI

Each parser module includes a `__main__` guard for quick testing. For example:

```bash
python axis_parser.py
python hdfc_parser.py
python icici_parser.py
python idfc_parser.py
python rbl_parser.py
```

Make sure the corresponding sample PDF exists in the `pdfs/` directory or adjust the path in the script before running.

---

## Troubleshooting

- **`FileNotFoundError`**: Verify the path passed to the parser and ensure the sample PDF exists.
- **Encoding / OCR issues**: Some PDFs may require OCR or advanced layout parsing; consider integrating `pdfplumber`’s table extraction or `PyPDF2`/`pdfminer` as fallbacks.
- **Rupee symbol anomalies**: Currency strings sometimes include backticks or other characters; `_normalize_amount` helpers strip them before conversion.
- **Layout variations**: Issuers frequently change statement templates—update regexes and rectangle coordinates accordingly.

---

## License / Usage

These scripts operate on real credit-card statements. Ensure you have the right to process the PDF files and handle sensitive data securely (e.g., mask card numbers, store results safely, delete temporary files). No licence is specified—adapt as needed for your project.
