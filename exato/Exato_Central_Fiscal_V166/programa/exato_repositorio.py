"""Repositório de XML no servidor do escritório (V164).

Cada XML guardado no banco do Exato também é copiado, como arquivo próprio, para uma pasta do servidor:

    <pasta>\\Repositório\\<CNPJ> - <Empresa>\\<Ano>\\<Mês>\\<Tipo>\\[Prestados|Tomados|Entrada|Saída]\\<chave>.xml

Regras de segurança:
- um arquivo por XML; vários computadores podem gravar ao mesmo tempo sem se atrapalhar;
- se o arquivo já existe com o mesmo conteúdo, nada é feito; se existe com conteúdo DIFERENTE, nunca se sobrescreve (o novo é
  guardado ao lado com o final do código de verificação) e o caso é contado como "diferente";
- se o servidor não responde, o XML continua na fila (tabela repositorio_copias) e é copiado quando ele voltar;
- nada aqui apaga arquivos sozinho: o prazo de guarda só avisa (a limpeza precisa de confirmação);
- sem Tkinter: tudo roda em segundo plano e pode ser testado sozinho.
"""
from __future__ import annotations
import hashlib, os, random, re, shutil, socket, sqlite3, tempfile, threading, time, zipfile
from datetime import datetime, timedelta
from pathlib import Path

PASTA_PADRAO = r'\\SERVER\Arquivos Compartilhados\Clientes\Exato Serviços Contábeis Ltda\Exato Central Fiscal'
SUBPASTA = 'Repositório'
SUBPASTA_BACKUP = 'Backups'
MESES_PADRAO = 12
TIPOS = {'nfe': 'NF-e', 'nfce': 'NFC-e', 'cte': 'CT-e', 'nfse': 'NFS-e'}
_TIPOS_REVERSO = {v: k for k, v in TIPOS.items()}
_PAUSA_ERRO = timedelta(hours=1)          # depois de uma falha, só tenta o mesmo XML de novo após esta pausa


def nome_seguro(texto, limite=40):
    t = re.sub(r'[\\/:*?"<>|\r\n\t]+', ' ', str(texto or '')).strip(' .')
    t = re.sub(r'\s+', ' ', t)
    return (t[:limite].strip(' .')) or 'sem nome'


def _longo(caminho):
    """Windows: caminhos de rede longos (mais de 260 caracteres) precisam do prefixo especial."""
    p = str(caminho)
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    p = os.path.abspath(p)
    if p.startswith('\\\\'):
        return '\\\\?\\UNC\\' + p[2:]
    return '\\\\?\\' + p


def pasta_acessivel(base, espera=6.0):
    """A pasta existe e responde? (Roda numa linha separada: pasta de rede fora do ar pode demorar muito para responder.)"""
    base = str(base or '').strip()
    if not base:
        return False
    resultado = []
    def teste():
        try: resultado.append(os.path.isdir(_longo(base)))
        except Exception: resultado.append(False)
    t = threading.Thread(target=teste, daemon=True); t.start(); t.join(espera)
    return bool(resultado and resultado[0])


def preparar_banco(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS repositorio_copias(
        doc_id TEXT PRIMARY KEY, caminho TEXT, sha256 TEXT, copiado_em TEXT,
        tentativas INTEGER DEFAULT 0, ultima_tentativa TEXT, erro TEXT, conflito INTEGER DEFAULT 0, removido INTEGER DEFAULT 0)""")
    conn.commit()


def _sha(dados):
    return hashlib.sha256(dados).hexdigest()


def _ler(caminho):
    with open(_longo(caminho), 'rb') as f:
        return f.read()


def _partes(linha, pasta_empresa):
    """Pastas (relativas à pasta do repositório) onde o XML fica."""
    familia = str(linha['family'] or 'nfe').lower()
    tipo = TIPOS.get(familia, familia.upper())
    evento = str(linha['status'] or '') == 'Evento' or str(linha['doc_type'] or '') == 'Evento'
    if evento:
        tipo = 'Eventos ' + tipo
    data = str(linha['issued_at'] or '') or str(linha['first_seen_at'] or '')
    m = re.match(r'(\d{4})-(\d{2})', data)
    ano, mes = (m.group(1), m.group(2)) if m else ('Sem data', '00')
    partes = [pasta_empresa, ano, mes, tipo]
    direcao = str(linha['direction'] or '')
    if direcao and not evento:
        if familia == 'nfse':
            direcao = {'Saída': 'Prestados', 'Entrada': 'Tomados'}.get(direcao, direcao)
        partes.append(nome_seguro(direcao, 20))
    chave = re.sub(r'\D', '', str(linha['access_key'] or ''))
    nome = chave if (chave and not evento) else nome_seguro(linha['doc_id'], 80)
    if evento and chave:
        nome = nome_seguro(f"{chave}_{linha['doc_id']}", 100)
    partes.append(nome + '.xml')
    return partes


class _Empresas:
    """Descobre/guarda o nome da pasta de cada empresa: 'CNPJ - Nome' (se já existe uma pasta com esse CNPJ, usa a mesma)."""
    def __init__(self, pasta_repo):
        self.pasta_repo = Path(pasta_repo); self.cache = {}
        try:
            for nome in os.listdir(_longo(self.pasta_repo)):
                m = re.match(r'(\d{14})\b', nome)
                if m: self.cache.setdefault(m.group(1), nome)
        except Exception:
            pass

    def pasta(self, cnpj, nome):
        cnpj = re.sub(r'\D', '', str(cnpj or '')) or 'sem CNPJ'
        if cnpj not in self.cache:
            self.cache[cnpj] = f"{cnpj} - {nome_seguro(nome, 40)}"
        return self.cache[cnpj]


def _listar(pasta):
    """{nome: tamanho} de uma pasta, numa única ida ao servidor (no Windows a lista já traz o tamanho: não abre arquivo nenhum)."""
    achados = {}
    try:
        with os.scandir(_longo(pasta)) as it:
            for e in it:
                try:
                    if e.is_file(): achados[e.name] = e.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return achados


def copiar_arquivo(pasta_repo, partes, xml):
    """Grava um XML. Devolve ('novo' | 'existe' | 'diferente', caminho relativo com /).

    Arquivo já existente com o MESMO TAMANHO é considerado o mesmo (passada rápida: não lê o conteúdo pela rede; a conferência por SHA-256
    é feita por amostra, todo dia, em `verificar`). Tamanho diferente: compara o conteúdo e, se for outro XML, guarda os dois."""
    pasta_repo = Path(pasta_repo)
    destino = pasta_repo.joinpath(*partes)
    sha = _sha(xml)
    os.makedirs(_longo(destino.parent), exist_ok=True)
    estado = 'novo'
    if os.path.exists(_longo(destino)):
        if os.path.getsize(_longo(destino)) == len(xml) or _sha(_ler(destino)) == sha:
            return 'existe', '/'.join([SUBPASTA] + list(partes))
        estado = 'diferente'
        partes = list(partes[:-1]) + [f"{Path(partes[-1]).stem}.{sha[:8]}.xml"]
        destino = pasta_repo.joinpath(*partes)
        if os.path.exists(_longo(destino)) and _sha(_ler(destino)) == sha:
            return 'diferente', '/'.join([SUBPASTA] + list(partes))
    temporario = destino.with_name('.' + destino.name + '.tmp')
    with open(_longo(temporario), 'wb') as f:
        f.write(xml); f.flush()
        try: os.fsync(f.fileno())
        except Exception: pass
    if os.path.getsize(_longo(temporario)) != len(xml):
        raise OSError('arquivo gravado incompleto')
    os.replace(_longo(temporario), _longo(destino))
    return estado, '/'.join([SUBPASTA] + list(partes))


def _pasta_repo(base):
    return Path(str(base)) / SUBPASTA


_SQL_ERRO = ("INSERT INTO repositorio_copias(doc_id,erro,ultima_tentativa,tentativas) VALUES(?,?,?,1) "
             "ON CONFLICT(doc_id) DO UPDATE SET erro=excluded.erro,ultima_tentativa=excluded.ultima_tentativa,tentativas=tentativas+1")
_SQL_OK = ("INSERT INTO repositorio_copias(doc_id,caminho,sha256,copiado_em,ultima_tentativa,erro,conflito,tentativas) VALUES(?,?,?,?,?,'',?,1) "
           "ON CONFLICT(doc_id) DO UPDATE SET caminho=excluded.caminho,sha256=excluded.sha256,copiado_em=excluded.copiado_em,ultima_tentativa=excluded.ultima_tentativa,erro='',conflito=excluded.conflito,removido=0")


def _gravar(conn, fila):
    """Grava de uma vez (em milissegundos) o que já foi copiado. O banco NUNCA fica travado durante a cópia de arquivos pela rede: antes a
    transação ficava aberta por minutos e as outras telas/buscas davam "database is locked" (V166)."""
    if not fila: return
    for tentativa in range(6):
        try:
            for sql, params in fila: conn.execute(sql, params)
            conn.commit(); fila.clear(); return
        except sqlite3.OperationalError:
            try: conn.rollback()
            except Exception: pass
            time.sleep(0.4 * (tentativa + 1))
    fila.clear()          # não conseguiu gravar agora: esses documentos continuam na fila e são refeitos na próxima rodada


def pendentes(db_path):
    """Quantos documentos do banco ainda não foram copiados."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        preparar_banco(conn)
        return int(conn.execute("SELECT COUNT(*) FROM documents d LEFT JOIN repositorio_copias r ON r.doc_id=d.doc_id WHERE r.copiado_em IS NULL").fetchone()[0] or 0)
    finally:
        conn.close()


def copiar_pendentes(db_path, base, cancelar=None, progresso=None, lote=300, maximo=None):
    """Copia para o servidor os documentos ainda não copiados. Pode ser interrompido e retomado a qualquer momento.

    Devolve {'ok','motivo','novos','existentes','diferentes','erros','restantes'}.
    """
    res = {'ok': True, 'motivo': '', 'novos': 0, 'existentes': 0, 'diferentes': 0, 'erros': 0, 'restantes': 0}
    if not pasta_acessivel(base):
        res.update(ok=False, motivo='inacessivel'); return res
    conn = sqlite3.connect(db_path, timeout=30); conn.row_factory = sqlite3.Row
    try:
        preparar_banco(conn)
        res['restantes'] = pendentes(db_path)
        pasta_repo = _pasta_repo(base)
        os.makedirs(_longo(pasta_repo), exist_ok=True)
        empresas = _Empresas(pasta_repo); falhas_seguidas = 0; feitos = 0; listagens = {}
        limite_tempo = (datetime.now() - _PAUSA_ERRO).isoformat(timespec='seconds')
        while True:
            if cancelar and cancelar():
                res['motivo'] = 'cancelado'; break
            if maximo is not None and feitos >= maximo: break
            linhas = conn.execute(
                """SELECT d.doc_id,d.cnpj,d.family,d.doc_type,d.direction,d.issued_at,d.first_seen_at,d.status,d.access_key,d.xml,c.name AS empresa
                   FROM documents d LEFT JOIN companies c ON c.cnpj=d.cnpj LEFT JOIN repositorio_copias r ON r.doc_id=d.doc_id
                   WHERE r.copiado_em IS NULL AND (r.ultima_tentativa IS NULL OR r.ultima_tentativa<?)
                   ORDER BY d.doc_id LIMIT ?""", (limite_tempo, lote)).fetchall()
            if not linhas: break
            agora = datetime.now().isoformat(timespec='seconds')
            fila = []; ultimo_flush = time.monotonic()
            for linha in linhas:
                if fila and (len(fila) >= 25 or time.monotonic() - ultimo_flush > 2.0):
                    _gravar(conn, fila); ultimo_flush = time.monotonic()
                if cancelar and cancelar():
                    res['motivo'] = 'cancelado'; break
                xml = bytes(linha['xml'] or b'')
                doc_id = linha['doc_id']
                if not xml:
                    fila.append((_SQL_ERRO, (doc_id, 'documento sem XML', agora)))
                    res['erros'] += 1; feitos += 1; continue
                try:
                    partes = _partes(linha, empresas.pasta(linha['cnpj'], linha['empresa']))
                    pasta_doc = str(pasta_repo.joinpath(*partes[:-1]))
                    if pasta_doc not in listagens:
                        listagens[pasta_doc] = _listar(pasta_doc)           # uma ida ao servidor por pasta, não uma por arquivo
                    if listagens[pasta_doc].get(partes[-1]) == len(xml):
                        estado, rel = 'existe', '/'.join([SUBPASTA] + list(partes))      # já está lá (por exemplo, copiado por outro computador)
                    else:
                        estado, rel = copiar_arquivo(pasta_repo, partes, xml)
                        if estado == 'novo': listagens[pasta_doc][partes[-1]] = len(xml)
                except Exception as exc:       # rede caiu, sem permissão, disco cheio...
                    fila.append((_SQL_ERRO, (doc_id, str(exc)[:200], agora)))
                    res['erros'] += 1; falhas_seguidas += 1; feitos += 1
                    if falhas_seguidas >= 3:
                        res.update(ok=False, motivo='falha'); _gravar(conn, fila); res['restantes'] = pendentes(db_path); return res
                    continue
                falhas_seguidas = 0
                fila.append((_SQL_OK, (doc_id, rel, _sha(xml), agora, agora, 1 if estado == 'diferente' else 0)))
                res[{'novo': 'novos', 'existe': 'existentes', 'diferente': 'diferentes'}[estado]] += 1; feitos += 1
            _gravar(conn, fila)
            res['restantes'] = pendentes(db_path)
            if progresso:
                try: progresso(dict(res))
                except Exception: pass
            if res['motivo'] == 'cancelado': break
        res['restantes'] = pendentes(db_path)
        return res
    finally:
        conn.close()


def resumo(db_path):
    """Números para a tela: documentos guardados, copiados, na fila, diferentes, com erro."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        preparar_banco(conn)
        total = int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] or 0)
        copiados = int(conn.execute("SELECT COUNT(*) FROM repositorio_copias r JOIN documents d ON d.doc_id=r.doc_id WHERE r.copiado_em IS NOT NULL").fetchone()[0] or 0)
        diferentes = int(conn.execute("SELECT COUNT(*) FROM repositorio_copias WHERE conflito=1").fetchone()[0] or 0)
        erros = int(conn.execute("SELECT COUNT(*) FROM repositorio_copias r JOIN documents d ON d.doc_id=r.doc_id WHERE r.copiado_em IS NULL AND COALESCE(r.erro,'')<>''").fetchone()[0] or 0)
        ultima = conn.execute("SELECT MAX(copiado_em) FROM repositorio_copias").fetchone()[0] or ''
        return {'total': total, 'copiados': copiados, 'fila': max(total - copiados, 0), 'diferentes': diferentes, 'erros': erros, 'ultima_copia': ultima}
    finally:
        conn.close()


def por_empresa_mes(db_path):
    """[(cnpj, empresa, 'AAAA-MM', documentos, copiados)] — mais recentes primeiro."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        preparar_banco(conn)
        linhas = conn.execute(
            """SELECT d.cnpj, COALESCE(c.name,''), COALESCE(NULLIF(substr(COALESCE(NULLIF(d.issued_at,''),d.first_seen_at),1,7),''),'Sem data') AS mes,
                      COUNT(*), SUM(CASE WHEN r.copiado_em IS NOT NULL THEN 1 ELSE 0 END)
               FROM documents d LEFT JOIN companies c ON c.cnpj=d.cnpj LEFT JOIN repositorio_copias r ON r.doc_id=d.doc_id
               GROUP BY d.cnpj, mes ORDER BY mes DESC, 2""").fetchall()
        return [(a, b, c, int(d or 0), int(e or 0)) for a, b, c, d, e in linhas]
    finally:
        conn.close()


# ------------------------------------------------------------------ cópia diária do banco
def backup_diario(db_path, base, computador=None, manter_dias=30):
    """Uma cópia por dia e por computador do banco de dados, em <pasta>\\Backups\\AAAA-MM-DD. Devolve 'feito', 'ja_feito' ou 'inacessivel'."""
    if not pasta_acessivel(base):
        return 'inacessivel'
    pc = nome_seguro(computador or socket.gethostname(), 30)
    hoje = datetime.now().strftime('%Y-%m-%d')
    pasta = Path(str(base)) / SUBPASTA_BACKUP / hoje
    alvo = pasta / f'central_fiscal_{pc}.zip'
    if os.path.exists(_longo(alvo)):
        return 'ja_feito'
    os.makedirs(_longo(pasta), exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='exato_bk_'))
    try:
        copia = tmp / 'central_fiscal.db'
        origem = sqlite3.connect(db_path, timeout=30); destino = sqlite3.connect(copia)
        try: origem.backup(destino)
        finally: destino.close(); origem.close()
        zip_tmp = tmp / 'bk.zip'
        with zipfile.ZipFile(zip_tmp, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.write(copia, 'central_fiscal.db')
        parcial = Path(str(alvo) + '.tmp')
        shutil.copyfile(zip_tmp, _longo(parcial))
        os.replace(_longo(parcial), _longo(alvo))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # guarda só as últimas cópias DESTE computador
    try:
        limite = datetime.now() - timedelta(days=manter_dias)
        for nome in os.listdir(_longo(Path(str(base)) / SUBPASTA_BACKUP)):
            try: dia = datetime.strptime(nome, '%Y-%m-%d')
            except ValueError: continue
            if dia < limite:
                velho = Path(str(base)) / SUBPASTA_BACKUP / nome / f'central_fiscal_{pc}.zip'
                if os.path.exists(_longo(velho)): os.remove(_longo(velho))
                try: os.rmdir(_longo(velho.parent))
                except OSError: pass
    except Exception:
        pass
    return 'feito'


# ------------------------------------------------------------------ conferência de integridade
def verificar(db_path, base, amostra=200):
    """Confere uma amostra de arquivos já copiados: existem e o conteúdo é o mesmo? Devolve lista de problemas (texto claro)."""
    problemas = []
    if not pasta_acessivel(base):
        return problemas
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        preparar_banco(conn)
        linhas = conn.execute("SELECT doc_id,caminho,sha256 FROM repositorio_copias WHERE copiado_em IS NOT NULL AND COALESCE(removido,0)=0 AND caminho<>''").fetchall()
        if len(linhas) > amostra:
            linhas = random.sample(linhas, amostra)
        voltam = []          # só grava no banco DEPOIS de ler a rede (nada de transação aberta durante o acesso ao servidor)
        for doc_id, caminho, sha in linhas:
            destino = Path(str(base)).joinpath(*caminho.split('/'))
            try:
                if not os.path.exists(_longo(destino)):
                    problemas.append(f'Arquivo sumiu do servidor: {caminho}')
                    voltam.append((doc_id,))      # volta para a fila
                elif _sha(_ler(destino)) != sha:
                    problemas.append(f'Arquivo foi alterado no servidor: {caminho}')
            except Exception as exc:
                problemas.append(f'Não consegui conferir {caminho}: {str(exc)[:80]}')
        _gravar(conn, [("UPDATE repositorio_copias SET copiado_em=NULL, erro='arquivo sumiu', ultima_tentativa=NULL WHERE doc_id=?", v) for v in voltam])
    finally:
        conn.close()
    return problemas


# ------------------------------------------------------------------ prazo de guarda (só avisa; apagar exige confirmação)
def _meses_vencidos(base, meses):
    """Pastas <empresa>/<ano>/<mês> mais antigas que o prazo."""
    corte = datetime.now().year * 12 + datetime.now().month - int(meses)
    pasta_repo = _pasta_repo(base); achadas = []
    try:
        for emp in os.listdir(_longo(pasta_repo)):
            for ano in os.listdir(_longo(pasta_repo / emp)):
                if not re.fullmatch(r'\d{4}', ano): continue
                for mes in os.listdir(_longo(pasta_repo / emp / ano)):
                    if not re.fullmatch(r'\d{2}', mes): continue
                    if int(ano) * 12 + int(mes) < corte:
                        achadas.append((emp, ano, mes))
    except Exception:
        pass
    return achadas


def vencidos(base, meses=MESES_PADRAO):
    """{'arquivos': n, 'bytes': n, 'pastas': [(empresa, ano, mes)]} — o que já passou do prazo no servidor."""
    if not pasta_acessivel(base):
        return {'arquivos': 0, 'bytes': 0, 'pastas': []}
    arquivos = tamanho = 0; pastas = _meses_vencidos(base, meses)
    pasta_repo = _pasta_repo(base)
    for emp, ano, mes in pastas:
        for raiz, _d, nomes in os.walk(_longo(pasta_repo / emp / ano / mes)):
            for n in nomes:
                if n.endswith('.xml'):
                    arquivos += 1
                    try: tamanho += os.path.getsize(os.path.join(raiz, n))
                    except OSError: pass
    return {'arquivos': arquivos, 'bytes': tamanho, 'pastas': pastas}


def apagar_vencidos(db_path, base, meses=MESES_PADRAO):
    """Remove do SERVIDOR as pastas de meses fora do prazo (o banco local não é tocado). Só chamar depois da confirmação do usuário."""
    info = vencidos(base, meses); pasta_repo = _pasta_repo(base)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        preparar_banco(conn)
        marcas = []
        for emp, ano, mes in info['pastas']:
            shutil.rmtree(_longo(pasta_repo / emp / ano / mes), ignore_errors=True)
            marcas.append(("UPDATE repositorio_copias SET removido=1 WHERE caminho LIKE ?", (f'{SUBPASTA}/{emp}/{ano}/{mes}/%',)))
            try: os.rmdir(_longo(pasta_repo / emp / ano))
            except OSError: pass
            try: os.rmdir(_longo(pasta_repo / emp))
            except OSError: pass
        _gravar(conn, marcas)
    finally:
        conn.close()
    return info


# ------------------------------------------------------------------ restaurar
def listar_para_restaurar(base):
    """[(cnpj, familia, caminho)] de todos os XMLs do repositório (para reconstruir o banco)."""
    pasta_repo = _pasta_repo(base); achados = []
    try:
        for emp in sorted(os.listdir(_longo(pasta_repo))):
            m = re.match(r'(\d{14})\b', emp)
            if not m: continue
            for raiz, _d, nomes in os.walk(_longo(pasta_repo / emp)):
                partes = Path(raiz.replace('\\\\?\\UNC\\', '\\\\').replace('\\\\?\\', '')).parts
                familia = ''
                for p in partes:
                    base_tipo = p[len('Eventos '):] if p.startswith('Eventos ') else p
                    if base_tipo in _TIPOS_REVERSO: familia = _TIPOS_REVERSO[base_tipo]; break
                for n in sorted(nomes):
                    if n.endswith('.xml') and not n.startswith('.'):
                        achados.append((m.group(1), familia, os.path.join(raiz, n)))
    except Exception:
        pass
    return achados


def ler_xml(caminho):
    return _ler(caminho)
