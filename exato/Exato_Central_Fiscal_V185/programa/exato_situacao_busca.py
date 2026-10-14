"""Situação da busca por empresa e tipo de documento (V176). Sem Tkinter.

Responde, para cada empresa: "o Exato já buscou NF-e, NFC-e, CT-e e NFS-e? até que dia? quantas notas tem?". Junta o registro da busca
(`exato_cobertura.registrar`), o arquivo fiscal deste computador e, quando nada existe, o índice do Repositório.

Estados de cada tipo: 'em_dia' (buscado nos últimos `ATRASO_DIAS` dias, com notas), 'sem_notas' (buscado, mas a empresa não tem nota desse
tipo), 'atrasado' (última busca há mais de `ATRASO_DIAS` dias) e 'nunca' (sem registro de busca e sem nenhuma nota).

NF-e, NFC-e e CT-e vêm do mesmo Web Service e a mesma busca cobre os três: um tipo raro (por exemplo CT-e, última nota há meses) não pode
fazer a empresa parecer atrasada; por isso a cobertura de um tipo do grupo é a mais recente entre os registros do grupo.
"""
from __future__ import annotations
import re, sqlite3
from datetime import date, datetime, timedelta

import exato_cobertura as cobertura
import exato_busca_motivos as motivos

ATRASO_DIAS = 3
TIPOS = (('nfe', 'NF-e'), ('nfce', 'NFC-e'), ('cte', 'CT-e'), ('nfse', 'NFS-e'))
GRUPO_XML = ('nfe', 'nfce', 'cte')


def _digitos(texto):
    return re.sub(r'\D', '', str(texto or ''))


def _banco(db_path):
    """{(cnpj, família): (última vez visto, quantidade, data da última nota)} numa única consulta."""
    saida = {}
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            for cnpj, fam, visto, n, ultima in conn.execute("SELECT cnpj, family, MAX(last_seen_at), COUNT(*), MAX(substr(issued_at,1,10)) FROM documents WHERE COALESCE(status,'')<>'Evento' GROUP BY cnpj, family").fetchall():
                saida[(_digitos(cnpj), str(fam or '').lower())] = (cobertura._data(visto), int(n or 0), cobertura._data(ultima))
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return saida


def _empresas(db_path):
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            return [(_digitos(c), str(n or '').strip()) for c, n in conn.execute("SELECT cnpj, name FROM companies ORDER BY name").fetchall() if len(_digitos(c)) == 14]
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def _ate_repositorio(indice_repo, cnpj):
    try: return cobertura.do_repositorio(indice_repo, cnpj)[0]
    except Exception: return None


def _data_curta(d, hoje):
    return d.strftime('%d/%m' if d.year == hoje.year else '%d/%m/%Y')


def _celula(familia, ate, notas, hoje, atraso, ultima=None):
    """Estado de um tipo. `ate`: até que dia a BUSCA foi (ou None); `notas`: quantas notas daquele tipo existem; `ultima`: data da nota mais recente."""
    base = {'familia': familia, 'ate': ate, 'notas': notas, 'ultima_nota': ultima, 'dias': None}
    if ate is None:
        return dict(base, estado='nunca', texto='Ainda não buscado', detalhe='nenhum registro de busca')
    dias = max((hoje - ate).days, 0); quando = _data_curta(ate, hoje)
    com_notas = (f'última nota {_data_curta(ultima, hoje)} • ' if ultima else '') + f'{notas:,} notas'.replace(',', '.')
    if dias > atraso:
        return dict(base, dias=dias, estado='atrasado', texto=f'Atrasado {dias} dia(s)', detalhe=(com_notas if notas else 'sem notas') + f'\nbuscado até {quando}')
    if not notas:
        return dict(base, dias=dias, estado='sem_notas', texto='Sem notas', detalhe=f'buscado até {quando}')
    return dict(base, dias=dias, estado='em_dia', texto='Em dia', detalhe=com_notas + f'\nbuscado até {quando}')


def linhas(db_path, config, indice_repo=None, hoje=None, atraso=ATRASO_DIAS, ocorrencias=None, diagnostico=None, compartilhada=None):
    """[{'cnpj','nome','celulas': {familia: célula}, 'resumo': 'em_dia' | 'atraso' | 'nunca', 'pendentes': [famílias]}] por empresa.
    `ocorrencias`: {(cnpj, tipo): última ocorrência} de `exato_busca_motivos.ultimas`; `diagnostico`: {cnpj: {'xml': código, 'nfse': código}} (causas já
    conhecidas pela configuração). Quando um tipo está pendente, a célula traz `causa` (explicação em português) e o detalhe mostra o título dela."""
    hoje = hoje or date.today(); banco = _banco(db_path); saida = []
    for cnpj, nome in _empresas(db_path):
        regs = {f: cobertura.do_registro(config, cnpj, f) for f, _ in TIPOS}
        if compartilhada:          # V178: o que outro computador já buscou também conta
            import exato_busca_compartilhada as comp
            for f, _ in TIPOS:
                outro = comp.cobertura_compartilhada(compartilhada, cnpj, f)
                if outro and (regs[f] is None or outro > regs[f]): regs[f] = outro
        ates = {}
        for f, _ in TIPOS:
            ates[f] = regs[f] or banco.get((cnpj, f), (None, 0, None))[0]
        if not any(ates.values()):
            repo = _ate_repositorio(indice_repo, cnpj)
            if repo: ates = {f: repo for f, _ in TIPOS if f != 'nfse'}
        # o grupo XML compartilha a busca: vale a cobertura mais recente entre os registros (e, sem registro, entre as notas)
        grupo = [a for a in (regs[f] for f in GRUPO_XML) if a] or [a for a in (ates[f] for f in GRUPO_XML) if a]
        ate_grupo = max(grupo) if grupo else None
        celulas = {}
        for f, _ in TIPOS:
            notas = banco.get((cnpj, f), (None, 0, None))[1]
            ate = (ate_grupo if f in GRUPO_XML else ates[f])
            if ate and ate > hoje: ate = hoje
            cel = celulas[f] = _celula(f, ate, notas, hoje, atraso, banco.get((cnpj, f), (None, 0, None))[2])
            oc = (ocorrencias or {}).get((cnpj, f)); causa = oc if (oc and oc.get('resultado') != 'ok') else None
            if causa is None and cel['estado'] in ('nunca', 'atrasado'):
                cod = ((diagnostico or {}).get(cnpj) or {}).get('nfse' if f == 'nfse' else 'xml')
                if cod: causa = dict(motivos.explicar(cod), cnpj=cnpj, tipo=f, quando='', resultado='previsto', detalhe='', previsto=True)
            cel['ocorrencia'] = oc; cel['causa'] = causa; cel['detalhe_base'] = cel['detalhe']
            if causa:
                if cel['estado'] == 'nunca': cel['detalhe'] = causa['titulo']
                else: cel['detalhe'] += '\n⚠ ' + causa['titulo']
        estados = {c['estado'] for c in celulas.values()}
        resumo = 'nunca' if 'nunca' in estados else ('atraso' if 'atrasado' in estados else 'em_dia')
        pend = [f for f, c in celulas.items() if c['estado'] in ('nunca', 'atrasado')]
        saida.append({'cnpj': cnpj, 'nome': nome, 'celulas': celulas, 'resumo': resumo, 'pendentes': pend})
    return saida


def totais(lista):
    """Quadros do topo. `atraso` e `nunca` contam empresas com PELO MENOS um tipo atrasado / nunca buscado (uma empresa pode estar nos dois)."""
    t = {'empresas': len(lista), 'em_dia': 0, 'atraso': 0, 'nunca': 0}
    for l in lista:
        estados = {c['estado'] for c in l['celulas'].values()}
        if 'atrasado' in estados: t['atraso'] += 1
        if 'nunca' in estados: t['nunca'] += 1
        if l['resumo'] == 'em_dia': t['em_dia'] += 1
    return t


def cobertura_empresa(db_path, config, indice_repo, cnpj, banco=None):
    """Até que dia a busca de documentos XML (NF-e, NFC-e, CT-e) da empresa foi: o mais recente entre os tipos do grupo. None se não se sabe."""
    cnpj = _digitos(cnpj); banco = banco if banco is not None else _banco(db_path)
    regs = [a for a in (cobertura.do_registro(config, cnpj, f) for f in GRUPO_XML) if a]
    if regs: return max(regs)
    ates = [a for a in (banco.get((cnpj, f), (None, 0, None))[0] for f in GRUPO_XML) if a]
    if ates: return max(ates)
    return _ate_repositorio(indice_repo, cnpj)


def filtrar(lista, texto='', situacao='Todas', tipo='Todos os tipos'):
    texto = str(texto or '').strip().casefold(); dig = _digitos(texto)
    nomes = {nome: f for f, nome in TIPOS}; fam = nomes.get(tipo)
    saida = []
    for l in lista:
        if texto and texto not in l['nome'].casefold() and not (dig and dig in l['cnpj']): continue
        alvo = [fam] if fam else [f for f, _ in TIPOS]
        estados = {l['celulas'][f]['estado'] for f in alvo}
        if situacao == 'Só com pendência' and not (estados & {'nunca', 'atrasado'}): continue
        if situacao == 'Só em dia' and (estados & {'nunca', 'atrasado'}): continue
        if situacao == 'Só atrasadas' and 'atrasado' not in estados: continue
        if situacao == 'Só não buscadas' and 'nunca' not in estados: continue
        saida.append(l)
    return saida


def itens_relatorio(linha):
    """Itens do relatório (tela e PDF) de uma empresa: um por tipo, com título, explicação, o que fazer e a gravidade, em português claro."""
    itens = []
    for f, nome in TIPOS:
        cel = linha['celulas'][f]; causa = cel.get('causa'); estado = cel['estado']
        resumo = cel.get('detalhe_base', cel['detalhe']).replace('\n', ' • ')
        if causa:
            item = dict(causa, tipo=f, estado=estado, resumo=resumo)
            if estado == 'em_dia' or estado == 'sem_notas': item['gravidade'] = 'aviso' if causa.get('gravidade') != 'erro' else 'erro'
        elif estado == 'nunca':
            item = dict(motivos.explicar('erro_desconhecido'), tipo=f, estado=estado, resumo=resumo, titulo='Ainda não buscado', gravidade='aviso',
                        explicacao='O Exato ainda não fez nenhuma busca deste tipo de nota para esta empresa.', acao='Clique em "Buscar o que falta".', quando='', detalhe='')
        elif estado == 'atrasado':
            item = dict(motivos.explicar('erro_desconhecido'), tipo=f, estado=estado, resumo=resumo, titulo=cel['texto'], gravidade='aviso',
                        explicacao=f"A última busca deste tipo foi há {cel['dias']} dia(s). O Exato considera atraso quando passa de {ATRASO_DIAS} dias.", acao='Clique em "Buscar o que falta".', quando='', detalhe='')
        else:
            item = dict(motivos.explicar('ok'), tipo=f, estado=estado, resumo=resumo, titulo=cel['texto'], gravidade='info', explicacao='', acao='', quando=(cel.get('ocorrencia') or {}).get('quando', ''), detalhe='')
        itens.append(item)
    return itens
