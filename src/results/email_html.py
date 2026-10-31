from html import escape

def results_email_html(plain_text: str) -> str:
    """Build a styled HTML alternative with bold headings and field labels."""
    headings = {"EXECUTIVE SUMMARY", "ANALYST INTERPRETATION", "IMPORTANT LIMITATIONS", "ANALYST REVIEW PRIORITIES", "FILING DETAILS"}
    rows = []
    for raw in plain_text.splitlines():
        line = raw.strip()
        if not line:
            rows.append('<div style="height:8px"></div>')
            continue
        safe = escape(line)
        if line in headings:
            rows.append(f'<h3 style="font: bold 15px Arial;color:#17365D;border-bottom:1px solid #D9E2F3;padding-bottom:5px">{safe}</h3>')
            continue
        if ":" in line:
            label, value = safe.split(":", 1)
            safe = f"<strong>{label}:</strong>{value}"
        for phrase in ("Revenue contracted YoY.", "PAT declined YoY.", "Revenue declined QoQ.", "PAT declined QoQ.", "Operating cash flow is negative despite positive PAT.", "The company reported a loss for this period.", "not a buy/sell recommendation"):
            safe = safe.replace(escape(phrase), f"<strong>{escape(phrase)}</strong>")
        rows.append(f'<p style="font:14px/1.55 Arial,sans-serif;margin:5px 0">{safe}</p>')
    return '<html><body style="margin:0;padding:22px;color:#202124"><main style="max-width:760px;margin:auto">' + "\n".join(rows) + '</main></body></html>'
