import os
import re
from decimal import Decimal

import pdfplumber
from helper import extract_last4s_from_pdf


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


def _extract_name(lines: list[str]) -> str:
	card_pattern = re.compile(r"\b\d{4}[Xx\*]{2,}\d{2,}\b")
	for idx, line in enumerate(lines):
		if card_pattern.search(line.replace(" ", "")):
			for prev in range(idx - 1, max(-1, idx - 6), -1):
				candidate = lines[prev].strip()
				if candidate and not card_pattern.search(candidate.replace(" ", "")) and ":" not in candidate:
					return candidate
			break

	for line in lines[:10]:
		stripped = line.strip()
		if not stripped:
			continue
		if "credit card statement" in stripped.lower():
			continue
		if re.search(r"\d{2}/\d{2}/\d{4}\s*-", stripped):
			continue
		if ":" in stripped:
			continue
		if any(c.isalpha() for c in stripped):
			return stripped
	return ""


def _extract_masked_card(text: str) -> str:
	match = re.search(r"(\d{4}[\sXx\*]{4,}\d{2,4})", text)
	if match:
		return re.sub(r"\s+", "", match.group(1))
	alt = re.search(r"([Xx\*]{2,}\s*\d{3,4})", text)
	return re.sub(r"\s+", "", alt.group(1)) if alt else ""


def _strip_artifacts(value: str) -> str:
	return re.sub(r"\(cid:[^)]+\)", "", value).strip()


def _extract_summary_amount(label: str, text: str) -> Decimal | None:
	pattern = re.compile(
		rf"{label}\s*(?:[:\-])?\s*\n\s*([₹rRs`\.\s]*[\d,]+(?:\.\d{{1,2}})?)",
		re.IGNORECASE,
	)
	match = pattern.search(text)
	if match:
		return _normalize_amount(match.group(1), None)
	return None


def _collect_transaction_text(text: str) -> str:
	marker = "YOUR TRANSACTIONS"
	end_markers = [
		"REWARDS SUMMARY",
		"SPECIAL BENEFITS",
		"IMPORTANT INFORMATION",
		"REWARDS",
	]

	collected: list[str] = []
	start = 0
	while True:
		idx = text.find(marker, start)
		if idx == -1:
			break
		end = len(text)
		for mark in end_markers:
			candidate = text.find(mark, idx + len(marker))
			if candidate != -1:
				end = min(end, candidate)
		collected.append(text[idx:end])
		start = end
	return "\n".join(collected) if collected else ""


def _extract_transactions(text: str) -> list[dict]:
	section = _collect_transaction_text(text)
	if not section:
		return []

	row_regex = re.compile(r"^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<body>.+)$", re.MULTILINE)
	amount_regex = re.compile(
		r"(?P<amount>-?[₹rRs`\.\s]*[\d,]+(?:\.\d{1,2})?)\s*(?P<flag>CR|DR)?$",
		re.IGNORECASE,
	)

	transactions: list[dict] = []
	matches = list(row_regex.finditer(section))
	for idx, match in enumerate(matches):
		start = match.start()
		end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section)
		chunk = section[start:end].strip()
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


def parse_idfc_statement(file_path: str) -> dict:
	document_text = get_document_text(file_path)
	lines = [ln for ln in document_text.splitlines()]

	name = _extract_name(lines)
	masked_card = _extract_masked_card(document_text)
	card_last4s = extract_last4s_from_pdf(file_path)

	statement_period_match = re.search(
		r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})",
		document_text,
	)
	if statement_period_match:
		statement_period = f"{statement_period_match.group(1)} - {statement_period_match.group(2)}"
	else:
		alt_period = re.search(
			r"From\s*[:\-]?\s*(\d{2}/\d{2}/\d{4}).*?To\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
			document_text,
			re.IGNORECASE | re.DOTALL,
		)
		statement_period = (
			f"{alt_period.group(1)} - {alt_period.group(2)}" if alt_period else ""
		)

	statement_date_match = re.search(
		r"Statement\s+Date\s*\n\s*([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{2}/\d{2}/\d{4})",
		document_text,
		re.IGNORECASE,
	)
	statement_date = _strip_artifacts(statement_date_match.group(1)) if statement_date_match else ""

	payment_due_match = re.search(
		r"Payment\s+Due\s+Date\s*\n\s*([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{2}/\d{2}/\d{4})",
		document_text,
		re.IGNORECASE,
	)
	if not payment_due_match:
		payment_due_match = re.search(
			r"Payment\s+Due\s+Date\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{2}/\d{2}/\d{4})",
			document_text,
			re.IGNORECASE,
		)
	payment_due_date = _strip_artifacts(payment_due_match.group(1)) if payment_due_match else ""

	total_amount_due = _extract_summary_amount("Total Amount Due", document_text)
	minimum_amount_due = _extract_summary_amount("Minimum Amount Due", document_text)

	credit_limit = _extract_summary_amount("Credit Limit", document_text)
	available_credit = _extract_summary_amount("Available Credit Limit", document_text)
	cash_limit = _extract_summary_amount("Cash Limit", document_text)
	available_cash = _extract_summary_amount("Available Cash", document_text)

	transactions = _extract_transactions(document_text)

	return {
		"file_path": file_path,
		"card_last4_digits": card_last4s,
		"masked_card_number": masked_card,
		"name": name,
		"statement_period": statement_period,
		"statement_date": statement_date,
		"payment_due_date": payment_due_date,
		"total_amount_due": total_amount_due,
		"minimum_amount_due": minimum_amount_due,
		"credit_limit": credit_limit,
		"available_credit_limit": available_credit,
		"cash_limit": cash_limit,
		"available_cash": available_cash,
		"transactions": transactions,
	}


if __name__ == "__main__":
	parsed = parse_idfc_statement("pdfs/idfc-2.pdf")
	print(parsed)