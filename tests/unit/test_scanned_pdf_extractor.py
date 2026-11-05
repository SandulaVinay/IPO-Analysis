"""Unit tests for scanned image PDF detection and OCR flagging."""
from io import BytesIO
import tempfile
from pathlib import Path
from PIL import Image as PILImage
from reportlab.platypus import SimpleDocTemplate, Image as RLImage
from reportlab.lib.pagesizes import letter

from unittest.mock import MagicMock, patch
import sys

from src.documents.extractor import (
    extract_pdf_candidate_evidence,
    extract_scanned_pdf_ocr_text,
)


def test_scanned_pdf_without_text_is_detected_and_flags_ocr_required():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as img_file:
        img_path = Path(img_file.name)
        image = PILImage.new("RGB", (150, 150), color=(128, 128, 128))
        image.save(img_path, format="PNG")

    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        rl_img = RLImage(str(img_path), width=100, height=100)
        doc.build([rl_img])
        pdf_bytes = buffer.getvalue()

        result = extract_pdf_candidate_evidence(
            pdf_bytes,
            source_url="https://www.nseindia.com/scanned-filing.pdf",
        )

        assert result["is_scanned_image"] is True
        assert result["ocr_required"] is True
        assert result["status"] == "SCANNED_IMAGE_DETECTED"
        assert result["text_pages_extracted"] == 0
        assert result["evidence_count"] == 0
        assert "SCANNED_PDF_NEEDS_OCR" in (result["notice"] or "")
        assert result["verification_status"] == "UNVERIFIED"
    finally:
        if img_path.exists():
            img_path.unlink()


def test_blank_pdf_without_images_is_not_flagged_as_scanned_image():
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    result = extract_pdf_candidate_evidence(
        pdf_bytes,
        source_url="https://www.nseindia.com/blank.pdf",
    )
    assert result["is_scanned_image"] is False
    assert result["ocr_required"] is False
    assert result["status"] == "NO_CANDIDATES_FOUND"


def test_extract_scanned_pdf_ocr_text_returns_safe_notice_when_engine_missing():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as img_file:
        img_path = Path(img_file.name)
        image = PILImage.new("RGB", (100, 100), color=(200, 200, 200))
        image.save(img_path, format="PNG")

    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        rl_img = RLImage(str(img_path), width=80, height=80)
        doc.build([rl_img])
        pdf_bytes = buffer.getvalue()

        # Without pytesseract installed, it gracefully returns OCR_TOOL_UNAVAILABLE
        res = extract_scanned_pdf_ocr_text(pdf_bytes, source_url="https://sebi.gov.in/doc.pdf")
        assert res["ocr_available"] is False
        assert res["status"] in ("OCR_TOOL_UNAVAILABLE", "OCR_ENGINE_ERROR")
        assert "pytesseract" in (res.get("notice") or "").lower() or "tesseract" in (res.get("notice") or "").lower()
    finally:
        if img_path.exists():
            img_path.unlink()


def test_extract_scanned_pdf_ocr_text_with_mocked_ocr_success():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as img_file:
        img_path = Path(img_file.name)
        image = PILImage.new("RGB", (100, 100), color=(200, 200, 200))
        image.save(img_path, format="PNG")

    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        rl_img = RLImage(str(img_path), width=80, height=80)
        doc.build([rl_img])
        pdf_bytes = buffer.getvalue()

        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_string.return_value = "Revenue from operations was 1200 crores in FY25"

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            res = extract_scanned_pdf_ocr_text(pdf_bytes, source_url="https://sebi.gov.in/doc.pdf")
            assert res["status"] == "OCR_EXTRACTED"
            assert res["ocr_available"] is True
            assert res["text_pages_extracted"] >= 1
            assert res["evidence_count"] >= 1
            assert res["evidence"][0]["field_name"] == "revenue_from_operations"

            # Verify enable_ocr wiring in extract_pdf_candidate_evidence
            cand_res = extract_pdf_candidate_evidence(
                pdf_bytes,
                source_url="https://sebi.gov.in/doc.pdf",
                enable_ocr=True,
            )
            assert cand_res["status"] == "CANDIDATES_FOUND"
            assert cand_res["evidence_count"] >= 1
            assert cand_res["evidence"][0]["field_name"] == "revenue_from_operations"
    finally:
        if img_path.exists():
            img_path.unlink()

