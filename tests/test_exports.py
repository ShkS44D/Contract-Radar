"""Export round trips preserve state, evidence, and escaped code."""

import io
import json

from pypdf import PdfReader

from sentinel.scanner.models import Confidence, Finding, ScanResult, ScanState, Severity
from sentinel.scanner.scoring import apply_score
from sentinel.services.exports import to_markdown, to_pdf, to_sarif


def test_pdf_text_and_pagination_roundtrip():
    findings = [
        Finding(
            f"rule/{i}",
            f"Issue {i}",
            Severity.MEDIUM,
            Confidence.HIGH,
            "Plain explanation",
            "Concrete fix",
            "A.sol",
            i + 1,
            i + 1,
            '// Unicode: λ\n<script>alert("x")</script>',
            swc="104",
            cwe="252",
        )
        for i in range(10)
    ]
    result = apply_score(
        ScanResult(
            "id",
            ScanState.COMPLETED,
            "A.sol",
            findings,
            {"compilers": {"A.sol": "0.8.30"}, "warnings": [], "submitted_at": 0},
        )
    )
    reader = PdfReader(io.BytesIO(to_pdf(result)))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert len(reader.pages) > 1
    assert "Issue 0" in text and "Issue 9" in text
    assert "Concrete fix" in text and "1970-01-01 00:00 UTC" in text
    assert "\\u03bb" in text and '<script>alert("x")</script>' in text
    assert any(page.get("/Annots") for page in reader.pages)
    markdown = to_markdown(result).decode()
    assert "[SWC-104]" in markdown and "&lt;script&gt;" in markdown
    sarif = json.loads(to_sarif(result))
    assert sarif["runs"][0]["results"][0]["partialFingerprints"]["sentinel/v1"] == findings[0].id
