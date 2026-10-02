"""NFS-e: acesso por usuário e senha ao portal do Emissor Nacional (navegador automatizado).

MODO EM CALIBRAÇÃO: os endereços e seletores do portal abaixo foram montados a partir de informações públicas
e NÃO puderam ser conferidos contra o portal real (o ambiente de desenvolvimento não alcança nfse.gov.br).
Tudo o que depende do desenho do portal está no dicionário PORTAL, para ajustar sem mexer na lógica.
Quando um passo falha, `PortalDiagnostics` guarda imagem, endereço e HTML da tela (sem a senha) em
Logs/nfse_portal/<data>/ para que o ajuste seja feito com dados reais.

A senha vive só na memória durante a busca: nunca é gravada, registrada nem enviada a lugar nenhum além do portal.
"""
import re
import time
from datetime import datetime
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


def login(page, user, password, portal, progress=None, cancelled=None, diag=None):
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
    deadline = time.time() + portal['login_wait_seconds']
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
        if _has_captcha(page, portal) and not warned:
            warned = True
            if progress: progress('O portal pediu confirmação (captcha). Resolva-a na janela do navegador; o Exato continua sozinho em seguida.')
        page.wait_for_timeout(1000)
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


def fetch_via_portal(user, password, cnpj, date_from, date_to, log_dir, portal=None, progress=None, cancelled=None,
                     browser_options=None):
    """Entra no portal, lista as NFS-e emitidas e recebidas do período e baixa os XMLs.

    Devolve (items, info). `items` no mesmo formato do ADN, pronto para db_upsert_nfse_items.
    """
    portal = portal or PORTAL
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        raise nfse.NfseError('Para entrar no portal com usuário e senha, o Exato precisa de um componente adicional.\nFeche o Exato e abra o arquivo INSTALAR_COMPONENTE_NFSE.bat, que está na pasta do programa. Depois abra o Exato de novo.\n(O componente usa o navegador Microsoft Edge, já instalado no Windows.)')
    diag = PortalDiagnostics(log_dir)
    cnpjq = re.sub(r'\D', '', cnpj or '')
    items, info = [], {'emitidas': 0, 'recebidas': 0, 'fora_periodo': 0, 'outras_empresas': 0, 'falhas': 0}
    opts = {'channel': 'msedge', 'headless': False, 'args': ['--window-size=1200,850']}
    opts.update(browser_options or {})
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(**opts)
        except Exception as exc:
            raise nfse.NfseError(f'Não consegui abrir o navegador Microsoft Edge. Confira se ele está instalado e tente de novo.')
        try:
            ctx = browser.new_context(accept_downloads=True, locale='pt-BR', viewport={'width': 1200, 'height': 800})
            page = ctx.new_page()
            login(page, user, password, portal, progress, cancelled, diag)
            if progress: progress('Acesso liberado. Buscando as notas...')
            seen = set()
            for label, base in portal['lists'].items():
                if cancelled and cancelled():
                    break
                keys = collect_keys(page, base, date_from, date_to, portal, progress, cancelled, diag, label)
                for i, key in enumerate(keys, 1):
                    if cancelled and cancelled():
                        break
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        resp = ctx.request.get(portal['xml_url'].format(chave=key), timeout=60000)
                        if resp.status != 200:
                            raise nfse.NfseError(f'HTTP {resp.status}')
                        data = resp.body()
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
        except nfse.NfseError:
            raise
        except Exception as exc:
            where = diag.save(page, 'erro_inesperado', f'{type(exc).__name__}: {exc}') if 'page' in locals() else ''
            raise nfse.NfseError(f'O acesso ao portal não funcionou como esperado. O Exato guardou o que viu em {where}.')
        finally:
            try: browser.close()
            except Exception: pass
    info['diagnostico'] = str(diag.dir) if diag.dir.exists() else ''
    return items, info
