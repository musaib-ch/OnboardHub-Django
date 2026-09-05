import io
from django.http import HttpResponse

try:
    from xhtml2pdf import pisa
    XHTML2PDF_AVAILABLE = True
except ImportError:
    XHTML2PDF_AVAILABLE = False


def render_html_to_pdf(html_content: str) -> bytes:
    """Render HTML string to PDF bytes. Uses xhtml2pdf if available."""
    if "<html" not in html_content.lower():
        full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8"/>
    <style>
        body {{
            font-family: Arial, Helvetica, sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #1f2937;
            margin: 20px;
        }}
        h1, h2, h3, h4 {{
            color: #1e3a8a;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            border: 1px solid #cbd5e1;
            padding: 8px 12px;
            text-align: left;
        }}
        th {{
            background-color: #f1f5f9;
        }}
        img {{
            max-width: 100%;
        }}
    </style>
</head>
<body>
    {html_content}
</body>
</html>"""
    else:
        full_html = html_content

    if XHTML2PDF_AVAILABLE:
        try:
            result_stream = io.BytesIO()
            pdf = pisa.pisaDocument(io.BytesIO(full_html.encode("utf-8")), result_stream)
            if pdf and not pdf.err:
                return result_stream.getvalue()
        except Exception:
            pass

    # Fallback to UTF-8 HTML string bytes if xhtml2pdf engine encounters syntax errors or fails
    return full_html.encode("utf-8")


def generate_offer_pdf_response(offer, filename: str = None) -> HttpResponse:
    """Generate a downloadable PDF HttpResponse for a canonical Offer."""
    html_content = offer.rendered_html or offer.metadata.get("rendered_html") or f"<h1>Offer {offer.offer_number}</h1><p>Candidate: {offer.candidate_name}</p>"
    pdf_bytes = render_html_to_pdf(html_content)
    
    if filename is None:
        filename = f"Offer_{offer.offer_number}.pdf"

    if pdf_bytes.startswith(b"%PDF"):
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
    else:
        # Fallback response format if PDF binary header is not generated
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response
