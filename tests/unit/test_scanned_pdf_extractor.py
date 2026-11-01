"""Unit tests for scanned image PDF detection and OCR flagging."""
from io import BytesIO
import tempfile
from pathlib import Path
from PIL import Image as PILImage
from reportlab.platypus import SimpleDocTemplate, Image as RLImage
from reportlab.lib.pagesizes import letter

from src.documents.extractor import extract_pdf_candidate_evidence


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
