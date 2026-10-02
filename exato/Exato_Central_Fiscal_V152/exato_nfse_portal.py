"""NFS-e: acesso por usuário e senha ao portal do Emissor Nacional (navegador automatizado).

MODO EM CALIBRAÇÃO: os endereços e seletores do portal abaixo foram montados a partir de informações públicas
e NÃO puderam ser conferidos contra o portal real (o ambiente de desenvolvimento não alcança nfse.gov.br).
Tudo o que depende do desenho do portal está no dicionário PORTAL, para ajustar sem mexer na lógica.
Quando um passo falha, `PortalDiagnostics` guarda imagem, endereço e HTML da tela (sem a senha) em
Logs/nfse_portal/<data>/ para que o ajuste seja feito com dados reais.

V152 (calibrado com o retorno real do portal): o download do XML é feito DE DENTRO da página (o portal recusa, com
erro 403, pedidos feitos fora do navegador); o portal só aceita períodos de até 30 dias, então períodos maiores são
divididos em janelas; o acesso tenta primeiro sem janela e só mostra o navegador se o portal pedir confirmação de
segurança; a sessão do portal pode ser reaproveitada (o aplicativo a guarda protegida pelo Windows).

A senha nunca é registrada nem enviada a lugar nenhum além do portal. Se o usuário pedir, o aplicativo a guarda
criptografada (proteção do Windows) – isso acontece fora deste módulo.
"""
import base64
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import exato_nfse as nfse

PORTAL = {
    'login_url': 'https://www.nfse.gov.br/EmissorNacional/Login',
    'lists': {'Emitidas': 'https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas',
              'Recebidas': 'https://www.nfse.gov.br/EmissorNacional/Notas/Recebidas'},
    'xml_url': 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/{chave}',
    'xml_link_re': r'/Notas/Download/NFSe/(\d{50})',
    'user_selectors': ['input[name="Inscricao"]', '#Inscricao', 'input[name*="nscri" i]', 'input[type="text"]'],
    'pass_selectors': ['input[name="Senha"]', '#Senha', 'input[type="password"]'],
    'submit_selectors': ['button[type="submit"]', 'input[type="submit"]', 'button:has-text("Entrar")'],
    'next_selectors': ['a[rel="next"]', 'a[aria-label*="róxima"]', 'a:has-text("Próxima")', 'li.next a'],
    'logged_in_hint': 'Login',          # enquanto a URL contiver isto, ainda não entrou
    'captcha_hint': ['captcha', 'recaptcha', 'hcaptcha', 'turnstile'],
    'date_params': ('datainicio', 'datafim'),
    'max_pages': 200,
    'max_window_days': 30,           # o portal recusa períodos maiores que 30 dias
    'headless_login_seconds': 40,    # sem janela: se não entrar nesse tempo (ou pedir captcha), mostra a janela
    'login_wait_seconds': 300,
}


class PortalDiagnostics:
    def __init__(self, log_dir):
        self.dir = Path(log_dir) / 'nfse_portal' / datetime.now().strftime('%Y%m%d_%H%M%S')

    def save(self, page, step, error=''):
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(self.dir / f'{step}.png'))
            html = page.content()
            html = re.sub(r'(<input[^>]*type=["\']password["\'][^>]*value=["\'])[^"\']*', r'\1***', html, flags=re.I)
            (self.dir / f'{step}.html').write_text(html, encoding='utf-8', errors='replace')
            (self.dir / f'{step}.txt').write_text(f'Passo: {step}\nEndereço: {page.url}\nErro: {error}\n', encoding='utf-8')
        except Exception:
            pass
        return self.dir


def _first_visible(page, selectors, timeout=4000):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state='visible', timeout=timeout)
            return loc
        except Exception:
            continue
    return None


def _has_captcha(page, portal):
    try:
        html = page.content().lower()
    except Exception:
        return False
    return any(h in html for h in portal['captcha_hint'])


def login(page, user, password, portal, progress=None, cancelled=None, diag=None, headless_wait=None):
    page.goto(portal['login_url'], wait_until='domcontentloaded', timeout=60000)
    u = _first_visible(page, portal['user_selectors'])
    p = _first_visible(page, portal['pass_selectors'])
    if u is None or p is None:
        where = diag.save(page, 'login_campos', 'campos de usuário/senha não encontrados') if diag else ''
        raise nfse.NfseError(f'Não encontrei os campos de usuário e senha na tela de entrada do portal. O Exato guardou o que viu em {where}. Envie essa pasta para o suporte ajustar o programa.')
    u.fill(re.sub(r'\D', '', user) if re.sub(r'\D', '', user) else user)
    p.fill(password)
    if progress: progress('Enviando usuário e senha ao portal...')
    submit = _first_visible(page, portal['submit_selectors'], timeout=2500)
    if submit is not None:
        submit.click()
    else:
        p.press('Enter')
    deadline = time.time() + (headless_wait if headless_wait else portal['login_wait_seconds'])
    warned = False
    while time.time() < deadline:
        if cancelled and cancelled():
            raise nfse.NfseError('Busca cancelada.')
        try:
            page.wait_for_load_state('domcontentloaded', timeout=1500)
        except Exception:
            pass
        if portal['logged_in_hint'].lower() not in page.url.lower():
            return
        if headless_wait and _has_captcha(page, portal):
            raise NeedVisibleBrowser()
        if _has_captcha(page, portal) and not warned:
            warned = True
            if progress: progress('O portal pediu confirmação (captcha). Resolva-a na janela do navegador; o Exato continua sozinho em seguida.')
        page.wait_for_timeout(1000)
    if headless_wait:
        raise NeedVisibleBrowser()
    where = diag.save(page, 'login_espera', 'o portal não liberou o acesso a tempo') if diag else ''
    raise nfse.NfseError(f'O portal não liberou o acesso em {portal["login_wait_seconds"] // 60} minutos (senha incorreta ou confirmação não concluída). Detalhes em {where}.')


def _list_url(base, date_from, date_to, portal, page_no):
    q = []
    if date_from: q.append(f"{portal['date_params'][0]}={date_from.strftime('%d/%m/%Y')}")
    if date_to: q.append(f"{portal['date_params'][1]}={date_to.strftime('%d/%m/%Y')}")
    if page_no > 1: q.append(f'pg={page_no}')
    return base + ('?' + '&'.join(q) if q else '')


def collect_keys(page, base_url, date_from, date_to, portal, progress=None, cancelled=None, diag=None, label=''):
    """Percorre as páginas de uma lista (Emitidas/Recebidas) e devolve as chaves das NFS-e encontradas."""
    keys, seen_pages = [], set()
    regex = re.compile(portal['xml_link_re'])
    page.goto(_list_url(base_url, date_from, date_to, portal, 1), wait_until='domcontentloaded', timeout=60000)
    for n in range(1, portal['max_pages'] + 1):
        if cancelled and cancelled():
            break
        html = page.content()
        found = list(dict.fromkeys(regex.findall(html)))
        sig = tuple(found)
        if n == 1 and not found and 'login' in page.url.lower():
            where = diag.save(page, f'lista_{label}', 'voltou para o login') if diag else ''
            raise nfse.NfseError(f'O portal voltou para a tela de login ao abrir as notas {label.lower()}. Detalhes em {where}.')
        if sig in seen_pages:
            break   # a mesma página de novo: acabou
        seen_pages.add(sig)
        new = [k for k in found if k not in keys]
        keys.extend(new)
        if progress: progress(f'Notas {label.lower()}: {len(keys)} encontrada(s) (página {n})...')
        nxt = _first_visible(page, portal['next_selectors'], timeout=800)
        if nxt is None or not found:
            break
        try:
            nxt.click(); page.wait_for_load_state('domcontentloaded', timeout=30000)
        except Exception:
            break
    return keys


class NeedVisibleBrowser(Exception):
    """O portal exigiu confirmação (captcha) ou não liberou o acesso sem janela: repetir com o navegador visível."""


def period_windows(date_from, date_to, max_days=30):
    """Divide [date_from, date_to] em janelas de até max_days dias. Sem datas: uma janela aberta (o portal usa os últimos 30 dias)."""
    if not date_from and not date_to:
        return [(None, None)]
    if not date_to:
        from datetime import date as _date
        date_to = _date.today()
    if not date_from:
        date_from = date_to - timedelta(days=max_days - 1)
    out, cur = [], date_from
    while cur <= date_to:
        end = min(cur + timedelta(days=max_days - 1), date_to)
        out.append((cur, end)); cur = end + timedelta(days=1)
    return out


_JS_FETCH = """async (url) => {
  const r = await fetch(url, {credentials: 'include', headers: {'Accept': 'application/xml,text/xml,*/*'}});
  const buf = new Uint8Array(await r.arrayBuffer());
  let bin = ''; const step = 0x8000;
  for (let i = 0; i < buf.length; i += step) bin += String.fromCharCode.apply(null, buf.subarray(i, i + step));
  return {status: r.status, b64: btoa(bin)};
}"""


def download_xml(page, url):
    """Baixa o XML de dentro da página já autenticada (mesma origem, com os cabeçalhos de navegador). Devolve bytes."""
    try:
        res = page.evaluate(_JS_FETCH, url)
        if res and res.get('status') == 200:
            return base64.b64decode(res['b64'])
        status = (res or {}).get('status')
    except Exception as exc:
        status = f'{type(exc).__name__}'
    # segunda tentativa: como se o usuário clicasse em "Download XML"
    try:
        with page.expect_download(timeout=30000) as dl:
            page.evaluate("u => { const a = document.createElement('a'); a.href = u; a.download = ''; document.body.appendChild(a); a.click(); a.remove(); }", url)
        path = dl.value.path()
        return Path(path).read_bytes()
    except Exception as exc:
        raise nfse.NfseError(f'HTTP {status}; clique: {type(exc).__name__}')


def _logged_in(page, portal):
    return portal['logged_in_hint'].lower() not in page.url.lower()


def _open_context(browser, session_state):
    kwargs = dict(accept_downloads=True, locale='pt-BR', viewport={'width': 1200, 'height': 800})
    if session_state:
        try:
            kwargs['storage_state'] = json.loads(session_state) if isinstance(session_state, str) else session_state
        except Exception:
            pass
    try:
        return browser.new_context(**kwargs)
    except Exception:
        kwargs.pop('storage_state', None)
        return browser.new_context(**kwargs)


def _session_valid(page, portal):
    """Com a sessão guardada: abre a lista e vê se o portal não mandou de volta ao login."""
    try:
        page.goto(list(portal['lists'].values())[0], wait_until='domcontentloaded', timeout=45000)
        return _logged_in(page, portal) and not _first_visible(page, portal['pass_selectors'], timeout=600)
    except Exception:
        return False


def _run_once(pw, opts, user, password, cnpjq, date_from, date_to, portal, diag, progress, cancelled, session_state, on_session, headless_wait):
    items, info = [], {'emitidas': 0, 'recebidas': 0, 'fora_periodo': 0, 'outras_empresas': 0, 'falhas': 0, 'sessao_reaproveitada': False}
    try:
        browser = pw.chromium.launch(**opts)
    except Exception:
        raise nfse.NfseError('Não consegui abrir o navegador Microsoft Edge. Confira se ele está instalado e tente de novo.')
    page = None
    try:
        ctx = _open_context(browser, session_state)
        page = ctx.new_page()
        reused = bool(session_state) and _session_valid(page, portal)
        if reused:
            info['sessao_reaproveitada'] = True
            if progress: progress('Acesso ao portal já liberado (sessão anterior).')
        else:
            if not password:
                raise nfse.NfseError('A sessão anterior no portal expirou e não há senha para entrar de novo. Informe a senha.')
            login(page, user, password, portal, progress, cancelled, diag, headless_wait=headless_wait)
            if progress: progress('Acesso liberado. Buscando as notas...')
        if on_session:
            try: on_session(json.dumps(ctx.storage_state()))
            except Exception: pass
        seen = set()
        windows = period_windows(date_from, date_to, portal.get('max_window_days', 30))
        for label, base in portal['lists'].items():
            for w_from, w_to in windows:
                if cancelled and cancelled():
                    break
                keys = collect_keys(page, base, w_from, w_to, portal, progress, cancelled, diag, label)
                for i, key in enumerate(keys, 1):
                    if cancelled and cancelled():
                        break
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        data = download_xml(page, portal['xml_url'].format(chave=key))
                        meta = nfse.parse_nfse(data, cnpjq)
                    except Exception as exc:
                        info['falhas'] += 1
                        if info['falhas'] == 1:
                            diag.save(page, f'download_{key[:12]}', str(exc))
                        continue
                    day = meta['data'][:10]
                    if (date_from and day and day < date_from.strftime('%Y-%m-%d')) or (date_to and day and day > date_to.strftime('%Y-%m-%d')):
                        info['fora_periodo'] += 1; continue
                    parties = {meta['prestador']['doc'], meta['tomador']['doc'], meta['intermediario']['doc']}
                    if cnpjq and cnpjq not in parties:
                        info['outras_empresas'] += 1; continue
                    info['emitidas' if label == 'Emitidas' else 'recebidas'] += 1
                    items.append({'nsu': 0, 'chave': meta['chave'], 'tipo_documento': 'NFSE', 'tipo_evento': '', 'xml': data})
                    if progress and i % 5 == 0:
                        progress(f'Baixando XMLs de notas {label.lower()}: {i} de {len(keys)}...')
        return items, info
    except (nfse.NfseError, NeedVisibleBrowser):
        raise
    except Exception as exc:
        where = diag.save(page, 'erro_inesperado', f'{type(exc).__name__}: {exc}') if page is not None else ''
        raise nfse.NfseError(f'O acesso ao portal não funcionou como esperado. O Exato guardou o que viu em {where}.')
    finally:
        try: browser.close()
        except Exception: pass


def fetch_via_portal(user, password, cnpj, date_from, date_to, log_dir, portal=None, progress=None, cancelled=None,
                     browser_options=None, session_state=None, on_session=None, fallback_options=None):
    """Entra no portal, lista as NFS-e emitidas e recebidas do período e baixa os XMLs.

    Tenta primeiro sem janela; se o portal pedir confirmação de segurança (ou não liberar o acesso), repete com o
    navegador visível (`fallback_options`). `session_state`/`on_session`: sessão do portal guardada pelo aplicativo.
    Devolve (items, info). `items` no mesmo formato do Emissor Nacional, pronto para db_upsert_nfse_items.
    """
    portal = portal or PORTAL
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        raise nfse.NfseError('Para entrar no portal com usuário e senha, o Exato precisa de um componente adicional.\nFeche o Exato e abra o arquivo INSTALAR_COMPONENTE_NFSE.bat, que está na pasta do programa. Depois abra o Exato de novo.\n(O componente usa o navegador Microsoft Edge, já instalado no Windows.)')
    diag = PortalDiagnostics(log_dir)
    cnpjq = re.sub(r'\D', '', cnpj or '')
    first = {'channel': 'msedge', 'headless': True, 'args': ['--window-size=1200,850']}
    first.update(browser_options or {})
    second = dict(first); second.update({'headless': False}); second.update(fallback_options or {})
    with sync_playwright() as pw:
        try:
            result = _run_once(pw, first, user, password, cnpjq, date_from, date_to, portal, diag, progress, cancelled, session_state, on_session,
                               headless_wait=portal.get('headless_login_seconds', 40) if first.get('headless') else None)
        except NeedVisibleBrowser:
            if progress: progress('O portal pediu confirmação de segurança. Vou abrir a janela do navegador: resolva-a e o Exato continua sozinho.')
            result = _run_once(pw, second, user, password, cnpjq, date_from, date_to, portal, diag, progress, cancelled, None, on_session, headless_wait=None)
    items, info = result
    info['diagnostico'] = str(diag.dir) if diag.dir.exists() else ''
    return items, info
