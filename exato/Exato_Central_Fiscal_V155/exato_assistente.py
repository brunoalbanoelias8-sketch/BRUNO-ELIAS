"""Exatinho conversando: entende perguntas e pedidos em português, consulta o Arquivo Fiscal Local e devolve respostas com as
evidências (as notas e a conta por trás), botões de ação e o resumo do dia.

Tudo roda no computador: nenhum dado fiscal sai daqui e não há IA externa. O módulo não conhece a tela: recebe `data`, um
dicionário de funções (empresas, resumo, notas, buscas, certificados...), e devolve dicionários simples que a tela mostra.

Resposta: {'text': str, 'lines': [str], 'actions': [{'label', 'kind', ...}], 'confirm': {...}|None, 'topic': str}
Ações: {'kind': 'goto', 'screen'} | {'kind': 'nfse_search_save'|'nfse_search', 'cnpj'} | {'kind': 'nfse_all_save'} |
       {'kind': 'nfse_report', 'cnpj', 'df', 'dt'} | {'kind': 'docs_cancelled_exported'} | {'kind': 'cert_list'}
"""
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal

MONTHS = ['janeiro', 'fevereiro', 'marco', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
MONTH_NAMES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
STOP_COMPANY = {'ltda', 'epp', 'eireli', 'sa', 'me', 'comercio', 'servicos', 'servico', 'industria', 'empresa', 'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'para', 'com', 'cia', 'grupo',
                'nota', 'notas', 'nfse', 'nfe', 'xml', 'mes', 'ano', 'todas', 'todos', 'tudo', 'quanto', 'quantas', 'quais', 'qual', 'busque', 'buscar', 'salve', 'gere', 'relatorio', 'abra', 'mostre',
                'prestou', 'prestei', 'tomou', 'tomei', 'cancelada', 'canceladas', 'exportada', 'exportadas', 'passado', 'atual', 'este', 'esta', 'esse', 'essa', 'meu', 'minha', 'hoje', 'ontem'}
FAMILY_LABEL = {'nfe': 'NF-e', 'nfce': 'NFC-e', 'cte': 'CT-e', 'nfse': 'NFS-e'}
SCREENS = {'nfse': ('nfs-e', 'nfse', 'servicos eletronicos'), 'documents': ('documentos', 'documento fiscal', 'arquivo fiscal'), 'companies': ('empresas', 'empresa cadastro', 'cadastro'),
           'audit': ('auditoria',), 'history': ('historico',), 'pending': ('pendencias', 'pendencia'), 'certificate': ('certificado', 'certificados'), 'reports': ('relatorios',),
           'dashboard': ('inicio', 'painel', 'home'), 'sync': ('buscar xml', 'busca de xml', 'buscar nf-e')}
SCREEN_LABEL = {'nfse': 'NFS-e', 'documents': 'Documentos Fiscais', 'companies': 'Empresas', 'audit': 'Auditoria Fiscal', 'history': 'Histórico', 'pending': 'Pendências',
                'certificate': 'Certificado', 'reports': 'Relatórios', 'dashboard': 'Início', 'sync': 'Buscar XML'}


def norm(text):
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode('ascii').lower()
    return re.sub(r'\s+', ' ', text).strip()


def brl(v):
    try:
        d = Decimal(str(v or 0))
    except Exception:
        d = Decimal('0')
    s = f'{d:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {s}'


def fmt_cnpj(d):
    d = re.sub(r'\D', '', str(d or ''))
    return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}' if len(d) == 14 else d


def br_date(iso):
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', str(iso or ''))
    return f'{m.group(3)}/{m.group(2)}/{m.group(1)}' if m else str(iso or '')


def _month_range(year, month):
    first = date(year, month, 1)
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    return first, nxt - timedelta(days=1)


def parse_period(text, today):
    """(inicio, fim, rótulo) em datas, ou None se a frase não fala de período."""
    t = norm(text)
    m = re.search(r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*(?:a|ate|ao|-)\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?', t)
    if m:
        try:
            y1 = int(m.group(3) or today.year); y2 = int(m.group(6) or y1)
            y1 += 2000 if y1 < 100 else 0; y2 += 2000 if y2 < 100 else 0
            a = date(y1, int(m.group(2)), int(m.group(1))); b = date(y2, int(m.group(5)), int(m.group(4)))
            if a <= b: return a, b, f'{a:%d/%m/%Y} a {b:%d/%m/%Y}'
        except ValueError:
            pass
    if re.search(r'\bhoje\b', t): return today, today, 'hoje'
    if re.search(r'\bontem\b', t):
        y = today - timedelta(days=1); return y, y, 'ontem'
    if re.search(r'mes passado|mes anterior|ultimo mes', t):
        last = today.replace(day=1) - timedelta(days=1); a, b = _month_range(last.year, last.month); return a, b, f'{MONTH_NAMES[a.month - 1]}/{a.year}'
    if re.search(r'este mes|esse mes|mes atual|no mes\b|do mes\b|neste mes', t) and not any(mo in t for mo in MONTHS):
        a, b = _month_range(today.year, today.month); return a, b, f'{MONTH_NAMES[a.month - 1]}/{a.year}'
    if re.search(r'este ano|esse ano|neste ano|no ano\b', t):
        return date(today.year, 1, 1), today, f'{today.year}'
    for idx, name in enumerate(MONTHS, 1):
        mm = re.search(rf'\b{name}\b(?:\s*(?:de|/)?\s*(\d{{4}}))?', t)
        if mm:
            year = int(mm.group(1)) if mm.group(1) else (today.year if idx <= today.month else today.year - 1)
            a, b = _month_range(year, idx); return a, b, f'{MONTH_NAMES[idx - 1]}/{year}'
    mm = re.search(r'\b(0?[1-9]|1[0-2])/(\d{4})\b', t)
    if mm:
        a, b = _month_range(int(mm.group(2)), int(mm.group(1))); return a, b, f'{MONTH_NAMES[a.month - 1]}/{a.year}'
    return None


def _tokens(name):
    return [w for w in re.findall(r'[a-z0-9]+', norm(name)) if len(w) >= 3 and w not in STOP_COMPANY and w not in MONTHS]


def match_companies(text, companies):
    """Empresas citadas na frase: CNPJ digitado ou nome (pelo menos uma palavra própria do nome). Devolve as de maior pontuação."""
    t = norm(text); digits = re.sub(r'\D', '', text or '')
    for c in companies:
        cn = re.sub(r'\D', '', str(c.get('cnpj') or ''))
        if cn and len(digits) >= 14 and cn in digits:
            return [c]
    words = set(re.findall(r'[a-z0-9]+', t)); scored = []
    for c in companies:
        toks = _tokens(c.get('name'))
        hit = [w for w in toks if w in words]
        if hit:
            scored.append((len(hit) / max(1, len(toks)) + len(hit), c))
    if not scored: return []
    best = max(s for s, _ in scored)
    return [c for s, c in scored if s == best]


def _has(t, *words):
    return any(w in t for w in words)


def detect_intent(question):
    t = norm(question)
    if not t: return 'vazio'
    if _has(t, 'ajuda', 'o que voce faz', 'o que voce sabe', 'o que voce pode', 'comandos', 'como funciona voce') and not _has(t, 'relatorio'): return 'ajuda'
    if _has(t, 'resumo do dia', 'resumo de hoje', 'o que tenho', 'o que preciso', 'pendencias de hoje', 'o que falta fazer', 'bom dia', 'tem algo', 'alguma pendencia', 'o que fazer hoje'): return 'resumo'
    if _has(t, 'relatorio'): return 'acao_relatorio'
    if _has(t, 'busque', 'buscar', 'busca', 'puxe', 'puxar', 'baixe', 'baixar', 'atualize', 'atualizar') and not _has(t, 'sem busca', 'nao buscou', 'nao buscaram', 'ultima busca', 'quando buscou'):
        if re.search(r'\b(todas|todos)\b', t) and _has(t, 'empresa'): return 'acao_todas'
        return 'acao_buscar_salvar' if _has(t, 'salv', 'tudo', 'exporte', 'exportar') else 'acao_buscar'
    if _has(t, 'abra', 'abrir', 'va para', 'ir para', 'leve-me', 'me leve', 'mostre a tela', 'abre') : return 'ir'
    if _has(t, 'sem busca', 'nao buscou', 'nao buscaram', 'sem buscar', 'desatualizad', 'atrasad', 'ultima busca', 'quando buscou', 'nao busquei', 'faz tempo'): return 'sem_busca'
    if _has(t, 'certificado') and _has(t, 'venc', 'validade', 'expira'): return 'certificados'
    if _has(t, 'cancelad'): return 'canceladas'
    if _has(t, 'nao exportad', 'falta exportar', 'ainda nao exportei', 'para exportar', 'nao salv', 'falta salvar'): return 'nao_exportadas'
    if _has(t, 'quanto', 'total', 'valor', 'soma', 'faturamento', 'faturei', 'faturou', 'gastei', 'paguei', 'recebi') and _has(t, 'prest', 'emit', 'fatur', 'tom', 'receb', 'pagu', 'gast', 'nfs'): return 'total_nfse'
    if _has(t, 'quantas', 'quantidade', 'quantos', 'numero de notas', 'contagem'): return 'contagem'
    if _has(t, 'nfs', 'servico') and _has(t, 'total', 'quanto'): return 'total_nfse'
    return 'desconhecido'


def _kind_from_text(t):
    if _has(t, 'prest', 'emit', 'fatur', 'recebi de', 'saida'): return 'Saída'
    if _has(t, 'tomad', 'tomei', 'tomou', 'gastei', 'paguei', 'contrat', 'entrada'): return 'Entrada'
    return ''


def _resolve_company(question, data):
    """(empresa|None, mensagem de dúvida|None). Sem citar nenhuma, usa a empresa ativa."""
    companies = data['companies']() or []
    found = match_companies(question, companies)
    if len(found) > 1:
        names = ', '.join(c['name'] for c in found[:5])
        return None, {'text': f'Encontrei mais de uma empresa parecida: {names}. Diga o nome completo ou o CNPJ.', 'lines': [], 'actions': [], 'confirm': None, 'topic': 'duvida'}
    if found: return found[0], None
    active = re.sub(r'\D', '', str(data['active_cnpj']() or ''))
    for c in companies:
        if re.sub(r'\D', '', str(c.get('cnpj'))) == active: return c, None
    return (companies[0], None) if len(companies) == 1 else (None, None)


def _reply(text, lines=None, actions=None, confirm=None, topic='resposta'):
    return {'text': text, 'lines': lines or [], 'actions': actions or [], 'confirm': confirm, 'topic': topic}


def _period_or_default(question, data, default='mes'):
    today = data['today']()
    p = parse_period(question, today)
    if p: return p
    if default == 'mes':
        a, b = _month_range(today.year, today.month); return a, b, f'{MONTH_NAMES[a.month - 1]}/{a.year} (mês atual)'
    return None


def _goto(screen, label=None):
    return {'label': label or f'Abrir {SCREEN_LABEL.get(screen, screen)}', 'kind': 'goto', 'screen': screen}


# ---------- resumo do dia
def daily_briefing(data):
    """Pontos que pedem a atenção do usuário hoje: [{'severity': 'alta'|'media'|'info', 'text', 'action'}]."""
    today = data['today'](); items = []; names = {re.sub(r'\D', '', str(c['cnpj'])): c['name'] for c in (data['companies']() or [])}
    nm = lambda cnpj: names.get(re.sub(r'\D', '', str(cnpj)), fmt_cnpj(cnpj))
    canc = data['cancelled_exported']() or []
    n = sum(int(x['count']) for x in canc)
    if n:
        who = ', '.join(sorted({nm(x['cnpj']) for x in canc})[:3])
        items.append({'severity': 'alta', 'text': f'{n} nota(s) já exportada(s) foram canceladas ({who}). Confira antes de lançar.', 'action': {'label': 'Ver canceladas exportadas', 'kind': 'docs_cancelled_exported'}})
    certs = data['certs']() or []
    for c in certs:
        try:
            left = (date.fromisoformat(str(c['not_after'])[:10]) - today).days
        except Exception:
            continue
        if left < 0:
            items.append({'severity': 'alta', 'text': f'O certificado de {c.get("name") or "uma empresa"} venceu há {-left} dia(s).', 'action': {'label': 'Abrir Certificado', 'kind': 'cert_list'}})
        elif left <= 30:
            items.append({'severity': 'media', 'text': f'O certificado de {c.get("name") or "uma empresa"} vence em {left} dia(s).', 'action': {'label': 'Abrir Certificado', 'kind': 'cert_list'}})
    runs = data['last_runs']() or {}
    stale = []
    for cnpj, name in names.items():
        ok = (runs.get(cnpj) or {}).get('ok_at')
        try:
            days = (today - date.fromisoformat(str(ok)[:10])).days if ok else None
        except Exception:
            days = None
        if days is None or days >= 7:
            stale.append((name, days))
    if stale:
        sample = ', '.join(f'{n} ({"nunca buscou" if d is None else f"há {d} dias"})' for n, d in stale[:3])
        items.append({'severity': 'media', 'text': f'{len(stale)} empresa(s) sem busca há 7 dias ou mais: {sample}{"..." if len(stale) > 3 else ""}.', 'action': {'label': 'Buscar NFS-e de todas e salvar', 'kind': 'nfse_all_save'}})
    failed = [(cnpj, r) for cnpj, r in runs.items() if r.get('last_error') and 'XML' in str(r.get('last_error'))]
    if failed:
        items.append({'severity': 'media', 'text': f'A última busca de {nm(failed[0][0])} deixou XMLs sem baixar. Tente de novo.', 'action': {'label': 'Buscar de novo', 'kind': 'nfse_search', 'cnpj': failed[0][0]}})
    unexp = data['unexported']() or []
    k = sum(int(x['count']) for x in unexp)
    if k:
        items.append({'severity': 'info', 'text': f'{k} nota(s) ainda não foram salvas na pasta dos clientes.', 'action': {'label': 'Abrir Documentos Fiscais', 'kind': 'goto', 'screen': 'documents'}})
    return items


def render_briefing(items, name=''):
    if not items:
        return _reply(f'{"Bom ver você, " + name + "! " if name else ""}Hoje está tudo em dia: nada pendente que eu tenha encontrado.', topic='resumo')
    head = f'{"Oi, " + name + "! " if name else ""}Tenho {len(items)} ponto(s) para você hoje:'
    lines = [('⚠ ' if i['severity'] == 'alta' else '• ') + i['text'] for i in items]
    return _reply(head, lines, [i['action'] for i in items if i.get('action')], topic='resumo')


# ---------- respostas
def answer(question, data, name=''):
    intent = detect_intent(question)
    t = norm(question)
    if intent == 'vazio':
        return _reply('Pode perguntar: por exemplo "quanto a CREATIVE HUB prestou em setembro?" ou "quais notas canceladas eu já exportei?".', topic='ajuda')
    if intent == 'ajuda': return _help()
    if intent == 'resumo': return render_briefing(daily_briefing(data), name)
    if intent == 'ir':
        for screen, words in SCREENS.items():
            if any(w in t for w in words):
                return _reply(f'Abrindo {SCREEN_LABEL[screen]}.', actions=[], confirm=None, topic='ir') | {'run': _goto(screen)}
        return _reply('Para qual tela? Posso abrir NFS-e, Documentos Fiscais, Empresas, Auditoria, Histórico, Pendências, Certificado, Relatórios, Início ou Buscar XML.', topic='duvida')
    if intent == 'sem_busca': return _a_sem_busca(data)
    if intent == 'certificados': return _a_certificados(data)
    if intent == 'nao_exportadas': return _a_nao_exportadas(data)
    if intent in ('acao_buscar', 'acao_buscar_salvar', 'acao_todas'): return _a_buscar(question, data, intent)
    comp, doubt = _resolve_company(question, data)
    if doubt: return doubt
    if intent == 'acao_relatorio': return _a_relatorio(question, data, comp)
    if intent == 'canceladas': return _a_canceladas(question, data, comp)
    if intent == 'total_nfse': return _a_total_nfse(question, data, comp)
    if intent == 'contagem': return _a_contagem(question, data, comp)
    return _reply('Ainda não sei responder isso. Eu consigo falar de valores e quantidades de notas, canceladas, empresas sem busca, certificados e também fazer buscas e relatórios para você.',
                  actions=[{'label': 'Ver o resumo do dia', 'kind': 'briefing'}, {'label': 'O que você sabe fazer?', 'kind': 'help'}], topic='desconhecido')


def _help():
    lines = ['"Quanto a CREATIVE HUB prestou em setembro?" — valores de NFS-e prestadas ou tomadas',
             '"Quantas notas tem a CREATIVE HUB este mês?" — quantidades por tipo de nota',
             '"Quais notas canceladas eu já exportei?" — canceladas, com as notas por trás',
             '"Que empresas estão sem busca?" — quem não busca há dias',
             '"Algum certificado vencendo?" — validade dos certificados',
             '"Busque e salve tudo da CREATIVE HUB" — eu faço a busca e salvo os XMLs (peço confirmação)',
             '"Gere o relatório de setembro" — relatório mensal em PDF',
             '"Abra Documentos" — vou para a tela; "Resumo do dia" — o que precisa de você']
    return _reply('Eu consulto os seus dados aqui no computador e posso fazer algumas tarefas por você. Exemplos do que dá para pedir:', lines, topic='ajuda')


def _sum_rows(rows):
    ok = [r for r in rows if r.get('status') != 'Cancelado']
    bad = [r for r in rows if r.get('status') == 'Cancelado']
    tot = lambda xs: sum((Decimal(str(r.get('value') or 0)) for r in xs), Decimal('0.00'))
    return ok, bad, tot(ok), tot(bad)


def _note_line(r):
    kind = 'Prestada' if r.get('direction') == 'Saída' else 'Tomada'
    flag = ' — cancelada' if r.get('status') == 'Cancelado' else ''
    exp = ' (já exportada)' if r.get('exported') else ''
    return f'NFS-e {r.get("number") or "s/n"} • {br_date(r.get("issued_at"))} • {kind} • {brl(r.get("value"))}{flag}{exp}'


def _a_total_nfse(question, data, comp):
    if comp is None:
        return _reply('De qual empresa? Diga o nome ou o CNPJ.', topic='duvida')
    t = norm(question); per = _period_or_default(question, data)
    df, dt, label = per
    rows = data['nfse_rows'](comp['cnpj'], df.isoformat(), dt.isoformat(), 5000)
    want = _kind_from_text(t)
    shown = [r for r in rows if not want or r.get('direction') == want]
    ok, bad, total, canc_total = _sum_rows(shown)
    kind_label = {'Saída': 'prestou', 'Entrada': 'tomou', '': 'movimentou'}[want]
    name = comp['name']
    if not shown:
        return _reply(f'Não encontrei NFS-e {"prestadas" if want == "Saída" else "tomadas" if want == "Entrada" else ""} de {name} em {label}. Se você ainda não buscou, posso fazer isso.'.replace('  ', ' '),
                      actions=[{'label': 'Buscar e salvar tudo', 'kind': 'nfse_search_save', 'cnpj': comp['cnpj']}], topic='total')
    text = f'{name} {kind_label} {brl(total)} em {label}: {len(ok)} nota(s) autorizada(s).'
    if want == '':
        p = [r for r in ok if r.get('direction') == 'Saída']; tm = [r for r in ok if r.get('direction') == 'Entrada']
        text = f'{name} em {label}: prestou {brl(sum((Decimal(str(r["value"] or 0)) for r in p), Decimal("0")))} ({len(p)} nota(s)) e tomou {brl(sum((Decimal(str(r["value"] or 0)) for r in tm), Decimal("0")))} ({len(tm)} nota(s)).'
    if bad:
        text += f' Há {len(bad)} cancelada(s) ({brl(canc_total)}), que não entram na soma.'
    lines = [_note_line(r) for r in sorted(shown, key=lambda r: str(r.get('issued_at')))[:8]]
    if len(shown) > 8: lines.append(f'… e mais {len(shown) - 8} nota(s).')
    actions = [{'label': 'Gerar relatório mensal', 'kind': 'nfse_report', 'cnpj': comp['cnpj'], 'df': df.isoformat(), 'dt': dt.isoformat()},
               {'label': 'Abrir NFS-e', 'kind': 'goto', 'screen': 'nfse', 'cnpj': comp['cnpj'], 'df': df.isoformat(), 'dt': dt.isoformat()}]
    return _reply(text, lines, actions, topic='total')


def _a_contagem(question, data, comp):
    if comp is None:
        return _reply('De qual empresa? Diga o nome ou o CNPJ.', topic='duvida')
    df, dt, label = _period_or_default(question, data)
    summ = data['summary'](comp['cnpj'], df.isoformat(), dt.isoformat())
    by = {}
    for r in summ:
        if r.get('status') == 'Evento': continue
        k = (r['family'], r.get('direction') or '')
        b = by.setdefault(k, {'n': 0, 'canc': 0, 'total': Decimal('0')})
        b['n'] += int(r['count'])
        if r.get('status') == 'Cancelado': b['canc'] += int(r['count'])
        else: b['total'] += Decimal(str(r.get('total') or 0))
    if not by:
        return _reply(f'{comp["name"]} não tem notas guardadas em {label}.', topic='contagem')
    lines = []
    for (fam, dire), b in sorted(by.items()):
        d = ('prestadas' if dire == 'Saída' else 'tomadas') if fam == 'nfse' else ('saídas' if dire == 'Saída' else 'entradas' if dire == 'Entrada' else '')
        lines.append(f'{FAMILY_LABEL.get(fam, fam)} {d}: {b["n"]} nota(s) • {brl(b["total"])}' + (f' • {b["canc"]} cancelada(s)' if b['canc'] else ''))
    n = sum(b['n'] for b in by.values())
    return _reply(f'{comp["name"]} tem {n} nota(s) em {label}:', lines, [{'label': 'Abrir Documentos Fiscais', 'kind': 'goto', 'screen': 'documents'}], topic='contagem')


def _a_canceladas(question, data, comp):
    only_exp = _has(norm(question), 'exportad')
    rows_all = []
    if comp is not None:
        per = parse_period(question, data['today']())
        df, dt = (per[0].isoformat(), per[1].isoformat()) if per else ('', '')
        rows_all = data['nfse_rows'](comp['cnpj'], df, dt, 5000)
    canc = [r for r in rows_all if r.get('status') == 'Cancelado' and (r.get('exported') or not only_exp)]
    if comp is None or not canc:
        gl = data['cancelled_exported']() or []
        n = sum(int(x['count']) for x in gl)
        if n:
            return _reply(f'No total, {n} nota(s) já exportada(s) foram canceladas depois. Confira antes de lançar.' if comp is None else f'{comp["name"]} não tem NFS-e canceladas {"já exportadas " if only_exp else ""}nesse período. No total do Exato há {n} nota(s) exportada(s) que foram canceladas.',
                          actions=[{'label': 'Ver canceladas exportadas', 'kind': 'docs_cancelled_exported'}], topic='canceladas')
        return _reply('Nenhuma nota exportada foi cancelada depois. Está tudo certo.' if only_exp else 'Não encontrei notas canceladas.', topic='canceladas')
    ok, bad, total, canc_total = _sum_rows(canc)
    lines = [_note_line(r) for r in canc[:8]] + ([f'… e mais {len(canc) - 8}.'] if len(canc) > 8 else [])
    return _reply(f'{comp["name"]} tem {len(canc)} NFS-e cancelada(s){" já exportada(s)" if only_exp else ""}, somando {brl(canc_total + total)}:', lines,
                  [{'label': 'Ver canceladas exportadas', 'kind': 'docs_cancelled_exported'}], topic='canceladas')


def _a_sem_busca(data):
    today = data['today'](); runs = data['last_runs']() or {}; rows = []
    for c in data['companies']() or []:
        cnpj = re.sub(r'\D', '', str(c['cnpj'])); ok = (runs.get(cnpj) or {}).get('ok_at')
        try: days = (today - date.fromisoformat(str(ok)[:10])).days if ok else None
        except Exception: days = None
        rows.append((9999 if days is None else days, c['name'], days))
    late = [r for r in sorted(rows, reverse=True) if r[0] >= 7]
    if not late:
        return _reply('Todas as empresas buscaram nos últimos 7 dias.', topic='sem_busca')
    lines = [f'{n} — {"nunca buscou" if d is None else f"última busca há {d} dia(s)"}' for _, n, d in late[:12]]
    return _reply(f'{len(late)} empresa(s) estão sem busca há 7 dias ou mais:', lines, [{'label': 'Buscar NFS-e de todas e salvar', 'kind': 'nfse_all_save'}], topic='sem_busca')


def _a_certificados(data):
    today = data['today'](); certs = data['certs']() or []
    if not certs:
        return _reply('Não encontrei certificados instalados neste computador.', actions=[{'label': 'Abrir Certificado', 'kind': 'cert_list'}], topic='certificados')
    rows = []
    for c in certs:
        try: rows.append(((date.fromisoformat(str(c['not_after'])[:10]) - today).days, c.get('name') or 'Certificado'))
        except Exception: pass
    rows.sort()
    near = [r for r in rows if r[0] <= 60]
    lines = [f'{n} — {"vencido há " + str(-d) + " dia(s)" if d < 0 else "vence em " + str(d) + " dia(s)"}' for d, n in (near or rows)[:10]]
    head = f'{len([r for r in rows if r[0] < 0])} vencido(s) e {len([r for r in rows if 0 <= r[0] <= 30])} vencendo em 30 dias:' if near else 'Nenhum certificado vence nos próximos 60 dias. Os mais próximos:'
    return _reply(head, lines, [{'label': 'Abrir Certificado', 'kind': 'cert_list'}], topic='certificados')


def _a_nao_exportadas(data):
    names = {re.sub(r'\D', '', str(c['cnpj'])): c['name'] for c in data['companies']() or []}
    items = data['unexported']() or []
    n = sum(int(x['count']) for x in items)
    if not n:
        return _reply('Tudo o que está no Arquivo Fiscal Local já foi salvo na pasta dos clientes.', topic='nao_exportadas')
    agg = {}
    for x in items:
        agg[x['cnpj']] = agg.get(x['cnpj'], 0) + int(x['count'])
    lines = [f'{names.get(re.sub(r"\D", "", str(c)), fmt_cnpj(c))}: {k} nota(s)' for c, k in sorted(agg.items(), key=lambda kv: -kv[1])[:10]]
    return _reply(f'{n} nota(s) ainda não foram salvas na pasta dos clientes:', lines, [{'label': 'Abrir Documentos Fiscais', 'kind': 'goto', 'screen': 'documents'}], topic='nao_exportadas')


def _a_buscar(question, data, intent):
    if intent == 'acao_todas':
        return _reply('Vou buscar as NFS-e de todas as empresas que têm certificado neste computador e salvar os XMLs novos na pasta dos clientes. Posso começar?',
                      confirm={'kind': 'nfse_all_save', 'label': 'Buscar de todas e salvar'}, topic='acao')
    comp, doubt = _resolve_company(question, data)
    if doubt: return doubt
    if comp is None:
        return _reply('De qual empresa? Diga o nome ou o CNPJ.', topic='duvida')
    t2 = ' ' + norm(question) + ' '
    for w in re.findall(r'[a-z0-9]+', norm(comp['name'])):      # "tudo" no nome da empresa (AGRO TUDO) não é o pedido de salvar tudo
        t2 = t2.replace(f' {w} ', ' ')
    save = _has(t2, 'salv', 'tudo', 'exporte', 'exportar')
    kind = 'nfse_search_save' if save else 'nfse_search'
    verb = 'buscar as NFS-e' + (' e salvar os XMLs novos na pasta dos clientes' if kind == 'nfse_search_save' else '')
    return _reply(f'Vou {verb} de {comp["name"]} ({fmt_cnpj(comp["cnpj"])}). Posso começar?', confirm={'kind': kind, 'cnpj': comp['cnpj'], 'label': 'Sim, pode começar'}, topic='acao')


def _a_relatorio(question, data, comp):
    if comp is None:
        return _reply('De qual empresa é o relatório? Diga o nome ou o CNPJ.', topic='duvida')
    p = parse_period(question, data['today']())
    if p is None:
        today = data['today'](); last = today.replace(day=1) - timedelta(days=1); a, b = _month_range(last.year, last.month); p = (a, b, f'{MONTH_NAMES[a.month - 1]}/{a.year} (mês anterior)')
    df, dt, label = p
    return _reply(f'Vou gerar o relatório mensal de NFS-e de {comp["name"]} para {label}.', confirm={'kind': 'nfse_report', 'cnpj': comp['cnpj'], 'df': df.isoformat(), 'dt': dt.isoformat(), 'label': 'Gerar o relatório'}, topic='acao')
