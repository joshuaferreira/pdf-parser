import os
import re
from decimal import Decimal

import pdfplumber
from .helper import extract_last4s_from_pdf


def display_pdf_text(file_path: str) -> None:
	"""Print all text from the PDF as a single string."""
	print(get_document_text(file_path))


def get_document_text(file_path: str) -> str:
	if not os.path.isfile(file_path):
		raise FileNotFoundError(f"The file {file_path} does not exist.")

	parts: list[str] = []
	with pdfplumber.open(file_path) as pdf:
		for page in pdf.pages:
			page_text = page.extract_text() or ""
			parts.append(page_text)
	return "\n".join(parts)


def _normalize_amount(raw_amount: str | None, sign: str | None) -> Decimal | None:
	if not raw_amount:
		return None
	clean = re.sub(r"[^0-9.\-]", "", raw_amount)
	if not clean:
		return None
	value = Decimal(clean)
	if sign and sign.lower() in {"cr", "credit"}:
		return -value
	return value


def _extract_masked_card(text: str) -> str:
	match = re.search(r"(\d{4}[\sXx\*]{4,}\d{2,4})", text)
	if match:
		return re.sub(r"\s+", "", match.group(1))
	return ""


def _extract_name(lines: list[str]) -> str:
	for line in lines:
		clean = line.strip()
		if not clean:
			continue
		if re.search(r"\d", clean):
			continue
		lowered = clean.lower()
		if any(keyword in lowered for keyword in ["bangalore", "contact", "page", "goods", "message", "offer"]):
			continue
		if len(clean.split()) <= 4:
			return clean
	return ""


def _extract_statement_details(text: str) -> dict:
	details: dict[str, str | Decimal | None] = {
		"statement_period": "",
		"payment_due_date": "",
		"total_amount_due": None,
		"minimum_amount_due": None,
	}

	period_match = re.search(
		r"(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}/\d{2}/\d{4}))?",
		text,
	)
	if period_match:
		details["statement_period"] = f"{period_match.group(1)} - {period_match.group(2)}"
		if period_match.group(3):
			details["payment_due_date"] = period_match.group(3)

	if not details["payment_due_date"]:
		due_match = re.search(
			r"Payment\s+Due\s+Date\s*(?:[:\-])?\s*(\d{2}/\d{2}/\d{4})",
			text,
			re.IGNORECASE,
		)
		if due_match:
			details["payment_due_date"] = due_match.group(1)

	total_match = re.search(
		r"Total\s+Amount\s+Due\s*(?:[:\-])?\s*([₹rRs`\.\s]*[\d,]+(?:\.\d{1,2})?)",
		text,
		re.IGNORECASE,
	)
	if total_match:
		details["total_amount_due"] = _normalize_amount(total_match.group(1), None)

	min_match = re.search(
		r"Minimum\s+Amount\s+Due\s*(?:[:\-])?\s*([₹rRs`\.\s]*[\d,]+(?:\.\d{1,2})?)",
		text,
		re.IGNORECASE,
	)
	if min_match:
		details["minimum_amount_due"] = _normalize_amount(min_match.group(1), None)

	if details["total_amount_due"] is None:
		fallback = re.search(
			r"to\s+\d{2}/\d{2}/\d{4}\s+\d{2}/\d{2}/\d{4}\s+([\d,]+\.\d{2})",
			text,
		)
		if fallback:
			details["total_amount_due"] = _normalize_amount(fallback.group(1), None)

	return details


def _extract_transactions(text: str) -> list[dict]:
	row_regex = re.compile(r"^(?P<date>\d{2}-[A-Za-z]{3}-\d{4})\s+(?P<body>.+)$", re.MULTILINE)
	amount_regex = re.compile(
		r"(?P<amount>-?[₹rRs`\.\s]*[\d,]+(?:\.\d{1,2})?)(?P<flag>Cr|CR|Dr|DR)?$",
		re.IGNORECASE,
	)

	transactions: list[dict] = []
	matches = list(row_regex.finditer(text))
	for idx, match in enumerate(matches):
		start = match.start()
		end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
		chunk = text[start:end].strip()
		if not chunk:
			continue

		lines_chunk = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
		if not lines_chunk:
			continue

		date = match.group("date")
		merged = " ".join(lines_chunk)
		body = merged[len(date) :].strip()
		if not body:
			continue

		amount_match = amount_regex.search(body)
		if not amount_match:
			continue

		amount = _normalize_amount(amount_match.group("amount"), amount_match.group("flag"))
		if amount is None:
			continue

		description = amount_regex.sub("", body).strip()
		tx_type = "credit" if amount < 0 else "debit"

		transactions.append(
			{
				"date": date,
				"description": description,
				"amount": amount,
				"type": tx_type,
			}
		)

	return transactions


def parse_rbl_statement(file_path: str) -> dict:
	document_text = get_document_text(file_path)
	lines = [ln for ln in document_text.splitlines()]

	name = _extract_name(lines)
	masked_card = _extract_masked_card(document_text)
	card_last4 = extract_last4s_from_pdf(file_path)
	statement_details = _extract_statement_details(document_text)
	transactions = _extract_transactions(document_text)

	return {
		"file_path": file_path,
		"card_last4_digits": card_last4,
		"masked_card_number": masked_card,
		"name": name,
		"statement_period": statement_details["statement_period"],
		"payment_due_date": statement_details["payment_due_date"],
		"total_amount_due": statement_details["total_amount_due"],
		"minimum_amount_due": statement_details["minimum_amount_due"],
		"transactions": transactions,
	}


if __name__ == "__main__":
	parsed = parse_rbl_statement("pdfs/rbl-1.pdf")
	print(parsed)