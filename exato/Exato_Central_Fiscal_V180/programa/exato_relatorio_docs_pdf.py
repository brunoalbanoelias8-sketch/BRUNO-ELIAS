"""Relatório em PDF da tela Documentos fiscais (V180). Sem Tkinter, sem os núcleos protegidos.

Recebe as linhas já normalizadas (ver `normalizar`) e monta um PDF paisagem, bem apresentado, com os TIPOS DE DOCUMENTO SEMPRE SEPARADOS:
capa com os filtros aplicados, quadros e gráficos; depois uma seção (a partir de página nova) para cada tipo: NF-e, NFC-e, CT-e e NFS-e.
Em todo total, as notas AUTORIZADAS e as CANCELADAS ficam em linhas/colunas separadas (cancelada nunca soma no valor das autorizadas).

Linha normalizada (dict): familia ('nfe'|'nfce'|'cte'|'nfse'), movimentacao ('Entrada'|'Saída'|'Prestado'|'Tomado'), numero, serie, data (AAAA-MM-DD), valor (str/Decimal),
situacao ('Autorizada'|'Cancelada'|outra), exportada (bool), chave, parte (nome da outra parte), doc (CNPJ/CPF da outra parte), empresa, cnpj e, só NFS-e,
aliquota, iss, iss_retido, iss_fora, municipio.
"""
import re
from datetime import datetime
from decimal import Decimal
from html import escape

TIPOS = {'nfe': 'NF-e', 'nfce': 'NFC-e', 'cte': 'CT-e', 'nfse': 'NFS-e'}
ORDEM = ('nfe', 'nfce', 'cte', 'nfse')
COR_TIPO = {'nfe': '#2563EB', 'nfce': '#D97706', 'cte': '#16A34A', 'nfse': '#7C3AED'}
VERMELHO = '#E11D2E'; TINTA = '#0F172A'; MUDO = '#64748B'; LINHA = '#E6EAF1'; SUAVE = '#EEF2F7'; ALERTA = '#B91C1C'
ZERO = Decimal('0.00')


def _dec(v):
    try: return Decimal(str(v)) if v not in (None, '') else ZERO
    except Exception: return ZERO


def money(v):
    try: d = Decimal(str(v if v not in (None, '') else 0))
    except Exception: return str(v)
    return 'R$ ' + f'{d:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _doc(d):
    d = re.sub(r'\D', '', str(d or ''))
    if len(d) == 14: return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'
    if len(d) == 11: return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}'
    return d or '—'


def _br(data):
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', str(data or ''))
    return f'{m.group(3)}/{m.group(2)}/{m.group(1)}' if m else (str(data or '') or '—')


def _mes(chave):
    m = re.match(r'(\d{4})-(\d{2})', str(chave or ''))
    nomes = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
    return f'{nomes[int(m.group(2)) - 1]}/{m.group(1)[2:]}' if m and 1 <= int(m.group(2)) <= 12 else 'sem data'


def _clip(texto, n):
    texto = str(texto or '')
    return texto if len(texto) <= n else texto[:n - 1].rstrip() + '…'


def _cancelada(r):
    return str(r.get('situacao') or '') == 'Cancelada'


def _autorizada(r):
    return str(r.get('situacao') or '') == 'Autorizada'


def _saida(r):
    return str(r.get('movimentacao') or '') in ('Saída', 'Prestado')


def normalizar(rows_db, extras=None):
    """Linhas do banco (`db_list_documents`) -> linhas do relatório. `extras`: {doc_id: dict com parte/doc/aliquota/iss/iss_retido/iss_fora/municipio} lido do XML."""
    extras = extras or {}; saida = []
    for r in rows_db or []:
        fam = str(r.get('family') or '').lower()
        if fam not in TIPOS: continue
        ex = extras.get(r.get('doc_id')) or {}
        st = str(r.get('status') or '')
        sit = 'Cancelada' if st == 'Cancelado' else ('Autorizada' if st == 'Autorizado' else (st or '—'))
        mov = ex.get('movimentacao') or r.get('direction') or ''
        saida.append({'familia': fam, 'movimentacao': mov, 'numero': str(r.get('number') or ''), 'serie': str(r.get('series') or ''), 'data': str(r.get('issued_at') or '')[:10],
                      'valor': _dec(r.get('value')), 'situacao': sit, 'exportada': bool(r.get('exported_any')), 'chave': str(r.get('access_key') or ''),
                      'parte': ex.get('parte', ''), 'doc': ex.get('doc', ''), 'empresa': str(r.get('company_name') or r.get('cnpj') or ''), 'cnpj': str(r.get('cnpj') or ''),
                      'aliquota': ex.get('aliquota'), 'iss': ex.get('iss'), 'iss_retido': ex.get('iss_retido'), 'iss_fora': ex.get('iss_fora'), 'municipio': ex.get('municipio')})
    return saida


_RE_BLOCO = {'dest': re.compile(rb'<(?:[A-Za-z_][\w.-]*:)?dest\b.*?</(?:[A-Za-z_][\w.-]*:)?dest>', re.S), 'emit': re.compile(rb'<(?:[A-Za-z_][\w.-]*:)?emit\b.*?</(?:[A-Za-z_][\w.-]*:)?emit>', re.S)}
_RE_NOME = re.compile(rb'<(?:[A-Za-z_][\w.-]*:)?xNome\s*>\s*([^<]*?)\s*<')
_RE_DOC = re.compile(rb'<(?:[A-Za-z_][\w.-]*:)?(CNPJ|CPF)\s*>\s*(\d+)\s*<')


def outra_parte(xml, direcao):
    """Nome e documento da outra parte de uma NF-e/NFC-e/CT-e, lidos direto do XML (Saída = destinatário; Entrada = emitente). Nunca levanta erro."""
    try:
        data = bytes(xml or b'')
        bloco = _RE_BLOCO['emit' if direcao == 'Entrada' else 'dest'].search(data)
        if not bloco: return {'parte': '', 'doc': ''}
        b = bloco.group(0); n = _RE_NOME.search(b); d = _RE_DOC.search(b)
        return {'parte': n.group(1).decode('utf-8', 'replace') if n else '', 'doc': d.group(2).decode('ascii') if d else ''}
    except Exception:
        return {'parte': '', 'doc': ''}


def resumo(linhas):
    """Totais gerais e por tipo/movimentação, com autorizadas e canceladas separadas."""
    por = {}; geral = {'an': 0, 'av': ZERO, 'cn': 0, 'cv': ZERO, 'ent': ZERO, 'sai': ZERO, 'exp_canc': 0}
    for r in linhas:
        g = por.setdefault((r['familia'], r['movimentacao'] or '—'), {'an': 0, 'av': ZERO, 'cn': 0, 'cv': ZERO})
        v = r['valor']
        if _cancelada(r):
            g['cn'] += 1; g['cv'] += v; geral['cn'] += 1; geral['cv'] += v
            if r.get('exportada'): geral['exp_canc'] += 1
        elif _autorizada(r):
            g['an'] += 1; g['av'] += v; geral['an'] += 1; geral['av'] += v
            if _saida(r): geral['sai'] += v
            else: geral['ent'] += v
    ordem = {f: i for i, f in enumerate(ORDEM)}
    lista = [(f, m, g['an'], g['av'], g['cn'], g['cv']) for (f, m), g in sorted(por.items(), key=lambda kv: (ordem.get(kv[0][0], 9), kv[0][1]))]
    return lista, geral


def por_mes(linhas):
    """{mês 'AAAA-MM': {familia: valor autorizado}} só com autorizadas."""
    saida = {}
    for r in linhas:
        if not _autorizada(r): continue
        k = str(r.get('data') or '')[:7] if re.match(r'\d{4}-\d{2}', str(r.get('data') or '')) else 'sem data'
        d = saida.setdefault(k, {}); d[r['familia']] = d.get(r['familia'], ZERO) + r['valor']
    return saida


def gerar(linhas, caminho, empresa='', cnpj='', periodo='Todo o período', filtros=None, logo=None, progresso=None):
    """Gera o PDF. `empresa`/`cnpj`: da empresa filtrada (vazio = várias). `filtros`: lista de textos em português. Devolve o caminho."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rlcanvas
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, CondPageBreak, KeepTogether
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.piecharts import Pie

    hx = colors.HexColor
    st = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=st['Title'], fontName='Helvetica-Bold', fontSize=24, leading=28, textColor=hx(TINTA), alignment=0, spaceAfter=3)
    h2 = ParagraphStyle('h2', parent=st['Heading2'], fontName='Helvetica-Bold', fontSize=14, leading=18, textColor=hx(TINTA), spaceBefore=6, spaceAfter=3)
    peq = ParagraphStyle('peq', parent=st['BodyText'], fontName='Helvetica', fontSize=9, leading=12, textColor=hx(MUDO))
    corpo = ParagraphStyle('corpo', parent=st['BodyText'], fontName='Helvetica', fontSize=9, leading=12, textColor=hx(TINTA))
    cel = ParagraphStyle('cel', parent=corpo, fontSize=8.6, leading=11)
    celr = ParagraphStyle('celr', parent=cel, alignment=2)
    cab = ParagraphStyle('cab', parent=cel, fontName='Helvetica-Bold', textColor=colors.white)
    cabr = ParagraphStyle('cabr', parent=cab, alignment=2)
    neg = ParagraphStyle('neg', parent=cel, fontName='Helvetica-Bold')
    negr = ParagraphStyle('negr', parent=neg, alignment=2)
    kv = ParagraphStyle('kv', parent=corpo, fontName='Helvetica-Bold', fontSize=15, leading=19)
    kt = ParagraphStyle('kt', parent=peq, fontName='Helvetica-Bold', fontSize=7.5, leading=10)
    W = 269

    class _Numerada(rlcanvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k); self._estados = []
        def showPage(self):
            self._estados.append(dict(self.__dict__)); self._startPage()
        def save(self):
            total = len(self._estados)
            for estado in self._estados:
                self.__dict__.update(estado); self._rodape(total); super().showPage()
            super().save()
        def _rodape(self, total):
            self.setFont('Helvetica', 8); self.setFillColor(hx(MUDO))
            self.drawString(14 * mm, 8 * mm, f"Exato Central Fiscal • gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
            self.drawRightString(landscape(A4)[0] - 14 * mm, 8 * mm, f'Página {self._pageNumber} de {total}')
            if self._pageNumber > 1:
                self.setFont('Helvetica', 8); self.drawString(14 * mm, landscape(A4)[1] - 9 * mm, f"Documentos fiscais • {empresa or 'Várias empresas'}" + (f' • CNPJ {_doc(cnpj)}' if cnpj else '') + f' • {periodo}')
                self.setStrokeColor(hx(VERMELHO)); self.setLineWidth(1.2); self.line(14 * mm, landscape(A4)[1] - 11 * mm, landscape(A4)[0] - 14 * mm, landscape(A4)[1] - 11 * mm)

    doc = SimpleDocTemplate(str(caminho), pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=15 * mm, bottomMargin=16 * mm, title='Relatório de documentos fiscais')
    story = []
    lista, geral = resumo(linhas)
    varias = len({r.get('cnpj') for r in linhas if r.get('cnpj')}) > 1
    base = [('GRID', (0, 0), (-1, -1), 0.3, hx(LINHA)), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]

    # ------------------------------------------------------------------ capa
    if logo:
        try:
            img = Image(str(logo), hAlign='LEFT'); sc = min((42 * mm) / img.imageWidth, (13 * mm) / img.imageHeight); img.drawWidth = img.imageWidth * sc; img.drawHeight = img.imageHeight * sc; story += [img, Spacer(1, 4 * mm)]
        except Exception: pass
    story += [Paragraph('Relatório de documentos fiscais', h1),
              Paragraph(f'<b>{escape(empresa or "Várias empresas")}</b>' + (f'  •  CNPJ {escape(_doc(cnpj))}' if cnpj else ''), corpo),
              Paragraph(f'Período: {escape(periodo)}  •  {len(linhas):,} documento(s)'.replace(',', '.'), peq)]
    if filtros:
        story.append(Paragraph('Filtros: ' + escape('  •  '.join(filtros)), peq))
    story.append(Spacer(1, 5 * mm))

    def cartao(titulo, valor, sub, cor):
        t = Table([[Paragraph(titulo, kt)], [Paragraph(f'<font color="{cor}">{escape(valor)}</font>', kv)], [Paragraph(escape(sub), peq)]], colWidths=[62 * mm])
        t.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.6, hx(LINHA)), ('BACKGROUND', (0, 0), (-1, -1), hx('#F8FAFC')), ('LINEBEFORE', (0, 0), (0, -1), 3, hx(cor)),
                               ('LEFTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        return t
    cartoes = Table([[cartao('AUTORIZADAS', money(geral['av']), f'{geral["an"]} nota(s)', '#16A34A'), cartao('CANCELADAS (à parte)', money(geral['cv']), f'{geral["cn"]} nota(s)', ALERTA),
                      cartao('ENTRADAS / TOMADOS', money(geral['ent']), 'só autorizadas', '#2563EB'), cartao('SAÍDAS / PRESTADOS', money(geral['sai']), 'só autorizadas', VERMELHO)]], colWidths=[W / 4 * mm] * 4, hAlign='LEFT')
    cartoes.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 4)]))
    story += [cartoes, Spacer(1, 5 * mm)]

    # quadro por tipo e movimentação
    dados = [[Paragraph(x, h) for x, h in (('Tipo de documento', cab), ('Movimentação', cab), ('Autorizadas (notas)', cabr), ('Autorizadas (valor)', cabr), ('Canceladas (notas)', cabr), ('Canceladas (valor)', cabr))]]
    for fam, mov, an, av, cn, cv in lista:
        dados.append([Paragraph(f'<font color="{COR_TIPO.get(fam, TINTA)}"><b>■</b></font> {TIPOS.get(fam, fam)}', cel), Paragraph(escape(str(mov)), cel), Paragraph(str(an), celr), Paragraph(money(av), celr),
                      Paragraph(f'<font color="{ALERTA}">{cn}</font>' if cn else '0', celr), Paragraph(f'<font color="{ALERTA}">{money(cv)}</font>' if cn else money(cv), celr)])
    if len(dados) == 1: dados.append([Paragraph('Nenhum documento neste filtro.', cel)] + [''] * 5)
    dados.append([Paragraph('TOTAL', neg), '', Paragraph(str(geral['an']), negr), Paragraph(money(geral['av']), negr), Paragraph(str(geral['cn']), negr), Paragraph(money(geral['cv']), negr)])
    t = Table(dados, colWidths=[55 * mm, 40 * mm, 40 * mm, 50 * mm, 40 * mm, 44 * mm], repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle(base + [('BACKGROUND', (0, 0), (-1, 0), hx(VERMELHO)), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, hx('#F8FAFC')]), ('BACKGROUND', (0, -1), (-1, -1), hx(SUAVE)), ('TOPPADDING', (0, 0), (-1, -1), 1.6), ('BOTTOMPADDING', (0, 0), (-1, -1), 1.6)]))
    story += [t, Spacer(1, 2 * mm), Paragraph('As notas autorizadas e as canceladas são somadas separadamente: cancelada nunca entra no valor das autorizadas. Cada tipo de documento tem a sua seção, a partir da próxima página.', peq)]
    if geral['exp_canc']:
        story += [Spacer(1, 2 * mm), Paragraph(f'<font color="{ALERTA}"><b>Atenção:</b> {geral["exp_canc"]} nota(s) cancelada(s) já foram exportadas. Confira na Domínio.</font>', corpo)]

    # gráficos
    meses = por_mes(linhas); chaves = sorted(meses)[-12:]
    fams = [f for f in ORDEM if any(f in meses[m] for m in chaves)]
    if chaves and fams:
        d1 = Drawing(165 * mm, 62 * mm)
        d1.add(String(0, 57 * mm, 'Valor autorizado por mês', fontName='Helvetica-Bold', fontSize=9, fillColor=hx(TINTA)))
        bc = VerticalBarChart(); bc.x = 12 * mm; bc.y = 9 * mm; bc.width = 148 * mm; bc.height = 44 * mm
        bc.data = [[float(meses[m].get(f, ZERO)) for m in chaves] for f in fams]
        bc.categoryAxis.categoryNames = [_mes(m) for m in chaves]; bc.categoryAxis.labels.fontSize = 7; bc.valueAxis.labels.fontSize = 7
        topo = max((max(s) for s in bc.data), default=0)
        bc.valueAxis.valueMin = 0; bc.valueAxis.labelTextFormat = (lambda v: f'{v / 1000:.0f} mil') if topo >= 10000 else (lambda v: f'{v:.0f}')
        bc.bars.strokeColor = None; bc.groupSpacing = 6; bc.barSpacing = 1
        for i, f in enumerate(fams): bc.bars[i].fillColor = hx(COR_TIPO[f])
        bc.valueAxis.gridStrokeColor = hx(LINHA); bc.valueAxis.visibleGrid = 1
        d1.add(bc)
        x0 = 100 * mm
        for i, f in enumerate(fams):
            d1.add(String(x0 + i * 16 * mm, 57 * mm, f'■ {TIPOS[f]}', fontName='Helvetica-Bold', fontSize=7.5, fillColor=hx(COR_TIPO[f])))
        d2 = Drawing(95 * mm, 62 * mm)
        d2.add(String(0, 57 * mm, 'Entradas x saídas (autorizadas)', fontName='Helvetica-Bold', fontSize=9, fillColor=hx(TINTA)))
        if geral['ent'] > 0 or geral['sai'] > 0:
            pie = Pie(); pie.x = 8 * mm; pie.y = 6 * mm; pie.width = 42 * mm; pie.height = 42 * mm
            pie.data = [float(geral['ent']), float(geral['sai'])]; pie.labels = None; pie.slices.strokeColor = colors.white
            pie.slices[0].fillColor = hx('#2563EB'); pie.slices[1].fillColor = hx(VERMELHO)
            d2.add(pie)
            tot = float(geral['ent'] + geral['sai']) or 1.0
            d2.add(String(56 * mm, 36 * mm, f'■ Entradas {geral["ent"] / Decimal(str(tot)) * 100:.0f}%', fontName='Helvetica-Bold', fontSize=8, fillColor=hx('#2563EB')))
            d2.add(String(56 * mm, 28 * mm, f'■ Saídas {geral["sai"] / Decimal(str(tot)) * 100:.0f}%', fontName='Helvetica-Bold', fontSize=8, fillColor=hx(VERMELHO)))
        g = Table([[d1, d2]], colWidths=[170 * mm, 99 * mm], hAlign='LEFT'); g.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        story += [PageBreak(), Paragraph('Visão geral por mês', h2), Spacer(1, 2 * mm), g, Spacer(1, 4 * mm)]
        # quadro mensal: valor autorizado por tipo e canceladas à parte
        canc_mes = {}
        for r in linhas:
            if _cancelada(r):
                k = str(r.get('data') or '')[:7] if re.match(r'\d{4}-\d{2}', str(r.get('data') or '')) else 'sem data'
                c = canc_mes.setdefault(k, [0, ZERO]); c[0] += 1; c[1] += r['valor']
        todos = sorted(set(meses) | set(canc_mes))
        md = [[Paragraph(x, h) for x, h in [('Mês', cab)] + [(TIPOS[f], cabr) for f in fams] + [('Total autorizadas', cabr), ('Canceladas (notas)', cabr), ('Canceladas (valor)', cabr)]]]
        tot_f = {f: ZERO for f in fams}; tc = [0, ZERO]
        for m in todos:
            linha = [Paragraph(_mes(m), cel)]; soma = ZERO
            for f in fams:
                v = meses.get(m, {}).get(f, ZERO); soma += v; tot_f[f] += v; linha.append(Paragraph(money(v), celr))
            cm = canc_mes.get(m, [0, ZERO]); tc[0] += cm[0]; tc[1] += cm[1]
            md.append(linha + [Paragraph(money(soma), negr), Paragraph(str(cm[0]), celr), Paragraph(money(cm[1]), celr)])
        md.append([Paragraph('TOTAL', neg)] + [Paragraph(money(tot_f[f]), negr) for f in fams] + [Paragraph(money(sum(tot_f.values(), ZERO)), negr), Paragraph(str(tc[0]), negr), Paragraph(money(tc[1]), negr)])
        nf = len(fams); ws = [34] + [int((269 - 34 - 90) / nf)] * nf + [34, 26, 30]; ws[1] += 269 - sum(ws)
        mt = Table(md, colWidths=[w * mm for w in ws], repeatRows=1, hAlign='LEFT')
        mt.setStyle(TableStyle(base + [('BACKGROUND', (0, 0), (-1, 0), hx(TINTA)), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, hx('#F8FAFC')]), ('BACKGROUND', (0, -1), (-1, -1), hx(SUAVE))]))
        story += [mt]

    # ------------------------------------------------------------------ uma seção por tipo (sempre separados)
    feitos = 0
    for fam in ORDEM:
        itens = [r for r in linhas if r['familia'] == fam]
        if not itens: continue
        itens.sort(key=lambda r: (str(r.get('data') or ''), str(r.get('numero') or '').zfill(12)))
        aut = [r for r in itens if _autorizada(r)]; can = [r for r in itens if _cancelada(r)]
        va = sum((r['valor'] for r in aut), ZERO); vc = sum((r['valor'] for r in can), ZERO)
        story += [PageBreak()]
        faixa = Table([[Paragraph(f'<font color="white"><b>{TIPOS[fam]}</b></font>', ParagraphStyle('faixa', parent=h1, fontSize=17, leading=21, textColor=colors.white)),
                        Paragraph(f'<font color="white">{len(itens)} documento(s)</font>', ParagraphStyle('faixad', parent=corpo, alignment=2, textColor=colors.white, fontSize=10))]], colWidths=[150 * mm, 119 * mm])
        faixa.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), hx(COR_TIPO[fam])), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7), ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
        story += [faixa, Spacer(1, 3 * mm)]
        movs = sorted({r['movimentacao'] or '—' for r in itens})
        qd = [[Paragraph(x, h) for x, h in (('Movimentação', cab), ('Autorizadas (notas)', cabr), ('Autorizadas (valor)', cabr), ('Canceladas (notas)', cabr), ('Canceladas (valor)', cabr))]]
        for mv in movs:
            sub = [r for r in itens if (r['movimentacao'] or '—') == mv]
            a_ = [r for r in sub if _autorizada(r)]; c_ = [r for r in sub if _cancelada(r)]
            qd.append([Paragraph(escape(mv), cel), Paragraph(str(len(a_)), celr), Paragraph(money(sum((r['valor'] for r in a_), ZERO)), celr), Paragraph(str(len(c_)), celr), Paragraph(money(sum((r['valor'] for r in c_), ZERO)), celr)])
        qd.append([Paragraph('TOTAL', neg), Paragraph(str(len(aut)), negr), Paragraph(money(va), negr), Paragraph(str(len(can)), negr), Paragraph(money(vc), negr)])
        qt = Table(qd, colWidths=[60 * mm, 45 * mm, 60 * mm, 45 * mm, 59 * mm], repeatRows=1, hAlign='LEFT')
        qt.setStyle(TableStyle(base + [('BACKGROUND', (0, 0), (-1, 0), hx(TINTA)), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, hx('#F8FAFC')]), ('BACKGROUND', (0, -1), (-1, -1), hx(SUAVE))]))
        story.append(qt)
        exp_c = [r for r in can if r.get('exportada')]
        if exp_c:
            story += [Spacer(1, 2 * mm), Paragraph(f'<font color="{ALERTA}"><b>{len(exp_c)} nota(s) cancelada(s) já exportada(s):</b> confira na Domínio.</font>', corpo)]
        if fam == 'nfse':
            fora = [r for r in aut if r.get('iss_fora') == 'SIM']
            iss_a = sum((_dec(r.get('iss')) for r in aut), ZERO); iss_f = sum((_dec(r.get('iss')) for r in fora), ZERO); iss_r = sum((_dec(r.get('iss')) for r in aut if r.get('iss_retido') == 'Sim'), ZERO)
            story += [Spacer(1, 2 * mm), Paragraph(f'ISS das autorizadas: <b>{money(iss_a)}</b>  •  ISS retido: <b>{money(iss_r)}</b>  •  ISS pago fora do município do prestador: <b>{money(iss_f)}</b> ({len(fora)} nota(s))', corpo)]
        story.append(Spacer(1, 4 * mm))
        # lista
        if fam == 'nfse':
            titulos = ['Nº', 'Emissão', 'Tipo', 'Outra parte', 'CNPJ / CPF', 'Valor', 'Alíq.', 'ISS', 'Retido', 'ISS fora?', 'Município', 'Situação', 'Exp.']
            larg = [13, 18, 16, 50, 31, 22, 12, 19, 15, 14, 27, 20, 12]; direita = {5, 6, 7}
            if varias: titulos[3] = 'Empresa / outra parte'
        else:
            titulos = ['Nº', 'Série', 'Emissão', 'Movim.', 'Outra parte', 'Chave de acesso', 'Valor', 'Situação', 'Exp.']
            larg = [16, 12, 18, 17, 64, 83, 25, 22, 12]; direita = {6}
        assert abs(sum(larg) - W) <= 1, sum(larg)
        cabec = [Paragraph(x, cabr if i in direita else cab) for i, x in enumerate(titulos)]
        corpo_t = [cabec]; estilos = []
        for i, r in enumerate(itens, 1):
            parte = _clip(((r['empresa'] + ' / ') if varias else '') + (r.get('parte') or '—'), 46 if not varias else 56)
            exp = 'Sim' if r.get('exportada') else '—'
            if fam == 'nfse':
                lin = [r['numero'], _br(r['data']), r['movimentacao'], parte, _doc(r.get('doc')), money(r['valor']), (f"{_dec(r['aliquota']):.2f}".replace('.', ',') + '%') if r.get('aliquota') not in (None, '') else '—',
                       money(r['iss']) if r.get('iss') not in (None, '') else '—', r.get('iss_retido') or '—', r.get('iss_fora') or '—', _clip(r.get('municipio') or '—', 26), r['situacao'], exp]
            else:
                lin = [r['numero'], r['serie'] or '—', _br(r['data']), r['movimentacao'] or '—', parte, r['chave'] or '—', money(r['valor']), r['situacao'], exp]
            corpo_t.append(lin)
            if _cancelada(r): estilos.append(('TEXTCOLOR', (0, i), (-1, i), hx(ALERTA)))
            if _cancelada(r) and r.get('exportada'): estilos.append(('BACKGROUND', (0, i), (-1, i), hx('#FEE2E2')))
            feitos += 1
            if progresso and feitos % 500 == 0:
                try: progresso(feitos, len(linhas))
                except Exception: pass
        vi = 5 if fam == 'nfse' else 6          # coluna do valor
        corpo_t.append(['Total das autorizadas'] + [''] * (vi - 1) + [money(va)] + [''] * (len(titulos) - vi - 1)); corpo_t.append(['Total das canceladas'] + [''] * (vi - 1) + [money(vc)] + [''] * (len(titulos) - vi - 1))
        n = len(corpo_t)
        tb = Table(corpo_t, colWidths=[w * mm for w in larg], repeatRows=1, hAlign='LEFT')
        alinha = [('ALIGN', (c, 1), (c, -1), 'RIGHT') for c in direita]
        tb.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), hx(VERMELHO)), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTSIZE', (0, 0), (-1, -1), 7.6),
                                ('GRID', (0, 0), (-1, -1), 0.25, hx(LINHA)), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 2.2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
                                ('ROWBACKGROUNDS', (0, 1), (-1, n - 3), [colors.white, hx('#F8FAFC')]), ('BACKGROUND', (0, n - 2), (-1, n - 1), hx(SUAVE)), ('FONTNAME', (0, n - 2), (-1, n - 1), 'Helvetica-Bold'),
                                ('SPAN', (0, n - 2), (vi - 1, n - 2)), ('SPAN', (0, n - 1), (vi - 1, n - 1)), ('TEXTCOLOR', (0, n - 1), (-1, n - 1), hx(ALERTA))] + alinha + estilos))
        # cabeçalho: os Paragraph já têm estilo; o resto é texto simples (rápido em listas grandes)
        story.append(tb)
    if not linhas:
        story += [PageBreak(), Paragraph('Nenhum documento neste filtro.', h2)]
    doc.build(story, canvasmaker=_Numerada)
    return str(caminho)
