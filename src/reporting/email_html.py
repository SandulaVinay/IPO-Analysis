from html import escape
import re

def digest_email_html(report_markdown: str, title: str = "Daily Indian IPO Status Digest") -> str:
    """Convert the markdown digest report into a beautifully styled HTML email."""
    lines = report_markdown.splitlines()
    body_elements = []

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            body_elements.append('<div style="height:10px;"></div>')
            continue

        if line_clean.startswith("# "):
            h1_text = escape(line_clean[2:].strip())
            body_elements.append(
                f'<h1 style="font-size:20px;color:#1E3A8A;margin:18px 0 8px 0;border-bottom:2px solid #DBEAFE;padding-bottom:6px;">{h1_text}</h1>'
            )
        elif line_clean.startswith("## "):
            h2_text = escape(line_clean[3:].strip())
            body_elements.append(
                f'<h2 style="font-size:16px;color:#1E293B;margin:16px 0 6px 0;border-bottom:1px solid #E2E8F0;padding-bottom:4px;">{h2_text}</h2>'
            )
        elif line_clean.startswith("### "):
            h3_text = escape(line_clean[4:].strip())
            body_elements.append(
                f'<h3 style="font-size:14px;color:#0F766E;margin:12px 0 4px 0;">{h3_text}</h3>'
            )
        elif line_clean.startswith("- "):
            item_text = line_clean[2:].strip()
            # replace markdown bold
            item_text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item_text)
            # replace markdown links
            item_text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2" style="color:#2563EB;text-decoration:underline;">\1</a>', item_text)
            body_elements.append(
                f'<li style="font-size:13px;line-height:1.6;margin-bottom:4px;color:#334155;">{item_text}</li>'
            )
        else:
            p_text = line_clean
            p_text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p_text)
            p_text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2" style="color:#2563EB;text-decoration:underline;">\1</a>', p_text)
            if "warning:" in p_text.lower():
                body_elements.append(
                    f'<div style="background:#FEF3C7;border-left:4px solid #F59E0B;padding:10px 14px;border-radius:4px;margin:10px 0;font-size:13px;color:#92400E;">{p_text}</div>'
                )
            elif "important limitation" in p_text.lower() or "not an investment recommendation" in p_text.lower():
                body_elements.append(
                    f'<div style="background:#F1F5F9;border-left:4px solid #64748B;padding:10px 14px;border-radius:4px;margin:10px 0;font-size:12px;color:#475569;">{p_text}</div>'
                )
            else:
                body_elements.append(
                    f'<p style="font-size:13px;line-height:1.55;color:#334155;margin:4px 0;">{p_text}</p>'
                )

    content_html = "\n".join(body_elements)
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
</head>
<body style="margin:0;padding:20px;background-color:#F8FAFC;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1E293B;">
  <div style="max-width:680px;margin:0 auto;background:#FFFFFF;border:1px solid #E2E8F0;border-radius:8px;padding:24px 30px;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
    <div style="margin-bottom:16px;">
      <span style="display:inline-block;background:#DBEAFE;color:#1E40AF;font-size:11px;font-weight:bold;padding:3px 8px;border-radius:12px;text-transform:uppercase;letter-spacing:0.5px;">IPO Intelligence</span>
    </div>
    {content_html}
    <hr style="border:none;border-top:1px solid #E2E8F0;margin:24px 0 16px 0;">
    <p style="font-size:11px;color:#94A3B8;margin:0;line-height:1.4;">This automated status digest was dispatched by the IPO Analysis platform via verified SMTP transport. A standalone PDF copy is attached for offline archiving.</p>
  </div>
</body>
</html>"""
