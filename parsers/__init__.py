from .axis_parser import parse_axis_statement
from .idfc_parser import parse_idfc_statement
from .hdfc_parser import parse_hdfc_statement
from .icici_parser import parse_icici_statement
from .rbl_parser import parse_rbl_statement

PARSERS = {
    "axis": parse_axis_statement,
    "idfc": parse_idfc_statement,
    "hdfc": parse_hdfc_statement,
    "icici": parse_icici_statement,
    "rbl": parse_rbl_statement,
}

def parse_statement(issuer: str, path: str) -> dict:
    try:
        parser = PARSERS[issuer.lower()]
    except KeyError:
        raise ValueError("Unsupported issuer")
    return parser(path)