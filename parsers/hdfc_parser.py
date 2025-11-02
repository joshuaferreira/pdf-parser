import fitz  # PyMuPDF
import re
import os
import pdfplumber
from decimal import Decimal

def extract_last4s_for_file(file_path: str) -> list[str]:
    """Return the list of unique last-4 digits for the provided PDF file."""
    from .helper import extract_last4s_from_pdf
    return extract_last4s_from_pdf(file_path)

def extract_text_from_rect(
    pdf_path: str,
    page_index: int,
    rect_coords: tuple[float, float, float, float],
    expand: float = 0.0,
    use_relative: bool = False,
) -> str:
    """
    Return text from a rectangular region.

    Parameters
    ----------
    pdf_path: path to the PDF file.
    page_index: zero-based index of the page to inspect.
    rect_coords: either absolute coordinates (x0, y0, x1, y1) in PDF units or
        percentages in the range [0, 1] if use_relative is True.
    expand: optional padding (same units as coordinates) to grow the rectangle.
    use_relative: interpret rect_coords as percentages of page width/height.
    """

    with fitz.open(pdf_path) as doc:
        page = doc[page_index]
        if use_relative:
            x0_pct, y0_pct, x1_pct, y1_pct = rect_coords
            page_width, page_height = page.rect.width, page.rect.height
            rect = fitz.Rect(
                x0_pct * page_width,
                y0_pct * page_height,
                x1_pct * page_width,
                y1_pct * page_height,
            )
        else:
            rect = fitz.Rect(*rect_coords)

        if expand:
            rect = rect + (-expand, -expand, expand, expand)

        # Collect and order words inside the rectangle for better layout control.
        words = page.get_text("words")
        rect_words = [w for w in words if fitz.Rect(w[:4]).intersects(rect)]
        rect_words.sort(key=lambda w: (round(w[1], 1), w[0]))  # sort by y, then x
        
    # Note: avoid writing files in serverless environments. Previously this
    # created an annotation and saved to disk (highlighted.pdf) for
    # debugging; that can fail on Vercel (read-only filesystem) and cause
    # runtime errors. We simply extract and return the text from the
    # rectangle instead.
    return " ".join(w[4] for w in rect_words)


# HDFC details block coordinates
HDFC_DETAILS_BLOCK = (0.03, 0.05, 0.40, 0.18)

# HDFC Statement Period block coordinates
HDFC_STATEMENT_PERIOD_BLOCK = (0.40, 0.06, 0.97, 0.39)


def get_document_text(file_path: str) -> str:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")

    parts: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)

def clean_text(text):
    text = re.sub(r'\s+', ' ', text)  # collapse all whitespace
    text = text.replace(" .", ".").replace(" ,", ",")
    return text.strip()


def hdfc_extract_statement_info(details_text, statement_text):
    info: dict[str, str] = {}

    details_clean = clean_text(details_text)
    statement_clean = clean_text(statement_text)

    name_match = re.search(
        r"Name\s*[:\-]?\s*([A-Za-z\s\.]+?)(?=\s+(Email|Mobile|Phone)\b)",
        details_clean,
        re.IGNORECASE,
    )
    if name_match:
        info["name"] = name_match.group(1).strip()

    statement_date_match = re.search(
        r"Statement\s*Date\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})",
        statement_clean,
        re.IGNORECASE,
    )
    if statement_date_match:
        info["statement_date"] = statement_date_match.group(1)

    amount_in_order = re.compile(
        r"Payment\s+Due\s+Date\s+Total\s+Dues\s+Minimum\s+Amount\s+Due\s+"
        r"(\d{1,2}/\d{1,2}/\d{4})\s+([\d,]+(?:\.\d{2})?)\s+([\d,]+(?:\.\d{2})?)",
        re.IGNORECASE,
    )
    amount_last = re.compile(
        r"Payment\s+Due\s+Date\s+Total\s+Dues\s+Minimum\s+Amount\s+Due\s+"
        r"([\d,]+(?:\.\d{2})?)\s+([\d,]+(?:\.\d{2})?)\s+(\d{1,2}/\d{1,2}/\d{4})",
        re.IGNORECASE,
    )

    payment_due_date = total_dues = minimum_due = None

    match = amount_in_order.search(statement_clean)
    if match:
        payment_due_date, total_dues, minimum_due = match.groups()
    else:
        match = amount_last.search(statement_clean)
        if match:
            total_dues, minimum_due, payment_due_date = match.groups()

    if payment_due_date:
        info["payment_due_date"] = payment_due_date
    if total_dues:
        info["total_dues"] = total_dues
    if minimum_due:
        info["minimum_amount_due"] = minimum_due

    return info

row_regex = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<body>.+)$",
    re.MULTILINE,
)

amount_regex = re.compile(
    r"(?P<amount>-?[\d,]+\.\d{2})\s*(?P<credit>Cr)?$"
)

def extract_transactions(block: str) -> list[dict]:
    block = block.replace("\r\n", "\n")
    matches = list(row_regex.finditer(block))
    records: list[dict] = []

    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(block)
        segment = block[start:end].strip()
        if not segment:
            continue

        lines = [ln.strip() for ln in segment.splitlines() if ln.strip()]
        if not lines:
            continue

        date = match.group("date")
        segment_text = " ".join(lines)
        rest = segment_text[len(date):].strip()
        if not rest:
            continue

        m_amt = amount_regex.search(rest)
        if not m_amt:
            continue

        amount = Decimal(m_amt.group("amount").replace(",", ""))
        credit = bool(m_amt.group("credit"))
        description = amount_regex.sub("", rest).strip()
        records.append(
            {
                "date": date,
                "description": description,
                "amount": amount,
                "type": "credit" if credit else "debit",
            }
        )

    return records

def parse_hdfc_statement(file_path: str) -> dict:
    details_text = extract_text_from_rect(
        file_path,
        page_index=0,
        rect_coords=HDFC_DETAILS_BLOCK,
        expand=4,
        use_relative=True,
    )
    statement_text = extract_text_from_rect(
        file_path,
        page_index=0,
        rect_coords=HDFC_STATEMENT_PERIOD_BLOCK,
        expand=4,
        use_relative=True,
    )

    statement_info = hdfc_extract_statement_info(details_text, statement_text)
    card_last4s = extract_last4s_for_file(file_path)
    full_text = get_document_text(file_path)
    transactions = extract_transactions(full_text)

    return {
        "file_path": file_path,
        "card_last4_digits": card_last4s,
        "statement_info": statement_info,
        "transactions": transactions,
    }


if __name__ == "__main__":
    parsed = parse_hdfc_statement("pdfs/hdfc-1.pdf")
    print(parsed)