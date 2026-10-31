"""Analyst-style email summaries for official financial-results filings.

Interpretations are deliberately conditional: percentage changes describe the figures,
while possible drivers are labelled as risks to investigate unless the filing proves them.
"""
from typing import Any, Dict, Optional


def _number(value: Optional[float], suffix: str = "", currency: str = "") -> str:
    if value is None:
        return "Not available"
    return f"{currency}{value:,.2f}{suffix}"


def _change(value: Optional[float]) -> str:
    if value is None:
        return "Not available (comparable prior-period figure missing or zero)"
    direction = "increased" if value > 0 else "declined" if value < 0 else "was unchanged"
    return f"{direction} {abs(value):.2f}%"

 
def build_results_email(item: Dict[str, Any], metrics: Dict[str, Any], report_url: Optional[str] = None) -> tuple[str, str]:
    """Return a professional subject and market-analyst-style plain-text email body."""
    company = str(item.get("company_name") or item.get("symbol") or "Company")
    symbol = str(item.get("symbol") or "").strip()
    exchange = str(item.get("exchange") or "exchange").upper()
    period = str(item.get("period_ended") or "period not specified")
    category = str(item.get("relating_to") or item.get("period_type") or "period not specified")
    subject = f"Financial Results Alert | {company} ({symbol}) | {category} ended {period}"

    lines = [
        "Dear Investor,",
        "",
        f"An official financial-results filing has been identified for {company} ({symbol}) on {exchange}.",
        "",
        "EXECUTIVE SUMMARY",
    ]
    if metrics.get("status") == "EXTRACTED":
        revenue = metrics.get("revenue_cr")
        pat = metrics.get("pat_cr")
        revenue_yoy = metrics.get("revenue_yoy_pct")
        pat_yoy = metrics.get("pat_yoy_pct")
        revenue_qoq = metrics.get("revenue_qoq_pct")
        pat_qoq = metrics.get("pat_qoq_pct")
        cfo = metrics.get("cfo_cr")
        eps = metrics.get("eps")
        lines.extend([
            f"• Revenue from operations: INR {_number(revenue, ' Cr')}",
            f"• Profit after tax (PAT): INR {_number(pat, ' Cr')}",
            f"• Earnings per share (EPS): INR {_number(eps)}",
            f"• Operating cash flow: INR {_number(cfo, ' Cr')}",
            f"• Revenue year-on-year (YoY): {_change(revenue_yoy)}",
            f"• PAT year-on-year (YoY): {_change(pat_yoy)}",
            f"• Revenue quarter-on-quarter (QoQ): {_change(revenue_qoq)}",
            f"• PAT quarter-on-quarter (QoQ): {_change(pat_qoq)}",
            "",
            "ANALYST INTERPRETATION",
        ])
        findings = []
        if revenue_yoy is not None:
            if revenue_yoy < 0:
                findings.append("Revenue contracted YoY. This may indicate weaker volumes, pricing/realisation, or a less favourable business mix; the filing's segment and volume disclosures should be checked before attributing a cause.")
            elif revenue_yoy > 0:
                findings.append("Revenue grew YoY. Assess whether growth is supported by volumes and core operations rather than one-off income or changes in accounting presentation.")
            else:
                findings.append("Revenue was flat YoY; check whether volume growth, pricing, or mix changes offset one another.")
        if pat_yoy is not None:
            if pat_yoy < 0:
                findings.append("PAT declined YoY. If revenue was stable or higher, investigate input costs, employee costs, finance costs, exceptional items, tax, and margin compression. Lower profit can weaken valuation support if the decline persists.")
            elif pat_yoy > 0:
                findings.append("PAT grew YoY. Compare profit growth with revenue growth and operating cash flow to determine whether earnings growth is broad-based and cash-backed.")
        if revenue_qoq is not None and revenue_qoq < 0:
            findings.append("Revenue declined QoQ. This signals sequential moderation, but seasonality and the comparable quarter should be considered before treating it as a structural slowdown.")
        if pat_qoq is not None and pat_qoq < 0:
            findings.append("PAT declined QoQ. Review sequential margin movement, exceptional items, finance costs, and tax effects to identify whether the decline is operational or temporary.")
        if cfo is not None and pat is not None and cfo < 0 < pat:
            findings.append("Operating cash flow is negative despite positive PAT. This is a cash-conversion warning; examine receivables, inventory, payables, and working-capital movements.")
        if pat is not None and pat < 0:
            findings.append("The company reported a loss for this period. Assess the loss's recurring versus exceptional components, cash runway, debt obligations, and the path to profitability.")
        if not findings:
            findings.append("The extracted figures do not support a clear directional conclusion on their own. Compare margins, cash conversion, debt, segment performance, and management commentary with prior periods.")
        lines.extend(f"• {finding}" for finding in findings)
        lines.extend([
            "",
            "IMPORTANT LIMITATIONS",
            "• These observations describe reported figures; they do not establish the cause of a movement unless the filing explicitly supports it.",
            "• QoQ comparisons are shown only when a comparable prior-quarter value was available. Missing figures are not estimated.",
            "• Confirm reporting period, units, and standalone/consolidated basis in the original filing before relying on the comparison.",
        ])
    else:
        lines.extend([
            "Automated financial metrics could not be reliably extracted from the detected filing.",
            "No growth, decline, or investment conclusion is inferred from the announcement headline alone.",
            "",
            "ANALYST REVIEW PRIORITIES",
            "• Confirm the reporting period and whether the figures are standalone or consolidated.",
            "• Compare revenue, EBITDA/operating margin, PAT, EPS, and operating cash flow against the prior quarter and corresponding prior-year quarter.",
            "• Review debt, working-capital movement, exceptional items, auditor remarks, segment disclosures, and management commentary.",
            "• Treat all figures as unverified until checked against the official filing.",
        ])

    lines.extend([
        "",
        "FILING DETAILS",
        f"Company: {company} ({symbol})",
        f"Exchange: {exchange}",
        f"Reporting period: {period}",
        f"Period/category: {category}",
        f"Announcement time: {item.get('broadcast_time') or 'Not specified'}",
        f"Audit status: {item.get('audit_status') or 'Not specified'}",
        f"Statement basis: {item.get('consolidation') or 'Not specified'}",
        f"Official filing: {item.get('attachment_url') or item.get('source_url') or 'Not available'}",
    ])
    if item.get("details_url"):
        lines.append(f"Filing details: {item['details_url']}")
    if item.get("headline"):
        lines.append(f"Announcement: {item['headline']}")
    if report_url:
        lines.append(f"Full report / workflow artifact: {report_url}")
    lines.extend([
        "",
        "Please review the source filing and accompanying report before drawing an investment conclusion. This alert is for informational research purposes only and is not a buy/sell recommendation.",
        "",
        "Kind regards,",
        "Market Research & IPO Analysis Team",
    ])
    return subject, "\n".join(lines) + "\n"
