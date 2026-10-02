import os, sys, tempfile, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ['EXATO_DATA_DIR']=tempfile.mkdtemp(prefix='exato_v146_ui_')
sys.path.insert(0,str(ROOT))
import exato_central_fiscal as m
m.init_database()
u=m.db_auth_get_user(m.AUTH_BOOTSTRAP_EMAIL)
m.db_auth_set_password(u['id'],'SenhaUI#2026')
user=m.db_auth_login(m.AUTH_BOOTSTRAP_EMAIL,'SenhaUI#2026')
certs=[{'Subject':'CN=%s'%n,'FriendlyName':n,'Thumbprint':'%040X'%i,'NotAfter':na,'Status':'Válido','Document':d,'TypeGuess':t}
       for i,(n,na,d,t) in enumerate([
           ('ALFA COMERCIO LTDA','2099-01-01','11.111.111/0001-11','Provável A3/token'),
           ('BETA SERVICOS LTDA','2099-01-01','22.222.222/0001-22','Não determinado'),
           ('GAMA INDUSTRIA LTDA',(m.datetime.now()+m.timedelta(days=10)).strftime('%Y-%m-%d'),'33.333.333/0001-33','Não determinado')],1)]
m.enumerate_windows_certificates=lambda *a,**k:(certs,'')
app=m.App(current_user=user)
try:
    assert m.APP_VERSION=='V146'
    app.update_idletasks(); app.update()
    # Tema: topo claro, barra lateral escura, vermelho Exato.
    assert m.HEADER_BG=='#FFFFFF' and m.SIDEBAR_BG=='#0B1220' and m.RED=='#E11D2E'
    # Todas as telas abrem e o título do topo acompanha a navegação.
    for fn,title in [('_show_dashboard','Início'),('_show_webservice_test','Buscar XML'),('_show_documents','Documentos Fiscais'),
                     ('_show_companies','Empresas'),('_show_audit','Auditoria Fiscal'),('_show_pending','Pendências'),
                     ('_show_history','Histórico'),('_show_reports','Relatórios'),('_show_users','Usuários'),
                     ('_show_maintenance','Manutenção'),('_show_certificate_list','Certificado')]:
        getattr(app,fn)(); app.update_idletasks(); app.update()
        assert app.header_crumb.cget('text')==title,(fn,app.header_crumb.cget('text'))
    # Botões em maiúsculas passam a usar capitalização normal; siglas e documentos fiscais são preservados.
    assert m._sentence_case_button_text('SALVAR XMLs NOVOS')=='Salvar XMLs novos'
    assert m._sentence_case_button_text('DIAGNÓSTICO NF-e')=='Diagnóstico NF-e'
    assert m._sentence_case_button_text('IMPORTAR EMPRESAS (EXCEL)')=='Importar empresas (Excel)'
    assert m._sentence_case_button_text('Auditar')=='Auditar'
    app._show_documents(); app.update()
    assert app.doc_rep_btn.cget('text')=='Ver/gerar representação'
    # Tela Certificado: busca e filtros.
    app._finish_refresh(list(certs),''); app.update()
    assert len(app.tree.get_children())==3
    app._cert_query.set('beta'); app.update()
    assert len(app.tree.get_children())==1
    app._cert_query.set('333.333'); app.update()
    assert len(app.tree.get_children())==1
    app._cert_query.set(''); app._cert_set_filter('token'); app.update()
    assert len(app.tree.get_children())==1
    app._cert_set_filter('expiring'); app.update()
    kids=app.tree.get_children(); assert len(kids)==1 and 'Vence em' in app.tree.item(kids[0],'values')[4]
    app._cert_set_filter('all'); app.update()
    assert len(app.tree.get_children())==3
    # A seleção continua habilitando o botão Continuar e preenchendo o rodapé.
    app.tree.selection_set(app.tree.get_children()[1]); app.update()
    assert str(app.continue_btn['state'])=='normal' and app.selection_label.cget('text')=='BETA SERVICOS LTDA'
finally:
    app.destroy(); shutil.rmtree(os.environ['EXATO_DATA_DIR'],ignore_errors=True)
print('V146 theme UI: OK')
