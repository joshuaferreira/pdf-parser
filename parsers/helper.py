import fitz  # PyMuPDF
import os 
import re

def get_pdf_page_count(file_path):
    """
    Returns the number of pages in a PDF file.
    :param file_path: Path to the PDF file.
    :return: Number of pages in the PDF.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")
    
    with fitz.open(file_path) as pdf_document:
        return pdf_document.page_count

def extract_text_from_page(file_path, page_number):
    """
    Extracts text from a specific page in a PDF file.
    :param file_path: Path to the PDF file.
    :param page_number: Page number to extract text from (0-indexed).
    :return: Extracted text from the specified page.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")
    
    with fitz.open(file_path) as pdf_document:
        if page_number < 0 or page_number >= pdf_document.page_count:
            raise ValueError(f"Page number {page_number} is out of range.")
        
        page = pdf_document.load_page(page_number)
        return page.get_text()

    
pattern = re.compile(r'(?:X{4}|\*{4}|x{4})(?:[\s-]*)+(\d{4})\b', re.IGNORECASE)

def find_last4s(text):
    return list(dict.fromkeys(m.group(1) for m in pattern.finditer(text)))


def extract_last4s_from_pdf(file_path):
    """Return the ordered list of unique last-4 card digits found in the PDF."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")

    last4s: list[str] = []
    with fitz.open(file_path) as pdf_document:
        for page_number in range(pdf_document.page_count):
            page_text = pdf_document.load_page(page_number).get_text()
            for digits in find_last4s(page_text):
                if digits not in last4s:
                    last4s.append(digits)

    return last4s

