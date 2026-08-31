"""
Forensic PDF Document Parser.
Extracts sections, financial tables, risk disclosures, objects of the issue, and promoter background.
Uses pdfplumber and pypdf with zero external costs.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import pypdf
import pdfplumber
from src.common.logging import logger


class DocumentParser:
    """Extracts structured sections and tables from IPO filings."""

    SECTIONS = [
        "OBJECTS OF THE ISSUE",
        "FINANCIAL INFORMATION",
        "RISK FACTORS",
        "OUR BUSINESS",
        "OUTSTANDING LITIGATION",
        "OUR PROMOTERS AND MANAGEMENT",
        "CAPITAL STRUCTURE",
    ]

    @staticmethod
    def extract_text_and_pages(file_path: str) -> Dict[str, Any]:
        """Extract full text with page-number mapping."""
        pages_content = []
        path = Path(file_path)
        if not path.exists():
            return {"page_count": 0, "pages": []}

        try:
            reader = pypdf.PdfReader(str(path))
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                pages_content.append({"page_number": idx + 1, "text": text})
            return {"page_count": len(pages_content), "pages": pages_content}
        except Exception as e:
            logger.warning(f"pypdf extraction error on {file_path}: {e}")
            return {"page_count": 0, "pages": []}

    @staticmethod
    def extract_tables_from_page(file_path: str, page_number: int) -> List[List[List[Optional[str]]]]:
        """Extract table structures from a specific PDF page using pdfplumber."""
        path = Path(file_path)
        if not path.exists():
            return []

        try:
            with pdfplumber.open(str(path)) as pdf:
                if page_number <= len(pdf.pages):
                    page = pdf.pages[page_number - 1]
                    tables = page.extract_tables()
                    return tables or []
        except Exception as e:
            logger.warning(f"pdfplumber table extraction error on page {page_number}: {e}")
        return []

    @classmethod
    def identify_key_sections(cls, pages: List[Dict[str, Any]]) -> Dict[str, int]:
        """Locate starting page numbers for critical prospectus sections."""
        section_pages: Dict[str, int] = {}
        for page in pages:
            text_upper = page["text"].upper()
            for section in cls.SECTIONS:
                if section not in section_pages and section in text_upper:
                    section_pages[section] = page["page_number"]
        return section_pages
