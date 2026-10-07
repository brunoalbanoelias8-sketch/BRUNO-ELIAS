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

ATRASO_DIAS = 3
TIPOS = (('nfe', 'NF-e'), ('nfce', 'NFC-e'), ('cte', 'CT-e'), ('nfse', 'NFS-e'))
GRUPO_XML = ('nfe', 'nfce', 'cte')


def _digitos(texto):
    return re.sub(r'\D', '', str(texto or ''))


def _banco(db_path):
    """{(cnpj, família): (última vez visto, quantidade)} numa única consulta."""
    saida = {}
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            for cnpj, fam, visto, n in conn.execute("SELECT cnpj, family, MAX(last_seen_at), COUNT(*) FROM documents WHERE COALESCE(status,'')<>'Evento' GROUP BY cnpj, family").fetchall():
                saida[(_digitos(cnpj), str(fam or '').lower())] = (cobertura._data(visto), int(n or 0))
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


def _celula(familia, ate, notas, hoje, atraso, reg):
    """Estado de um tipo. `ate`: até que dia buscamos (ou None); `notas`: quantas notas daquele tipo existem; `reg`: há registro de busca."""
    if ate is None:
        return {'familia': familia, 'estado': 'nunca', 'ate': None, 'notas': notas, 'dias': None, 'texto': 'Ainda não buscado', 'detalhe': 'nenhum registro de busca'}
    dias = max((hoje - ate).days, 0); quando = ate.strftime('%d/%m')
    if dias > atraso:
        return {'familia': familia, 'estado': 'atrasado', 'ate': ate, 'notas': notas, 'dias': dias, 'texto': f'Atrasado {dias} dia(s)',
                'detalhe': f'até {quando} • ' + (f'{notas:,} notas'.replace(',', '.') if notas else 'sem notas')}
    if not notas:
        return {'familia': familia, 'estado': 'sem_notas', 'ate': ate, 'notas': 0, 'dias': dias, 'texto': 'Sem notas', 'detalhe': f'buscado até {quando}'}
    return {'familia': familia, 'estado': 'em_dia', 'ate': ate, 'notas': notas, 'dias': dias, 'texto': 'Em dia', 'detalhe': f'até {quando} • ' + f'{notas:,} notas'.replace(',', '.')}


def linhas(db_path, config, indice_repo=None, hoje=None, atraso=ATRASO_DIAS):
    """[{'cnpj','nome','celulas': {familia: célula}, 'resumo': 'em_dia' | 'atraso' | 'nunca', 'pendentes': [famílias]}] por empresa."""
    hoje = hoje or date.today(); banco = _banco(db_path); saida = []
    for cnpj, nome in _empresas(db_path):
        regs = {f: cobertura.do_registro(config, cnpj, f) for f, _ in TIPOS}
        ates = {}
        for f, _ in TIPOS:
            ates[f] = regs[f] or banco.get((cnpj, f), (None, 0))[0]
        if not any(ates.values()):
            repo = _ate_repositorio(indice_repo, cnpj)
            if repo: ates = {f: repo for f, _ in TIPOS if f != 'nfse'}
        # o grupo XML compartilha a busca: vale a cobertura mais recente entre os registros (e, sem registro, entre as notas)
        grupo = [a for a in (regs[f] for f in GRUPO_XML) if a] or [a for a in (ates[f] for f in GRUPO_XML) if a]
        ate_grupo = max(grupo) if grupo else None
        celulas = {}
        for f, _ in TIPOS:
            notas = banco.get((cnpj, f), (None, 0))[1]
            ate = (ate_grupo if f in GRUPO_XML else ates[f])
            if ate and ate > hoje: ate = hoje
            celulas[f] = _celula(f, ate, notas, hoje, atraso, bool(regs[f]))
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
    ates = [a for a in (banco.get((cnpj, f), (None, 0))[0] for f in GRUPO_XML) if a]
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
