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
	value = Decimal(raw_amount.replace(",", ""))
	if sign and sign.lower() == "cr":
		return -value
	return value


def _extract_customer_details(lines: list[str]) -> tuple[str, str]:
	name = ""
	masked_card = ""
	for idx, line in enumerate(lines):
		if line.strip().lower().startswith("customer name"):
			for candidate in lines[idx + 1 : idx + 5]:
				candidate = candidate.strip()
				if not candidate:
					continue
				card_match = re.search(r"(\d{4}\s+[Xx\*]{2,}\s+[Xx\*]{2,}\s+\d{3,4})", candidate)
				if card_match:
					masked_card = card_match.group(1)
					name = candidate[: card_match.start()].strip()
					if not name:
						name = candidate.replace(masked_card, "").strip()
				else:
					name = candidate
				break
			if name or masked_card:
				break
	return name, masked_card


def parse_icici_statement(file_path: str) -> dict:
	document_text = get_document_text(file_path)
	lines = [ln for ln in document_text.splitlines()]
	cleaned = re.sub(r"\s+", " ", document_text)

	name, masked_card = _extract_customer_details(lines)
	card_last4s = extract_last4s_from_pdf(file_path)

	summary_pattern = re.compile(
		r"Statement\s+Date\s+Minimum\s+Amount\s+Due\s+Your\s+Total\s+Amount\s+Due\s+"
		r"(?P<statement_date>\d{2}/\d{2}/\d{4})\s*\|?\s*(?P<minimum>[\d,]+\.\d{2})\s*\|?\s*(?P<total>[\d,]+\.\d{2})",
		re.IGNORECASE,
	)
	statement_date = ""
	minimum_amount_due = total_amount_due = None
	summary_match = summary_pattern.search(cleaned)
	if summary_match:
		statement_date = summary_match.group("statement_date")
		minimum_amount_due = _normalize_amount(summary_match.group("minimum"), None)
		total_amount_due = _normalize_amount(summary_match.group("total"), None)

	statement_period_match = re.search(
		r"Statement\s*Period\s*[:\-]?\s*(\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4})",
		document_text,
		re.IGNORECASE,
	)
	statement_period = statement_period_match.group(1) if statement_period_match else ""

	due_date_match = re.search(
		r"Due\s+Date\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
		document_text,
		re.IGNORECASE,
	)
	payment_due_date = due_date_match.group(1) if due_date_match else ""


	transactions_section = document_text
	start_marker = "Account Summary"
	start_idx = document_text.find(start_marker)
	if start_idx != -1:
		transactions_section = document_text[start_idx:]

	end_markers = ["Schedule of charges", "Important Message", "**** End of Statement ****"]
	end_positions = [transactions_section.find(marker) for marker in end_markers if marker in transactions_section]
	if end_positions:
		cutoff = min(pos for pos in end_positions if pos >= 0)
		transactions_section = transactions_section[:cutoff]

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

	return {
		"file_path": file_path,
		"card_last4_digits": card_last4s,
		"masked_card_number": masked_card,
		"name": name,
		"statement_date": statement_date,
		"statement_period": statement_period,
		"payment_due_date": payment_due_date,
		"total_amount_due": total_amount_due,
		"minimum_amount_due": minimum_amount_due,
		"transactions": transactions,
	}


if __name__ == "__main__":
	parsed = parse_icici_statement("pdfs/icici-1.pdf")
	print(parsed)