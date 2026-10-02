"""Acesso por usuário e senha: roda o navegador de verdade contra um portal SIMULADO (não é o portal real)."""
import glob, os, sys, tempfile, threading, shutil
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(Path(__file__).parent))
import exato_nfse as n, exato_nfse_portal as portal
from test_v150_nfse_core import nfse_xml, chave, PREST, TOMA
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw: exe=pw.chromium.executable_path
    if not exe or not Path(exe).exists():
        found=sorted(glob.glob(os.path.join(os.environ.get('PLAYWRIGHT_BROWSERS_PATH','/opt/pw-browsers'),'chromium-*','chrome-linux*','chrome')))
        if not found: raise FileNotFoundError(exe)
        exe=found[-1]
except Exception as exc:
    print(f'V150 NFS-e portal: PULADO (sem Playwright/Chromium neste computador: {exc})'); sys.exit(0)

NOTAS={1:nfse_xml(1,dh='2026-09-10T10:00:00-03:00'),2:nfse_xml(2,dh='2026-09-20T10:00:00-03:00'),3:nfse_xml(3,dh='2026-01-05T10:00:00-03:00'),
       4:nfse_xml(4,prest='11111111000191',toma='22222222000191',dh='2026-09-12T10:00:00-03:00'),
       5:nfse_xml(5,prest='33333333000191',toma=PREST,dh='2026-09-15T10:00:00-03:00')}
EMITIDAS=[[1,2],[3,4]]; RECEBIDAS=[[5]]
def link(i): return f'<a href="/EmissorNacional/Notas/Download/NFSe/{chave(i)}">XML</a>'
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _send(self,code,body,ctype='text/html; charset=utf-8',headers=()):
        self.send_response(code); self.send_header('Content-Type',ctype)
        for k,v in headers: self.send_header(k,v)
        self.end_headers(); self.wfile.write(body if isinstance(body,bytes) else body.encode())
    def authed(self): return 'sid=ok' in (self.headers.get('Cookie') or '')
    def do_GET(self):
        u=urlparse(self.path); q=parse_qs(u.query)
        if u.path=='/EmissorNacional/Login': return self._send(200,'<form method="post" action="/EmissorNacional/Login"><input type="text" name="Inscricao"><input type="password" name="Senha"><button type="submit">Entrar</button></form>')
        if not self.authed(): return self._send(302,'',headers=[('Location','/EmissorNacional/Login')])
        if u.path=='/EmissorNacional/': return self._send(200,'<h1>Painel</h1>')
        if u.path.startswith('/EmissorNacional/Notas/Download/NFSe/'):
            k=u.path.rsplit('/',1)[1]; i=next((i for i in NOTAS if chave(i)==k),None)
            return self._send(200 if i else 404,NOTAS.get(i,b''),'application/xml')
        for name,pages in (('Emitidas',EMITIDAS),('Recebidas',RECEBIDAS)):
            if u.path==f'/EmissorNacional/Notas/{name}':
                pg=int(q.get('pg',['1'])[0]); rows=''.join(f'<tr><td>{i}</td><td>{link(i)}</td></tr>' for i in pages[pg-1]) if pg<=len(pages) else ''
                nxt=f'<a rel="next" href="/EmissorNacional/Notas/{name}?pg={pg+1}">Próxima</a>' if pg<len(pages) else ''
                return self._send(200,f'<table>{rows}</table>{nxt}')
        self._send(404,'nao')
    def do_POST(self):
        body=self.rfile.read(int(self.headers.get('Content-Length',0))).decode(); f=parse_qs(body)
        if f.get('Inscricao',[''])[0]==PREST and f.get('Senha',[''])[0]=='segredo': return self._send(302,'',headers=[('Location','/EmissorNacional/'),('Set-Cookie','sid=ok; Path=/')])
        self._send(200,'<form><input type="text" name="Inscricao"><input type="password" name="Senha"></form><p>Usuário ou senha inválidos</p>')
srv=ThreadingHTTPServer(('127.0.0.1',0),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{srv.server_port}'
P=dict(portal.PORTAL); P.update(login_url=base+'/EmissorNacional/Login', lists={'Emitidas':base+'/EmissorNacional/Notas/Emitidas','Recebidas':base+'/EmissorNacional/Notas/Recebidas'},
       xml_url=base+'/EmissorNacional/Notas/Download/NFSe/{chave}', login_wait_seconds=4)
opts={'executable_path':exe,'headless':True,'args':['--no-sandbox'],'channel':None}
logs=Path(tempfile.mkdtemp(prefix='exato_portal_logs_')); msgs=[]
try:
    items,info=portal.fetch_via_portal('12.345.678/0001-95','segredo',PREST,date(2026,9,1),date(2026,9,30),logs,portal=P,progress=msgs.append,browser_options=opts)
    keys=sorted(i['chave'] for i in items)
    assert keys==sorted([chave(1),chave(2),chave(5)]),keys                      # 3 vem de janeiro (fora do período) e 4 é de outra empresa
    assert info['emitidas']==2 and info['recebidas']==1 and info['fora_periodo']==1 and info['outras_empresas']==1 and info['falhas']==0,info
    assert any('página 2' in m for m in msgs), 'percorreu a segunda página'
    assert all(i['tipo_documento']=='NFSE' and i['xml'].startswith(b'<?xml') for i in items)
    # senha errada: erro amigável, sem a senha em lugar nenhum
    try: portal.fetch_via_portal(PREST,'errada',PREST,None,None,logs,portal=P,browser_options=opts); raise SystemExit('deveria falhar')
    except n.NfseError as e:
        assert 'não liberou o acesso' in str(e) and 'errada' not in str(e)
    txt=''.join(p.read_text(errors='ignore') for p in logs.rglob('*') if p.is_file() and p.suffix in ('.html','.txt'))
    assert 'errada' not in txt and 'segredo' not in txt, 'a senha não pode aparecer no diagnóstico'
    # tela de login diferente do esperado: diagnóstico guardado
    P2=dict(P); P2.update(user_selectors=['#nao_existe'],pass_selectors=['#nao_existe'])
    try: portal.fetch_via_portal(PREST,'segredo',PREST,None,None,logs,portal=P2,browser_options=opts); raise SystemExit('deveria falhar')
    except n.NfseError as e: assert 'campos de usuário e senha' in str(e) and 'nfse_portal' in str(e)
    assert list(logs.rglob('login_campos.png')) and list(logs.rglob('login_campos.html'))
    # cancelamento
    try: portal.fetch_via_portal(PREST,'segredo',PREST,None,None,logs,portal=P,cancelled=lambda:True,browser_options=opts)
    except n.NfseError: pass
finally:
    srv.shutdown(); shutil.rmtree(logs,ignore_errors=True)
print('V150 NFS-e portal (simulado): OK')
