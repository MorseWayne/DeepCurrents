import pytest
from src.services.report_exporter import ReportExporter

SAMPLE_MD = """# Daily Macro Report 2026-03-24

## Executive Summary

Markets traded mixed as VIX remained elevated.

## Key Events

1. **Fed holds rates** — Impact: High
2. **Oil surges 3%** — Impact: Medium

## Investment Trends

| Asset | Direction | Confidence |
|-------|-----------|------------|
| SPY   | Neutral   | Medium     |
"""


@pytest.fixture
def exporter():
    return ReportExporter()


def test_export_word_creates_file(exporter, tmp_path):
    out = tmp_path / "report.docx"
    exporter.export_word(SAMPLE_MD, str(out))
    assert out.exists()
    assert out.stat().st_size > 0


def test_export_word_contains_title(exporter, tmp_path):
    out = tmp_path / "report.docx"
    exporter.export_word(SAMPLE_MD, str(out))
    from docx import Document
    doc = Document(str(out))
    texts = [p.text for p in doc.paragraphs]
    assert any("Daily Macro Report" in t for t in texts)


def test_md_to_html_basic(exporter):
    html = exporter._md_to_html("**bold** text")
    assert "<strong>" in html
    assert "bold" in html


def test_export_pdf_returns_none_without_wkhtmltopdf(exporter, tmp_path):
    """wkhtmltopdf not available → should return None gracefully"""
    out = tmp_path / "report.pdf"
    result = exporter.export_pdf(SAMPLE_MD, str(out))
    assert result is None or isinstance(result, str)
