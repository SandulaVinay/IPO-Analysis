"""
Multi-Format Report Generation Engine.
Generates:
1. Executive Summary (Fast decision overview)
2. Full Forensic Report (Comprehensive evidence-backed analysis with source links & page citations)
3. Copy Mode (Clean plain-text format optimized for WhatsApp, Notes, and messaging apps)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class ReportGenerator:
    """Formats IPO assessment outputs into distinct delivery formats."""

    @staticmethod
    def generate_executive_summary(data: Dict[str, Any]) -> str:
        """Format A: Executive Summary."""
        ipo = data.get("ipo", {})
        score_data = data.get("score_data", {})
        horizons = score_data.get("horizons", {})
        gmp = data.get("gmp", {})

        verdict_emoji = "🟢" if score_data.get("verdict") == "ATTRACTIVE" else ("🟡" if score_data.get("verdict") == "NEUTRAL" else ("🔴" if score_data.get("verdict") == "AVOID" else "⚪"))

        return f"""# 📊 IPO Executive Summary: {ipo.get('company_name')} ({ipo.get('symbol')})

**Assessment**: {verdict_emoji} **{score_data.get('verdict', 'UNABLE_TO_ASSESS')}** | **Overall Score**: {score_data.get('overall_score')}/10 | **Confidence**: {data.get('confidence_level', 'HIGH')}

### Key Issue Details
- **Application Window**: {ipo.get('verified_open_date')} to {ipo.get('verified_close_date')}
- **Price Band**: ₹{ipo.get('min_price')} – ₹{ipo.get('max_price')}
- **Market Lot**: {ipo.get('lot_size')} shares (Min Investment: ₹{round(ipo.get('min_price', 0)*ipo.get('lot_size', 0), 2):,})
- **Total Issue Size**: ₹{ipo.get('issue_size_cr')} Cr (Fresh: ₹{ipo.get('fresh_issue_cr')} Cr | OFS: ₹{ipo.get('ofs_cr')} Cr)
- **GMP Signal**: ₹{gmp.get('gmp_value', 'N/A')} (~{gmp.get('potential_listing_gain_pct', 'N/A')}% Est. Listing Gain)

### Multi-Horizon Scores
- **Company Quality**: {horizons.get('company_quality', 'N/A')}/10
- **IPO Attractiveness**: {horizons.get('ipo_attractiveness', 'N/A')}/10
- **Listing Opportunity**: {horizons.get('listing_opportunity', 'N/A')}/10
- **Long-Term Opportunity**: {horizons.get('long_term_opportunity', 'N/A')}/10
"""

    @staticmethod
    def generate_full_report(data: Dict[str, Any]) -> str:
        """Format B: Full Forensic Evidence-Backed Analysis Report."""
        ipo = data.get("ipo", {})
        score_data = data.get("score_data", {})
        pillars = score_data.get("pillar_scores", {})
        horizons = score_data.get("horizons", {})
        gmp = data.get("gmp", {})
        biz = data.get("business", {})
        fin = data.get("financials", {})
        mgmt = data.get("management", {})
        struct = data.get("structure", {})
        val = data.get("valuation", {})
        anomalies = data.get("anomalies", [])
        risks = data.get("risks", [])
        yt_videos = data.get("youtube_videos", [])

        verdict_emoji = "🟢" if score_data.get("verdict") == "ATTRACTIVE" else ("🟡" if score_data.get("verdict") == "NEUTRAL" else ("🔴" if score_data.get("verdict") == "AVOID" else "⚪"))

        report = f"""# 📑 Forensic IPO Intelligence & Research Report
## {ipo.get('company_name')} ({ipo.get('symbol')})

**Generated on**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | **Source Verification**: VERIFIED | **Confidence**: {data.get('confidence_level', 'HIGH')}

---

## 1. Executive Verdict & Scoring Matrix

| Dimension | Score | Weight | Weighted Score |
| :--- | :--- | :--- | :--- |
| **Business Quality** | {pillars.get('business_quality', 'N/A')}/10 | 20% | {round(pillars.get('business_quality', 0)*0.20, 2)} |
| **Financial Quality** | {pillars.get('financial_quality', 'N/A')}/10 | 20% | {round(pillars.get('financial_quality', 0)*0.20, 2)} |
| **Management & Governance** | {pillars.get('management_governance', 'N/A')}/10 | 10% | {round(pillars.get('management_governance', 0)*0.10, 2)} |
| **IPO Issue Structure** | {pillars.get('ipo_structure', 'N/A')}/10 | 10% | {round(pillars.get('ipo_structure', 0)*0.10, 2)} |
| **Valuation & Multiples** | {pillars.get('valuation', 'N/A')}/10 | 20% | {round(pillars.get('valuation', 0)*0.20, 2)} |
| **Growth & Industry Moat** | {pillars.get('growth_industry', 'N/A')}/10 | 10% | {round(pillars.get('growth_industry', 0)*0.10, 2)} |
| **Risk Factors** | {pillars.get('risk', 'N/A')}/10 | 5% | {round(pillars.get('risk', 0)*0.05, 2)} |
| **Market Sentiment** | {pillars.get('market_sentiment', 'N/A')}/10 | 5% | {round(pillars.get('market_sentiment', 0)*0.05, 2)} |
| **OVERALL COMPOSITE** | **{score_data.get('overall_score', 'N/A')}/10** | **100%** | **{score_data.get('overall_score', 'N/A')}** |

**Final Assessment**: {verdict_emoji} **{score_data.get('verdict')}**

---

## 2. Issue Structure & Timeline
- **Open Date**: {ipo.get('verified_open_date')}
- **Close Date**: {ipo.get('verified_close_date')}
- **Price Band**: ₹{ipo.get('min_price')} – ₹{ipo.get('max_price')}
- **Lot Size**: {ipo.get('lot_size')} shares
- **Total Issue Size**: ₹{ipo.get('issue_size_cr')} Cr
  - **Fresh Issue**: ₹{ipo.get('fresh_issue_cr')} Cr ({struct.get('fresh_issue_pct', 'N/A')}%)
  - **Offer For Sale (OFS)**: ₹{ipo.get('ofs_cr')} Cr ({struct.get('ofs_pct', 'N/A')}%)

---

## 3. Financial Analysis & Cash Conversion
- **Revenue CAGR**: {fin.get('revenue_cagr', 'N/A')}%
- **PAT CAGR**: {fin.get('pat_cagr', 'N/A')}%
- **Earnings Quality Score**: {fin.get('earnings_quality_score', 'N/A')}/10

### Key Financial Insights
"""
        for ins in fin.get("insights", []):
            report += f"- {ins}\n"

        report += "\n## 4. Valuation Multiples vs Listed Peers\n"
        report += f"- **Post-IPO Market Cap**: ₹{val.get('post_ipo_market_cap_cr', 'N/A')} Cr\n"
        report += f"- **Enterprise Value**: ₹{val.get('enterprise_value_cr', 'N/A')} Cr\n"
        report += f"- **P/E Ratio**: {val.get('pe_ratio', 'N/A')}x\n"
        report += f"- **EV/EBITDA**: {val.get('ev_ebitda', 'N/A')}x\n"
        report += f"- **Peer Premium/Discount**: {val.get('pe_premium_discount_pct', 'N/A')}%\n"

        if anomalies:
            report += "\n## 5. Forensic Red Flags & Accounting Anomalies\n"
            for anom in anomalies:
                report += f"- **{anom.get('title')}** ({anom.get('severity')}): {anom.get('explanation')} *[Evidence: {anom.get('evidence')}]*\n"

        report += "\n## 6. Key Investment Risks\n"
        for r in risks:
            report += f"- **{r.get('title')}** (Severity: {r.get('severity')}): {r.get('citation')}\n"

        report += "\n## 7. Market Sentiment & GMP Signal\n"
        report += f"- **GMP Value**: ₹{gmp.get('gmp_value', 'N/A')}\n"
        report += f"- **Estimated Listing Gain**: ~{gmp.get('potential_listing_gain_pct', 'N/A')}%\n"
        report += f"- *{gmp.get('disclaimer')}*\n"

        if yt_videos:
            report += "\n## 8. YouTube Independent Research & Video Commentary\n"
            for vid in yt_videos:
                report += f"- [{vid.get('channel_name')}: {vid.get('title')}]({vid.get('video_url')})\n"

        return report

    @staticmethod
    def generate_copy_mode(data: Dict[str, Any]) -> str:
        """Format C: Copy Mode (Plain-text formatted for WhatsApp, Notes, Messaging apps)."""
        ipo = data.get("ipo", {})
        score_data = data.get("score_data", {})
        gmp = data.get("gmp", {})
        fin = data.get("financials", {})
        struct = data.get("structure", {})
        val = data.get("valuation", {})
        yt = data.get("youtube_videos", [])

        verdict_emoji = "🟢" if score_data.get("verdict") == "ATTRACTIVE" else ("🟡" if score_data.get("verdict") == "NEUTRAL" else ("🔴" if score_data.get("verdict") == "AVOID" else "⚪"))

        copy_text = f"""🚨 NEW IPO ALERT: {ipo.get('company_name')}

Application:
{ipo.get('verified_open_date')} – {ipo.get('verified_close_date')}

Price:
₹{ipo.get('min_price')}–{ipo.get('max_price')}

Lot:
{ipo.get('lot_size')} shares

Minimum Investment:
₹{round(ipo.get('min_price', 0)*ipo.get('lot_size', 0), 2):,}

Issue Size:
₹{ipo.get('issue_size_cr')} Cr (Fresh: ₹{ipo.get('fresh_issue_cr')} Cr | OFS: ₹{ipo.get('ofs_cr')} Cr)

Assessment:
{verdict_emoji} {score_data.get('verdict')}

Overall Score:
{score_data.get('overall_score')}/10

Confidence:
{data.get('confidence_level', 'HIGH')}

GMP:
₹{gmp.get('gmp_value', 'N/A')} (~{gmp.get('potential_listing_gain_pct', 'N/A')}% Est. Listing Gain)

KEY POSITIVES:
✅ Revenue CAGR: {fin.get('revenue_cagr', 'N/A')}%
✅ Valuation P/E: {val.get('pe_ratio', 'N/A')}x
✅ Fresh Issue: {struct.get('fresh_issue_pct', 'N/A')}%

KEY RISKS:
⚠️ Risk Score: {score_data.get('pillar_scores', {}).get('risk', 'N/A')}/10
⚠️ OFS Portion: {struct.get('ofs_pct', 'N/A')}%

YOUTUBE REVIEWS:
"""
        for v in yt[:2]:
            copy_text += f"• {v.get('channel_name')}: {v.get('video_url')}\n"

        copy_text += "\nFull evidence and analysis recorded."
        return copy_text.strip()
