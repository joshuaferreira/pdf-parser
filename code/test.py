import os
import pandas as pd
import helper
import pdfplumber
import re
import spacy
nlp = spacy.load("en_core_web_sm")
import fitz  # PyMuPDF

filename = "pdfs/idfc-1.pdf"

def get_tables_from_page(file_path: str) -> list[pd.DataFrame]:
    """Extract tables from a specific page in the PDF and return them as a list of DataFrames."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")

    tables = []
    with pdfplumber.open(file_path) as pdf:
        for page_number in range(len(pdf.pages)):
            if page_number < 0 or page_number >= len(pdf.pages):
                raise ValueError(f"Page number {page_number} is out of range.")

            page = pdf.pages[page_number]
            extracted_tables = page.extract_tables()

            for table in extracted_tables:
                df = pd.DataFrame(table[1:], columns=table[0])  # First row as header
                tables.append(df)

    return tables



print(get_tables_from_page(filename))