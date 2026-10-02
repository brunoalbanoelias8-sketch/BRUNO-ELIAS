"""NFS-e: representação em PDF (uma página por nota), no papel que o DANFE tem para a NF-e.

Gerada a partir do XML. Não substitui o DANFSe oficial do Emissor Nacional (a nota diz isso no rodapé).
"""
import re
from datetime import datetime
from decimal import Decimal
from html import escape

import exato_nfse as nfse


def _money(v):
    if v is None or v == '':
        return '—'
    try:
        d = Decimal(str(v))
    except Exception:
        return str(v)
    s = f'{d:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {s}'


def _doc(d):
    d = re.sub(r'\D', '', str(d or ''))
    if len(d) == 14: return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'
    if len(d) == 11: return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}'
    return d or '—'


def _date(v):
    v = str(v or '')
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?', v)
    if not m: return v or '—'
    out = f'{m.group(3)}/{m.group(2)}/{m.group(1)}'
    return out + (f' {m.group(4)}:{m.group(5)}' if m.group(4) else '')


def _key_groups(key):
    key = re.sub(r'\D', '', str(key or ''))
    return ' '.join(key[i:i + 5] for i in range(0, len(key), 5)) or '—'


def _addr_text(a):
    if not a: return '—'
    parts = [a.get('logradouro'), a.get('numero'), a.get('complemento'), a.get('bairro')]
    line = ', '.join(p for p in parts if p)
    city = ' - '.join(p for p in (a.get('municipio'), a.get('uf')) if p)
    cep = f"CEP {a['cep']}" if a.get('cep') else ''
    return ' • '.join(p for p in (line, city, cep) if p) or '—'


def build_pages(items, story_builder):
    """items: dicts com 'xml', 'cnpj' (empresa consultada) e opcionalmente 'situacao' ('Cancelada')."""
    for i, it in enumerate(items):
        try:
            d = nfse.parse_nfse_details(it['xml'], it.get('cnpj', ''))
        except Exception:
            d = None
        story_builder(i, d, it)


def generate_nfse_pdf(items, output_path, company_name='', logo_path=None):
    """Um PDF com uma página por NFS-e (ou um PDF individual, se houver só um item)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
    ink = colors.HexColor('#0F172A'); muted = colors.HexColor('#64748B'); line = colors.HexColor('#CBD5E1'); red = colors.HexColor('#E11D2E')
    st = getSampleStyleSheet()
    lab = ParagraphStyle('lab', parent=st['BodyText'], fontName='Helvetica', fontSize=6.8, leading=8, textColor=muted)
    val = ParagraphStyle('val', parent=st['BodyText'], fontName='Helvetica-Bold', fontSize=8.8, leading=10.5, textColor=ink)
    txt = ParagraphStyle('txt', parent=st['BodyText'], fontName='Helvetica', fontSize=8.6, leading=11, textColor=ink)
    title = ParagraphStyle('title', parent=st['Title'], fontName='Helvetica-Bold', fontSize=14, leading=17, textColor=ink, alignment=0, spaceAfter=0)
    sub = ParagraphStyle('sub', parent=st['BodyText'], fontName='Helvetica', fontSize=8.5, leading=11, textColor=muted)
    sec = ParagraphStyle('sec', parent=st['BodyText'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white)
    W = 182 * mm

    def cell(label, value, style=val):
        return [Paragraph(escape(label.upper()), lab), Paragraph(escape(str(value if value not in (None, '') else '—')), style)]

    def box(rows, widths):
        t = Table(rows, colWidths=widths)
        t.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.6, line), ('INNERGRID', (0, 0), (-1, -1), 0.3, line), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        return t

    def section(name):
        t = Table([[Paragraph(escape(name.upper()), sec)]], colWidths=[W])
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), ink), ('LEFTPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        return t

    def fields(pairs, widths):
        return box([[cell(l, v) for l, v in pairs]], widths)

    story = []
    cancelled_pages = set()
    for index, it in enumerate(items):
        try:
            d = nfse.parse_nfse_details(it['xml'], it.get('cnpj', ''))
        except Exception:
            d = None
        if index: story.append(PageBreak())
        head = [Paragraph('DANFSe — Documento Auxiliar da NFS-e', title), Paragraph('Nota Fiscal de Serviço Eletrônica • Padrão Nacional', sub)]
        logo = None
        if logo_path:
            try:
                logo = Image(str(logo_path)); sc = min((38 * mm) / logo.imageWidth, (12 * mm) / logo.imageHeight); logo.drawWidth = logo.imageWidth * sc; logo.drawHeight = logo.imageHeight * sc
            except Exception:
                logo = None
        top = Table([[head, logo or '']], colWidths=[W - 42 * mm, 42 * mm])
        top.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'RIGHT'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        story += [top, Spacer(1, 3 * mm)]
        if d is None:
            story += [Paragraph('Não foi possível ler este XML como NFS-e do padrão nacional.', txt)]
            continue
        if it.get('situacao') == 'Cancelada': cancelled_pages.add(index + 1)
        story.append(box([[cell('Chave de acesso', _key_groups(d['chave']))]], [W]))
        story.append(fields([('Número da NFS-e', d['numero']), ('Série / DPS', ' / '.join(x for x in (d['serie'], d['numero_dps']) if x) or '—'), ('Emissão', _date(d['data'])),
                             ('Competência', _date(d['competencia'])), ('Situação', 'CANCELADA' if it.get('situacao') == 'Cancelada' else 'Autorizada')], [34 * mm, 32 * mm, 42 * mm, 34 * mm, 40 * mm]))
        story.append(fields([('Local de emissão', d['local_emissao']), ('Local da prestação', d['local_prestacao'] or d['local_emissao']), ('Processamento', _date(d['processamento']))], [66 * mm, 66 * mm, 50 * mm]))
        story += [Spacer(1, 2 * mm), section('Prestador do serviço')]
        story.append(fields([('Nome / Razão social', d['prestador']['nome']), ('CNPJ / CPF', _doc(d['prestador']['doc'])), ('Inscrição municipal', d['prestador_im'])], [96 * mm, 46 * mm, 40 * mm]))
        story.append(box([[cell('Endereço', _addr_text(d['prestador_end']))]], [W]))
        story += [Spacer(1, 2 * mm), section('Tomador do serviço')]
        story.append(fields([('Nome / Razão social', d['tomador']['nome']), ('CNPJ / CPF', _doc(d['tomador']['doc'])), ('Inscrição municipal', d['tomador_im'])], [96 * mm, 46 * mm, 40 * mm]))
        story.append(box([[cell('Endereço', _addr_text(d['tomador_end']))]], [W]))
        if d['intermediario']['doc'] or d['intermediario']['nome']:
            story.append(fields([('Intermediário', d['intermediario']['nome']), ('CNPJ / CPF', _doc(d['intermediario']['doc']))], [136 * mm, 46 * mm]))
        story += [Spacer(1, 2 * mm), section('Serviço prestado')]
        story.append(fields([('Código de tributação nacional', d['servico_codigo']), ('Código municipal', d['servico_codigo_municipal']), ('Município de incidência', d['local_incidencia'])], [70 * mm, 50 * mm, 62 * mm]))
        story.append(box([[[Paragraph('DESCRIÇÃO DO SERVIÇO', lab), Paragraph(escape(d['servico_descricao'] or d['servico_trib_nacional'] or '—'), txt)]]], [W]))
        if d['info_complementar']:
            story.append(box([[[Paragraph('INFORMAÇÕES COMPLEMENTARES', lab), Paragraph(escape(d['info_complementar']), txt)]]], [W]))
        story += [Spacer(1, 2 * mm), section('Valores')]
        story.append(fields([('Valor do serviço', _money(d['valor_servico'] if d['valor_servico'] is not None else d['valor'])), ('Desconto', _money(d['valor_desconto'])), ('Base de cálculo', _money(d['valor_base'])),
                             ('Alíquota ISS', (d['aliquota'] + '%') if d['aliquota'] else '—'), ('ISS apurado', _money(d['valor_iss']))], [40 * mm, 34 * mm, 38 * mm, 32 * mm, 38 * mm]))
        story.append(fields([('Retenções', _money(d['valor_retido'])), ('Valor líquido', _money(d['valor_liquido'])), ('ISS retido', {'1': 'Não', '2': 'Sim'}.get(str(d['retencao_iss']), '—'))], [60 * mm, 60 * mm, 62 * mm]))
        story += [Spacer(1, 4 * mm), Paragraph('Representação gráfica gerada pelo Exato Central Fiscal a partir do XML da NFS-e. Não substitui o DANFSe oficial do Emissor Nacional.', sub)]

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5); canvas.setFillColor(muted)
        canvas.drawString(14 * mm, 8 * mm, f"Exato Central Fiscal • {company_name or ''} • gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        canvas.drawRightString(A4[0] - 14 * mm, 8 * mm, f'Página {doc.page}')
        if doc.page in cancelled_pages:
            canvas.translate(A4[0] / 2, A4[1] / 2); canvas.rotate(35); canvas.setFont('Helvetica-Bold', 70); canvas.setFillColor(colors.Color(0.88, 0.11, 0.18, alpha=0.18))
            canvas.drawCentredString(0, 0, 'CANCELADA')
        canvas.restoreState()

    doc = SimpleDocTemplate(str(output_path), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=14 * mm, title='DANFSe')
    doc.build(story or [Paragraph('Nenhuma NFS-e.', txt)], onFirstPage=decorate, onLaterPages=decorate)
    return str(output_path)


def monthly_summary(rows):
    """rows: dicts com data (AAAA-MM-DD...), tipo ('Prestado'/'Tomado'), valor, situacao ('Cancelada'/'Autorizada').

    Devolve lista ordenada por mês: {'mes','prest_qtd','prest_valor','tom_qtd','tom_valor','canc_qtd','canc_valor'}.
    Canceladas não entram nos valores de prestados/tomados.
    """
    months = {}
    for r in rows:
        key = str(r.get('data') or '')[:7] if re.match(r'\d{4}-\d{2}', str(r.get('data') or '')) else 'Sem data'
        m = months.setdefault(key, {'mes': key, 'prest_qtd': 0, 'prest_valor': Decimal('0.00'), 'tom_qtd': 0, 'tom_valor': Decimal('0.00'), 'canc_qtd': 0, 'canc_valor': Decimal('0.00')})
        v = Decimal(str(r.get('valor') or 0))
        if r.get('situacao') == 'Cancelada':
            m['canc_qtd'] += 1; m['canc_valor'] += v
        elif r.get('tipo') == 'Prestado':
            m['prest_qtd'] += 1; m['prest_valor'] += v
        else:
            m['tom_qtd'] += 1; m['tom_valor'] += v
    return [months[k] for k in sorted(months)]


def month_label(key):
    names = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    m = re.match(r'(\d{4})-(\d{2})$', key or '')
    return f'{names[int(m.group(2)) - 1]}/{m.group(1)}' if m and 1 <= int(m.group(2)) <= 12 else (key or 'Sem data')


def generate_monthly_summary_pdf(summary, output_path, company_name='', cnpj='', period_label='Todo o período', logo_path=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    ink = colors.HexColor('#0F172A'); muted = colors.HexColor('#64748B'); line = colors.HexColor('#E6EAF1'); red = colors.HexColor('#E11D2E')
    st = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=st['Title'], fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=ink, alignment=0, spaceAfter=2)
    small = ParagraphStyle('small', parent=st['BodyText'], fontName='Helvetica', fontSize=9, leading=12, textColor=muted)
    c = ParagraphStyle('c', parent=st['BodyText'], fontName='Helvetica', fontSize=8.6, leading=11, textColor=ink)
    cr = ParagraphStyle('cr', parent=c, alignment=2)
    hd = ParagraphStyle('hd', parent=c, fontName='Helvetica-Bold', textColor=colors.white)
    hdr = ParagraphStyle('hdr', parent=hd, alignment=2)
    bold = ParagraphStyle('bold', parent=c, fontName='Helvetica-Bold')
    boldr = ParagraphStyle('boldr', parent=bold, alignment=2)
    doc = SimpleDocTemplate(str(output_path), pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=16 * mm, title='Resumo mensal de NFS-e')
    story = []
    if logo_path:
        try:
            img = Image(str(logo_path), hAlign='LEFT'); sc = min((42 * mm) / img.imageWidth, (13 * mm) / img.imageHeight); img.drawWidth = img.imageWidth * sc; img.drawHeight = img.imageHeight * sc; story += [img, Spacer(1, 3 * mm)]
        except Exception:
            pass
    story += [Paragraph('Resumo mensal de NFS-e', h1), Paragraph(f'<b>{escape(company_name or "Empresa")}</b>  •  CNPJ {escape(_doc(cnpj))}', small),
              Paragraph(f'Período: {escape(period_label)}', small), Spacer(1, 5 * mm)]
    head = [Paragraph('Mês', hd), Paragraph('Prestados (notas)', hdr), Paragraph('Prestados (valor)', hdr), Paragraph('Tomados (notas)', hdr), Paragraph('Tomados (valor)', hdr), Paragraph('Canceladas', hdr)]
    data = [head]
    tot = {'pq': 0, 'pv': Decimal('0.00'), 'tq': 0, 'tv': Decimal('0.00'), 'cq': 0}
    for m in summary:
        data.append([Paragraph(escape(month_label(m['mes'])), c), Paragraph(str(m['prest_qtd']), cr), Paragraph(_money(m['prest_valor']), cr), Paragraph(str(m['tom_qtd']), cr), Paragraph(_money(m['tom_valor']), cr), Paragraph(str(m['canc_qtd']), cr)])
        tot['pq'] += m['prest_qtd']; tot['pv'] += m['prest_valor']; tot['tq'] += m['tom_qtd']; tot['tv'] += m['tom_valor']; tot['cq'] += m['canc_qtd']
    if len(data) == 1:
        data.append([Paragraph('Nenhuma NFS-e neste filtro.', c)] + [''] * 5)
    data.append([Paragraph('Total', bold), Paragraph(str(tot['pq']), boldr), Paragraph(_money(tot['pv']), boldr), Paragraph(str(tot['tq']), boldr), Paragraph(_money(tot['tv']), boldr), Paragraph(str(tot['cq']), boldr)])
    t = Table(data, colWidths=[55 * mm, 38 * mm, 48 * mm, 38 * mm, 48 * mm, 30 * mm], repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), red), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F8FAFC')]), ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EEF2F7')),
                           ('GRID', (0, 0), (-1, -1), 0.3, line), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    story += [t, Spacer(1, 4 * mm), Paragraph('Notas canceladas não entram nos valores de prestados e tomados.', small)]
    def footer(canvas, d):
        canvas.saveState(); canvas.setFont('Helvetica', 8); canvas.setFillColor(muted)
        canvas.drawString(14 * mm, 8 * mm, f"Exato Central Fiscal • gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"); canvas.drawRightString(landscape(A4)[0] - 14 * mm, 8 * mm, f'Página {d.page}'); canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return str(output_path)
