from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GOLD = colors.HexColor('#b58863')
INK = colors.HexColor('#262421')
CREAM = colors.HexColor('#f0d9b5')


def table_pdf_response(filename, title, subtitle, header, rows, col_widths, align_left_cols=(1,)):
    """Build a single-table PDF in the club's style and return it as a download."""
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    doc = SimpleDocTemplate(response, pagesize=A4, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ClubTitle', parent=styles['Heading1'], fontSize=22, textColor=GOLD,
        spaceAfter=8, alignment=TA_CENTER, fontName='Helvetica-Bold',
    )
    sub_style = ParagraphStyle(
        'ClubSub', parent=styles['Normal'], fontSize=10, textColor=colors.grey,
        spaceAfter=16, alignment=TA_CENTER,
    )

    # Paragraph parses markup, so escape user-supplied text such as tournament names.
    elements = [
        Paragraph(escape(title), title_style),
        Paragraph(f"{escape(subtitle)} &middot; Generated {timezone.localdate().strftime('%B %d, %Y')}", sub_style),
        Spacer(1, 0.1 * inch),
    ]

    table = Table([header] + rows, colWidths=col_widths, repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), INK),
        ('TEXTCOLOR', (0, 0), (-1, 0), CREAM),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('PADDING', (0, 1), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f4ef')]),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 1), (0, -1), GOLD),
    ]
    for col in align_left_cols:
        style.append(('ALIGN', (col, 1), (col, -1), 'LEFT'))
    table.setStyle(TableStyle(style))
    elements.append(table)

    doc.build(elements)
    return response
