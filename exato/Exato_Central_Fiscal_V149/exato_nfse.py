"""NFS-e Padrão Nacional: leitura dos XMLs e comunicação com o ADN (Ambiente de Dados Nacional).

Este módulo não depende da interface nem do banco: recebe e devolve dados simples, para poder ser testado
em qualquer computador. A comunicação real (certificado digital do Windows) fica em `adn_transport_windows`.

Base técnica (fontes públicas secundárias; conferir com o Manual dos Contribuintes - APIs ADN):
  GET {base}/contribuintes/DFe/{ultNSU}  -> JSON com LoteDFe (até 50 documentos),
  cada item com NSU, ChaveAcesso, TipoDocumento, TipoEvento, ArquivoXml (gzip + base64), DataHoraGeracao.
  Autenticação: TLS mútuo com o certificado digital do contribuinte (sem token).
"""
import base64
import gzip
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

ADN_PRODUCAO = 'https://adn.nfse.gov.br/contribuintes'
ADN_HOMOLOGACAO = 'https://adn.producaorestrita.nfse.gov.br/contribuintes'
ADN_PAGE_SIZE = 50
ADN_PAUSE_SECONDS = 0.5          # pausa entre lotes: o ADN bloqueia consultas em rajada
NFSE_CANCEL_EVENT_TYPES = {'101101', '105102'}   # cancelamento e cancelamento por substituição


class NfseError(Exception):
    """Falha esperada de comunicação ou de formato (a mensagem já é amigável)."""


# ---------------------------------------------------------------- XML
def _local(tag):
    return str(tag).rsplit('}', 1)[-1]


def _digits(value):
    return re.sub(r'\D', '', str(value or ''))


def _find_children(node, name):
    return [c for c in list(node) if _local(c.tag) == name]


def _first(node, *path):
    """Primeiro descendente seguindo o caminho de nomes locais (ignora namespace)."""
    cur = [node]
    for name in path:
        nxt = []
        for n in cur:
            nxt.extend(_find_children(n, name))
        cur = nxt
        if not cur:
            return None
    return cur[0]


def _text(node, *path):
    n = _first(node, *path) if path else node
    return (n.text or '').strip() if n is not None and n.text else ''


def _party(node):
    if node is None:
        return {'doc': '', 'nome': ''}
    return {'doc': _digits(_text(node, 'CNPJ') or _text(node, 'CPF')), 'nome': _text(node, 'xNome')}


def _decimal(value):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def is_nfse_xml(xml_bytes):
    head = bytes(xml_bytes)[:800]
    return bool(re.search(rb'<(?:[A-Za-z_][\w.-]*:)?NFSe\b', head) or b'sped.fazenda.gov.br/nfse' in head and b'infNFSe' in bytes(xml_bytes)[:4000])


def is_nfse_event_xml(xml_bytes):
    head = bytes(xml_bytes)[:1200]
    return bool(re.search(rb'<(?:[A-Za-z_][\w.-]*:)?evento\b', head) or b'pedRegEvento' in bytes(xml_bytes)[:4000])


def parse_nfse(xml_bytes, consulta_cnpj=''):
    """Metadados de uma NFS-e nacional, no mesmo formato usado pelas demais famílias."""
    result = {'family': 'nfse', 'tipo': 'NFS-e', 'empresa': 'Empresa não identificada', 'direcao': 'Entrada',
              'numero': '', 'serie': '', 'data': '', 'valor': Decimal('0.00'), 'chave': '',
              'prestador': {'doc': '', 'nome': ''}, 'tomador': {'doc': '', 'nome': ''}, 'intermediario': {'doc': '', 'nome': ''},
              'municipio': '', 'situacao': 'Autorizado'}
    try:
        root = ET.fromstring(bytes(xml_bytes))
    except ET.ParseError as exc:
        raise NfseError(f'XML de NFS-e inválido: {exc}')
    inf = root if _local(root.tag) == 'infNFSe' else _first(root, 'infNFSe')
    if inf is None:
        raise NfseError('O XML não é uma NFS-e do padrão nacional (não há infNFSe).')
    ident = inf.attrib.get('Id') or ''
    m = re.search(r'(\d{50})', ident)
    result['chave'] = m.group(1) if m else _digits(ident)
    result['numero'] = _text(inf, 'nNFSe')
    result['municipio'] = _text(inf, 'xLocEmi') or _text(inf, 'xLocPrestacao')
    dps = _first(inf, 'DPS', 'infDPS')
    prest = _party(_first(dps, 'prest')) if dps is not None else {'doc': '', 'nome': ''}
    if not prest['doc']:
        prest = _party(_first(inf, 'emit'))
    result['prestador'] = prest
    if dps is not None:
        result['tomador'] = _party(_first(dps, 'toma'))
        result['intermediario'] = _party(_first(dps, 'interm'))
        result['serie'] = _text(dps, 'serie')
        result['data'] = _text(dps, 'dhEmi') or _text(dps, 'dCompet')
        valor = _decimal(_text(dps, 'valores', 'vServPrest', 'vServ'))
    else:
        valor = None
    if not result['data']:
        result['data'] = _text(inf, 'dhProc')
    if valor is None:
        valor = _decimal(_text(inf, 'valores', 'vLiq'))
    result['valor'] = valor if valor is not None else Decimal('0.00')
    cnpjq = _digits(consulta_cnpj)
    if cnpjq and cnpjq == prest['doc']:
        result['direcao'] = 'Saída'; result['empresa'] = prest['nome'] or 'Empresa não identificada'
    elif cnpjq and cnpjq == result['tomador']['doc']:
        result['direcao'] = 'Entrada'; result['empresa'] = result['tomador']['nome'] or prest['nome'] or 'Empresa não identificada'
    elif cnpjq and cnpjq == result['intermediario']['doc']:
        result['direcao'] = 'Entrada'; result['empresa'] = result['intermediario']['nome'] or prest['nome'] or 'Empresa não identificada'
    else:
        # O CNPJ consultado não participa da nota: não inventa o nome da empresa.
        result['empresa'] = 'Empresa não identificada' if cnpjq else (prest['nome'] or result['tomador']['nome'] or 'Empresa não identificada')
        result['direcao'] = 'Saída' if prest['doc'] else 'Entrada'
    return result


def parse_nfse_event(xml_bytes):
    """Dados mínimos de um evento de NFS-e: chave da nota, tipo (101101 = cancelamento) e se cancela."""
    out = {'key': '', 'type': '', 'seq': '1', 'cancels': False}
    data = bytes(xml_bytes)
    m = re.search(rb'<(?:[A-Za-z_][\w.-]*:)?chNFSe\s*>\s*(\d{50})\s*<', data)
    if m:
        out['key'] = m.group(1).decode('ascii')
    m = re.search(rb'<(?:[A-Za-z_][\w.-]*:)?tpEvento\s*>\s*(\d+)\s*<', data) or re.search(rb'<(?:[A-Za-z_][\w.-]*:)?e(\d{6})\b', data)
    if m:
        out['type'] = m.group(1).decode('ascii')
    m = re.search(rb'<(?:[A-Za-z_][\w.-]*:)?nPedRegEvento\s*>\s*(\d+)\s*<', data)
    if m:
        out['seq'] = m.group(1).decode('ascii')
    out['cancels'] = bool(out['key'] and out['type'] in NFSE_CANCEL_EVENT_TYPES)
    return out


# ---------------------------------------------------------------- ADN (JSON)
def decode_arquivo_xml(value):
    """ArquivoXml do ADN: base64 de um arquivo gzip. Aceita também XML puro em base64."""
    try:
        raw = base64.b64decode(value, validate=False)
    except Exception as exc:
        raise NfseError(f'Conteúdo do documento não está em base64: {exc}')
    try:
        return gzip.decompress(raw)
    except OSError:
        if raw.lstrip()[:1] == b'<':
            return raw
        raise NfseError('Não foi possível descompactar o documento recebido do ADN.')


def _ci(d, *names):
    """Lê uma chave de um dict ignorando maiúsculas/minúsculas."""
    low = {str(k).lower(): v for k, v in (d or {}).items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def parse_adn_response(status_code, body_text):
    """Interpreta a resposta do ADN. Devolve dict(items, status, errors, max_nsu, empty)."""
    out = {'items': [], 'status': '', 'errors': [], 'max_nsu': 0, 'empty': False, 'http': int(status_code)}
    text = (body_text or '').strip()
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    out['status'] = str(_ci(data, 'StatusProcessamento') or '')
    for err in (_ci(data, 'Erros', 'Erro') or []):
        if isinstance(err, dict):
            out['errors'].append(str(_ci(err, 'Descricao', 'Mensagem', 'Codigo') or err)[:200])
        else:
            out['errors'].append(str(err)[:200])
    code = int(status_code)
    if code in (401, 403):
        raise NfseError('O ADN recusou o certificado digital (acesso negado). Confira se o certificado é válido e pertence à empresa consultada.')
    if code == 429:
        raise NfseError('O ADN pediu para aguardar antes de uma nova consulta (muitas consultas seguidas). Tente novamente em alguns minutos.')
    if code >= 500:
        raise NfseError(f'O ADN está indisponível no momento (erro {code}). Tente novamente mais tarde.')
    lote = _ci(data, 'LoteDFe') or []
    for item in lote if isinstance(lote, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            nsu = int(_ci(item, 'NSU') or 0)
        except (TypeError, ValueError):
            nsu = 0
        tipo = str(_ci(item, 'TipoDocumento') or '').upper()
        arquivo = _ci(item, 'ArquivoXml')
        xml = decode_arquivo_xml(arquivo) if arquivo else b''
        out['items'].append({'nsu': nsu, 'chave': _digits(_ci(item, 'ChaveAcesso')), 'tipo_documento': tipo,
                             'tipo_evento': str(_ci(item, 'TipoEvento') or ''), 'xml': xml,
                             'gerado_em': str(_ci(item, 'DataHoraGeracao') or '')})
        out['max_nsu'] = max(out['max_nsu'], nsu)
    status_up = out['status'].upper()
    out['empty'] = not out['items'] and (code == 404 or 'NENHUM' in status_up or code == 200)
    if code >= 400 and code != 404 and not out['items']:
        detail = '; '.join(out['errors']) or text[:160]
        raise NfseError(f'O ADN recusou a consulta (erro {code}). {detail}'.strip())
    return out


def classify_item(item):
    """'nfse' | 'evento' | 'outro' para um item do lote do ADN."""
    tipo = item.get('tipo_documento') or ''
    xml = item.get('xml') or b''
    if 'EVENTO' in tipo or (xml and is_nfse_event_xml(xml)):
        return 'evento'
    if 'NFSE' in tipo.replace('-', '').replace('_', '') or (xml and is_nfse_xml(xml)):
        return 'nfse'
    return 'outro'


# ---------------------------------------------------------------- transporte
_PS_GET = r'''param([string]$Thumbprint,[string]$Url)
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$cert=$null
foreach($path in @("Cert:\CurrentUser\My\$Thumbprint","Cert:\LocalMachine\My\$Thumbprint")) { try { $c=Get-Item -Path $path -ErrorAction Stop; if($c.HasPrivateKey){$cert=$c;break} } catch {} }
if(-not $cert){throw 'Certificado com chave privada não localizado no repositório do Windows.'}
$request=[System.Net.HttpWebRequest]::Create($Url); $request.Method='GET'; $request.Accept='application/json'
$request.UserAgent='ExatoCentralFiscal/1.0'; $request.ClientCertificates.Add($cert)|Out-Null; $request.Timeout=60000
try { $response=[Net.HttpWebResponse]$request.GetResponse(); $code=[int]$response.StatusCode; $reader=New-Object IO.StreamReader($response.GetResponseStream(),[Text.Encoding]::UTF8); $content=$reader.ReadToEnd(); $reader.Close(); $response.Close() }
catch [Net.WebException] { $resp=$_.Exception.Response; if($resp){ $code=[int]$resp.StatusCode; $reader=New-Object IO.StreamReader($resp.GetResponseStream(),[Text.Encoding]::UTF8); $content=$reader.ReadToEnd(); $reader.Close(); $resp.Close() } else { throw } }
Write-Output ('STATUS:'+$code); Write-Output $content'''


def adn_transport_windows(url, thumbprint, timeout=75):
    """GET com o certificado do Windows (TLS mútuo). Devolve (status_http, corpo_texto). Só funciona no Windows."""
    thumb = re.sub(r'\s+', '', thumbprint or '').upper()
    if not thumb:
        raise NfseError('Certificado digital não informado.')
    script = base64.b64encode(_PS_GET.encode('utf-8')).decode('ascii')
    command = ("$s=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + script + "'));$sb=[ScriptBlock]::Create($s);& $sb "
               + f"-Thumbprint '{thumb}' -Url '{url}'")
    try:
        proc = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', command],
                              capture_output=True, text=True, timeout=timeout, encoding='utf-8', errors='replace')
    except FileNotFoundError:
        raise NfseError('A busca de NFS-e com certificado só funciona no Windows (PowerShell não encontrado).')
    except subprocess.TimeoutExpired:
        raise NfseError('A comunicação com o ADN excedeu o tempo limite. Tente novamente.')
    out = (proc.stdout or '').strip()
    m = re.match(r'STATUS:(\d{3})\s*\n?(.*)', out, re.S)
    if not m:
        err = (proc.stderr or out or '').strip()
        raise NfseError('Não foi possível consultar o ADN: ' + (err[:300] or 'sem resposta.'))
    return int(m.group(1)), m.group(2)


def adn_fetch_batch(thumbprint, ult_nsu, homologacao=False, cnpj_consulta='', transport=adn_transport_windows):
    """Uma consulta ao ADN a partir do último NSU conhecido."""
    base = ADN_HOMOLOGACAO if homologacao else ADN_PRODUCAO
    url = f'{base}/DFe/{int(ult_nsu)}'
    if cnpj_consulta:
        url += f'?cnpjConsulta={_digits(cnpj_consulta)}'
    status, body = transport(url, thumbprint)
    return parse_adn_response(status, body)


def fetch_all_new(thumbprint, ult_nsu, homologacao=False, cnpj_consulta='', transport=adn_transport_windows,
                  max_batches=400, progress=None, cancelled=None, sleep=time.sleep):
    """Busca em lotes até acabar. Devolve (items, ultimo_nsu, resumo). Não grava nada."""
    items, last = [], int(ult_nsu)
    batches = 0
    while batches < max_batches:
        if cancelled and cancelled():
            return items, last, {'batches': batches, 'cancelled': True}
        res = adn_fetch_batch(thumbprint, last, homologacao, cnpj_consulta, transport)
        batches += 1
        if not res['items']:
            break
        items.extend(res['items'])
        new_last = max(res['max_nsu'], last)
        if progress:
            progress(len(items), batches)
        if new_last <= last:
            break
        last = new_last
        sleep(ADN_PAUSE_SECONDS)
    return items, last, {'batches': batches, 'cancelled': False}


# ---------------------------------------------------------------- importação de arquivos (XML ou ZIP)
def read_nfse_files(paths, consulta_cnpj):
    """Lê XMLs de NFS-e (soltos ou dentro de ZIP) baixados do Emissor Nacional.

    Devolve dict(items, outros_cnpj, invalidos, lidos). Só entram as notas em que o CNPJ da empresa é
    prestador, tomador ou intermediário; eventos entram se forem de uma nota dessa empresa ou ainda desconhecida.
    """
    import zipfile
    from pathlib import Path
    cnpjq = _digits(consulta_cnpj)
    out = {'items': [], 'outros_cnpj': 0, 'invalidos': [], 'lidos': 0}
    seen = set()

    def handle(name, data):
        out['lidos'] += 1
        try:
            if is_nfse_event_xml(data):
                ev = parse_nfse_event(data)
                if not ev['key']:
                    raise NfseError('evento sem chave de NFS-e')
                if cnpjq and ev['key'][8:22] != cnpjq and cnpjq not in ev['key']:
                    pass  # a chave do evento não indica as partes; o evento só tem efeito sobre notas já guardadas desta empresa
                key = ('E', ev['key'], ev['type'], ev['seq'])
                if key not in seen:
                    seen.add(key)
                    out['items'].append({'nsu': 0, 'chave': ev['key'], 'tipo_documento': 'EVENTO', 'tipo_evento': ev['type'], 'xml': data})
                return
            meta = parse_nfse(data, cnpjq)
            parties = {meta['prestador']['doc'], meta['tomador']['doc'], meta['intermediario']['doc']}
            if cnpjq and cnpjq not in parties:
                out['outros_cnpj'] += 1
                return
            key = ('N', meta['chave'])
            if key not in seen:
                seen.add(key)
                out['items'].append({'nsu': 0, 'chave': meta['chave'], 'tipo_documento': 'NFSE', 'tipo_evento': '', 'xml': data})
        except NfseError as exc:
            out['invalidos'].append(f'{name}: {exc}')

    for raw in paths or []:
        path = Path(raw)
        try:
            if path.suffix.lower() == '.zip':
                with zipfile.ZipFile(path) as zf:
                    for info in zf.infolist():
                        if info.filename.lower().endswith('.xml') and not info.is_dir():
                            handle(f'{path.name}/{info.filename}', zf.read(info))
            elif path.suffix.lower() == '.xml':
                handle(path.name, path.read_bytes())
        except (OSError, zipfile.BadZipFile) as exc:
            out['invalidos'].append(f'{path.name}: {exc}')
    return out
