"""Report exporters use the same result schema as the browser and CLI."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from html import escape
from typing import Any
from urllib.parse import quote

from sentinel import __version__
from sentinel.scanner.models import ScanResult, Severity


def to_json(result: ScanResult) -> bytes:
    """Export the full normalized result including failure state."""
    return json.dumps(result.to_dict(), indent=2, ensure_ascii=False).encode("utf-8")


def to_sarif(result: ScanResult) -> bytes:
    """Export SARIF 2.1.0 with rule metadata and source evidence."""
    rules = {f.rule_id: f for f in result.findings}
    indices = {rule: i for i, rule in enumerate(rules)}
    run = {
        "tool": {
            "driver": {
                "name": "Solidity Sentinel",
                "version": __version__,
                "informationUri": "https://github.com/ShkS44D/Solidity-Sentinel",
                "rules": [
                    {
                        "id": rule,
                        "name": f.title,
                        "shortDescription": {"text": f.title},
                        "fullDescription": {"text": f.description},
                        "help": {"text": f.remediation},
                        "properties": {
                            "tags": [f"SWC-{f.swc}"] if f.swc else [],
                            "precision": f.confidence.value,
                        },
                    }
                    for rule, f in rules.items()
                ],
            }
        },
        "invocations": [
            {
                "executionSuccessful": result.state.value == "completed",
                **(
                    {
                        "toolExecutionNotifications": [
                            {
                                "level": "error",
                                "message": {"text": result.diagnostics or result.state.value},
                            }
                        ]
                    }
                    if result.state.value != "completed"
                    else {}
                ),
            }
        ],
        "results": [
            {
                "ruleId": f.rule_id,
                "ruleIndex": indices[f.rule_id],
                "level": "error"
                if f.severity in {Severity.CRITICAL, Severity.HIGH}
                else "warning"
                if f.severity in {Severity.MEDIUM, Severity.LOW}
                else "note",
                "message": {"text": f.description + "\nFix: " + f.remediation},
                "partialFingerprints": {"sentinel/v1": f.id},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": quote(f.file, safe="/")},
                            "region": {"startLine": f.line_start, "endLine": f.line_end},
                        }
                    }
                ],
                "properties": {
                    "severity": f.severity.value,
                    "confidence": f.confidence.value,
                    "cwe": f.cwe,
                    "swc": f.swc,
                },
            }
            for f in result.findings
        ],
    }
    return json.dumps(
        {
            "version": "2.1.0",
            "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json",
            "runs": [run],
        },
        indent=2,
    ).encode()


def to_markdown(result: ScanResult) -> bytes:
    """Export a readable report without executable raw HTML."""
    lines = [
        "# Solidity Sentinel scan report",
        "",
        f"File: {escape(result.filename)}",
        f"State: {result.state.value}",
        "",
    ]
    if result.score is not None:
        lines += [
            f"Observed-risk score: {result.score}/100 | Grade {result.grade} | {result.risk} risk",
            "",
        ]
    else:
        lines += ["**Unscored: analysis did not complete.**", escape(result.diagnostics), ""]
    lines += ["## Metadata", "", "```json", json.dumps(result.metadata, indent=2), "```", ""]
    for finding in result.findings:
        lines += [
            f"## {finding.severity.value.upper()}: {escape(finding.title)}",
            "",
            f"Rule: {finding.rule_id} | Confidence: {finding.confidence.value} | {escape(finding.file)}:{finding.line_start}-{finding.line_end}",
            "",
            escape(finding.description),
            "",
            f"**How to fix:** {escape(finding.remediation)}",
            "References: "
            + " · ".join(
                filter(
                    None,
                    [
                        f"[SWC-{finding.swc}](https://swcregistry.io/docs/SWC-{finding.swc}/)"
                        if finding.swc
                        else None,
                        f"[CWE-{finding.cwe}](https://cwe.mitre.org/data/definitions/{finding.cwe}.html)"
                        if finding.cwe
                        else None,
                    ],
                )
            ),
            "",
            "<pre>" + escape(finding.snippet) + "</pre>",
            "",
        ]
    lines += [
        "## Score breakdown",
        "",
        "```json",
        json.dumps(result.breakdown, indent=2),
        "```",
        "",
        "Static analysis is not a replacement for a manual audit.",
    ]
    return "\n".join(lines).encode("utf-8")


def to_pdf(result: ScanResult) -> bytes:
    """Build a paginated PDF with safe text, wrapped source, and remediation."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        KeepTogether,
        Paragraph,
        Preformatted,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    stream = io.BytesIO()

    def pdf_text(value: object) -> str:
        # Standard PDF fonts cannot cover all Unicode: preserve unsupported source
        # as explicit escapes rather than silently rendering black boxes.
        return escape(str(value).encode("ascii", errors="backslashreplace").decode())

    def metadata_text(key: str, value: Any) -> str:
        if key == "submitted_at":
            return datetime.fromtimestamp(float(value), UTC).strftime("%Y-%m-%d %H:%M UTC")
        if isinstance(value, dict):
            return "<br/>".join(
                f"{pdf_text(name)}: {pdf_text(item)}" for name, item in value.items()
            )
        if isinstance(value, list):
            return "<br/>".join(pdf_text(item) for item in value) or "None"
        return pdf_text(value)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("CodeSmall", fontName="Courier", fontSize=7, leading=10))
    styles["Title"].textColor = colors.HexColor("#14532d")
    styles["Title"].alignment = TA_LEFT
    styles["BodyText"].leading = 14
    story = [
        Paragraph("Solidity Sentinel", styles["Title"]),
        Paragraph("Static analysis report", styles["Heading2"]),
        Paragraph(pdf_text(result.filename), styles["BodyText"]),
        Spacer(1, 16),
    ]
    headline = (
        f"{result.score}/100 - Grade {result.grade} - {result.risk} risk"
        if result.score is not None
        else f"UNSCORED - {result.state.value}"
    )
    story += [Paragraph(pdf_text(headline), styles["Heading2"])]
    if result.diagnostics:
        story += [
            Paragraph(pdf_text(result.diagnostics).replace("\n", "<br/>"), styles["BodyText"])
        ]
    rows = [["Metadata", "Value"]] + [
        [key.replace("_", " ").title(), Paragraph(metadata_text(key, value), styles["BodyText"])]
        for key, value in result.metadata.items()
    ]
    table = Table(rows, colWidths=[140, 350], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcfce7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#14532d")),
            ]
        )
    )
    story += [Spacer(1, 12), table, Spacer(1, 18)]
    for finding in result.findings:
        first = len(story)
        story += [
            Paragraph(
                pdf_text(f"{finding.severity.value.upper()} - {finding.title}"), styles["Heading2"]
            ),
            Paragraph(
                pdf_text(
                    f"{finding.rule_id} | {finding.confidence.value} confidence | {finding.file}:{finding.line_start}-{finding.line_end}"
                ),
                styles["BodyText"],
            ),
            Paragraph(pdf_text(finding.description), styles["BodyText"]),
            Paragraph("<b>How to fix:</b> " + pdf_text(finding.remediation), styles["BodyText"]),
        ]
        refs = " / ".join(
            filter(
                None,
                [
                    f'<link href="https://swcregistry.io/docs/SWC-{escape(finding.swc)}/">SWC-{escape(finding.swc)}</link>'
                    if finding.swc
                    else None,
                    f'<link href="https://cwe.mitre.org/data/definitions/{escape(finding.cwe)}.html">CWE-{escape(finding.cwe)}</link>'
                    if finding.cwe
                    else None,
                ],
            )
        )
        if refs:
            story += [Paragraph(refs, styles["BodyText"])]
        if finding.snippet:
            wrapped = "\n".join(
                f"{finding.snippet_start + i:>4}  {line.encode('ascii', errors='backslashreplace').decode()}"
                for i, line in enumerate(finding.snippet.splitlines())
            )
            story += [
                Spacer(1, 6),
                Preformatted(wrapped, styles["CodeSmall"], maxLineLength=104),
                Spacer(1, 10),
            ]
        story[first:] = [KeepTogether(story[first:])]
    story += [Paragraph("Score breakdown", styles["Heading2"])]
    for group in result.breakdown:
        story += [
            Paragraph(
                pdf_text(
                    f"{group['rule_id']}: {group['instances']} instance(s), penalty {group['penalty']}, cap {group['cap']}"
                ),
                styles["BodyText"],
            )
        ]
    story += [
        Spacer(1, 16),
        Paragraph("Static analysis is not a replacement for a manual audit.", styles["BodyText"]),
    ]

    def footer(canvas: Any, doc: Any) -> None:
        canvas.setFont("Helvetica", 8)
        canvas.drawString(42, 25, "Solidity Sentinel | " + result.scan_id)
        canvas.drawRightString(553, 25, str(doc.page))

    SimpleDocTemplate(
        stream,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=42,
        title="Solidity Sentinel scan report",
        author="Solidity Sentinel",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


EXPORTERS = {
    "json": (to_json, "application/json"),
    "sarif": (to_sarif, "application/sarif+json"),
    "md": (to_markdown, "text/markdown; charset=utf-8"),
    "pdf": (to_pdf, "application/pdf"),
}
