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


def _normalize_amount(raw_amount: str, sign: str | None) -> Decimal:
	value = Decimal(raw_amount.replace(",", ""))
	if sign and sign.lower() == "cr":
		return -value
	return value


def _extract_name(lines: list[str]) -> str:
	for idx, line in enumerate(lines):
		if "MY ZONE CREDIT CARD STATEMENT" in line.upper():
			for candidate in lines[idx + 1 :]:
				candidate = candidate.strip()
				if candidate:
					return candidate
			break
	return ""


def parse_axis_statement(file_path: str) -> dict:
	document_text = get_document_text(file_path)
	lines = [ln.strip() for ln in document_text.splitlines()]

	name = _extract_name(lines)
	card_last4s = extract_last4s_from_pdf(file_path)

	summary_match = re.search(
		r"Total\s+Payment\s+Due.*?\n"
		r"(?P<total>[\d,]+\.\d{2})\s*(?P<total_flag>Dr|Cr)?\s+"
		r"(?P<minimum>[\d,]+\.\d{2})\s*(?P<minimum_flag>Dr|Cr)?\s+"
		r"(?P<period>\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4})\s+"
		r"(?P<payment_due>\d{2}/\d{2}/\d{4})"
		r"(?:\s+(?P<generated>\d{2}/\d{2}/\d{4}))?",
		document_text,
		re.IGNORECASE,
	)

	statement_period = payment_due_date = statement_generated = ""
	total_payment_due = minimum_payment_due = None

	if summary_match:
		statement_period = summary_match.group("period").strip()
		payment_due_date = summary_match.group("payment_due")
		statement_generated = summary_match.group("generated") or ""
		total_payment_due = _normalize_amount(
			summary_match.group("total"), summary_match.group("total_flag")
		)
		minimum_payment_due = _normalize_amount(
			summary_match.group("minimum"), summary_match.group("minimum_flag")
		)

	transactions_section = ""
	start_idx = document_text.find("Account Summary")
	end_marker = "**** End of Statement ****"
	end_idx = document_text.find(end_marker)
	if start_idx != -1:
		transactions_section = document_text[start_idx:end_idx if end_idx != -1 else None]

	row_regex = re.compile(
		r"^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<body>.+)$",
		re.MULTILINE,
	)
	amount_regex = re.compile(r"(?P<amount>-?[\d,]+\.\d{2})\s*(?P<flag>Dr|Cr)?$")

	transactions: list[dict] = []
	matches = list(row_regex.finditer(transactions_section))
	for idx, match in enumerate(matches):
		start = match.start()
		end = matches[idx + 1].start() if idx + 1 < len(matches) else len(transactions_section)
		chunk = transactions_section[start:end].strip()
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

	return {
		"file_path": file_path,
		"card_last4_digits": card_last4s,
		"name": name,
		"statement_period": statement_period,
		"payment_due_date": payment_due_date,
		"statement_generated_date": statement_generated,
		"total_payment_due": total_payment_due,
		"minimum_payment_due": minimum_payment_due,
		"transactions": transactions,
	}


if __name__ == "__main__":
	parsed = parse_axis_statement("pdfs/axis-1.pdf")
	print(parsed)
