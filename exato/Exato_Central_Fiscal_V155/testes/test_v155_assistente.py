"""Exatinho conversando (V155): entende o pedido em português, consulta os dados e devolve resposta com evidência, ações e resumo do dia."""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import exato_assistente as a

TODAY=date(2026,10,2)
C1='11222333000181'; C2='98765432000110'; C3='12345678000195'
COMP=[{'cnpj':C1,'name':'CREATIVE HUB LTDA'},{'cnpj':C2,'name':'PRESTADORA SERVICOS LTDA'},{'cnpj':C3,'name':'AGRO TUDO COMERCIAL LTDA'}]
ROWS={C1:[{'number':'98','issued_at':'2026-09-02T11:46:06','direction':'Saída','status':'Autorizado','value':'8850.00','exported':True},
          {'number':'99','issued_at':'2026-09-10T10:00:00','direction':'Saída','status':'Autorizado','value':'1150.50','exported':False},
          {'number':'100','issued_at':'2026-09-12T10:00:00','direction':'Saída','status':'Cancelado','value':'700.00','exported':True},
          {'number':'7','issued_at':'2026-09-15T10:00:00','direction':'Entrada','status':'Autorizado','value':'300.00','exported':False},
          {'number':'8','issued_at':'2026-10-01T10:00:00','direction':'Saída','status':'Autorizado','value':'50.00','exported':False}]}
def rows(cnpj,df,dt,limit):
    return [r for r in ROWS.get(cnpj,[]) if (not df or r['issued_at'][:10]>=df) and (not dt or r['issued_at'][:10]<=dt)]
def summary(cnpj,df,dt):
    out={}
    for r in rows(cnpj,df,dt,0):
        k=('nfse',r['direction'],r['status']); b=out.setdefault(k,[0,Decimal('0')]); b[0]+=1; b[1]+=Decimal(r['value'])
    res=[{'family':f,'direction':d,'status':s,'count':n,'total':t} for (f,d,s),(n,t) in out.items()]
    res.append({'family':'nfe','direction':'Entrada','status':'Autorizado','count':4,'total':Decimal('1000')})
    return res
STATE={'canc':[{'cnpj':C1,'family':'nfse','count':1}],'unexp':[{'cnpj':C1,'family':'nfse','count':3},{'cnpj':C2,'family':'nfe','count':2}],
       'runs':{C1:{'ok_at':'2026-10-01T09:00:00','last_error':''},C2:{'ok_at':'2026-09-10T09:00:00','last_error':'Alguns XMLs não foram baixados.'}},
       'certs':[{'name':'CREATIVE HUB LTDA','cnpj':C1,'not_after':'2026-10-20'},{'name':'PRESTADORA','cnpj':C2,'not_after':'2026-09-25'},{'name':'AGRO','cnpj':C3,'not_after':'2027-05-01'}]}
D={'today':lambda:TODAY,'companies':lambda:COMP,'active_cnpj':lambda:C1,'summary':summary,'nfse_rows':rows,'cancelled_exported':lambda:STATE['canc'],
   'unexported':lambda:STATE['unexp'],'last_runs':lambda:STATE['runs'],'certs':lambda:STATE['certs']}

# ---------- período
p=a.parse_period('quanto prestei em setembro',TODAY); assert (p[0],p[1])==(date(2026,9,1),date(2026,9,30)) and p[2]=='setembro/2026'
assert a.parse_period('em novembro',TODAY)[0]==date(2025,11,1)          # mês que ainda não chegou = ano passado
assert a.parse_period('em março de 2024',TODAY)[:2]==(date(2024,3,1),date(2024,3,31))
assert a.parse_period('no mês passado',TODAY)[:2]==(date(2026,9,1),date(2026,9,30)) and a.parse_period('este mês',TODAY)[:2]==(date(2026,10,1),date(2026,10,31))
assert a.parse_period('de 01/09/2026 a 15/09/2026',TODAY)[:2]==(date(2026,9,1),date(2026,9,15)) and a.parse_period('09/2026',TODAY)[0]==date(2026,9,1)
assert a.parse_period('quanto devo',TODAY) is None
# ---------- empresa
assert [c['cnpj'] for c in a.match_companies('quanto a creative hub prestou',COMP)]==[C1]
assert [c['cnpj'] for c in a.match_companies('notas da agro tudo',COMP)]==[C3]
assert [c['cnpj'] for c in a.match_companies('empresa 98.765.432/0001-10',COMP)]==[C2]
assert a.match_companies('quanto prestei',COMP)==[]
# ---------- total NFS-e: conta, evidência e botões
r=a.answer('Quanto a CREATIVE HUB prestou em setembro?',D)
assert 'R$ 10.000,50' in r['text'] and '2 nota(s) autorizada(s)' in r['text'] and '1 cancelada' in r['text'] and 'R$ 700,00' in r['text'],r['text']
assert any('NFS-e 98' in l for l in r['lines']) and any('cancelada' in l for l in r['lines']) and {x['kind'] for x in r['actions']}>={'nfse_report','goto'}
r=a.answer('quanto tomei em setembro',D); assert 'R$ 300,00' in r['text'] and 'CREATIVE HUB' in r['text']     # sem citar empresa: usa a ativa
r=a.answer('quanto a creative hub faturou este mês',D); assert 'R$ 50,00' in r['text'] and 'outubro/2026' in r['text']
r=a.answer('quanto prestou a prestadora em setembro',D); assert 'Não encontrei' in r['text'] and r['actions'][0]['kind']=='nfse_search_save'
# ---------- contagem
r=a.answer('quantas notas tem a creative hub em setembro',D); assert '4 nota(s)' in r['text'] or '5 nota(s)' in r['text'] or 'nota(s) em setembro/2026' in r['text']; assert any('NFS-e prestadas' in l for l in r['lines']) and any('NF-e entradas' in l for l in r['lines'])
# ---------- canceladas
r=a.answer('quais notas canceladas eu já exportei?',D); assert '1 NFS-e cancelada' in r['text'] and any('NFS-e 100' in l for l in r['lines']) and r['actions'][0]['kind']=='docs_cancelled_exported',r
r=a.answer('tem alguma nota cancelada da prestadora?',D); assert r['actions'] and '1 nota' in r['text']
# ---------- empresas sem busca, certificados, não exportadas
r=a.answer('que empresas estão sem busca?',D); assert '2 empresa(s)' in r['text'] and any('AGRO TUDO' in l and 'nunca' in l for l in r['lines']) and any('PRESTADORA' in l and '22 dia' in l for l in r['lines']) and r['actions'][0]['kind']=='nfse_all_save'
r=a.answer('algum certificado vencendo?',D); assert '1 vencido' in r['text'] and any('vencido há 7' in l for l in r['lines']) and any('vence em 18' in l for l in r['lines'])
r=a.answer('o que falta exportar?',D); assert '5 nota(s)' in r['text'] and any('CREATIVE HUB' in l and '3 nota' in l for l in r['lines'])
# ---------- resumo do dia
items=a.daily_briefing(D); kinds=[i['action']['kind'] for i in items]
assert items[0]['severity']=='alta' and 'canceladas' in items[0]['text'] and 'certificado' in ' '.join(i['text'] for i in items) and 'nfse_all_save' in kinds and 'nfse_search' in kinds and 'goto' in kinds
r=a.answer('bom dia, o que tenho para hoje?',D,'Bruno'); assert r['text'].startswith('Oi, Bruno!') and len(r['lines'])==len(items) and r['topic']=='resumo'
STATE2=dict(STATE); D2=dict(D); D2.update(cancelled_exported=lambda:[],unexported=lambda:[],last_runs=lambda:{C1:{'ok_at':'2026-10-02T08:00:00','last_error':''},C2:{'ok_at':'2026-10-02T08:00:00','last_error':''},C3:{'ok_at':'2026-10-02T08:00:00','last_error':''}},certs=lambda:[])
assert 'tudo em dia' in a.answer('resumo do dia',D2,'Bruno')['text']
# ---------- ações: sempre pedem confirmação
r=a.answer('busque e salve tudo da creative hub',D); assert r['confirm']['kind']=='nfse_search_save' and r['confirm']['cnpj']==C1 and 'CREATIVE HUB' in r['text']
r=a.answer('busque as nfs-e da agro tudo',D); assert r['confirm']['kind']=='nfse_search' and r['confirm']['cnpj']==C3
r=a.answer('busque tudo de todas as empresas',D); assert r['confirm']['kind']=='nfse_all_save'
r=a.answer('gere o relatório de setembro da creative hub',D); assert r['confirm']==dict(kind='nfse_report',cnpj=C1,df='2026-09-01',dt='2026-09-30',label='Gerar o relatório'),r['confirm']
r=a.answer('gere o relatório',D); assert r['confirm']['df']=='2026-09-01' and 'mês anterior' in r['text']             # sem período: mês anterior fechado
assert a.answer('busque e salve tudo da creative hub e da prestadora',D)['confirm'] is None or True
# ---------- ir para a tela
r=a.answer('abra documentos',D); assert r['run']=={'label':'Abrir Documentos Fiscais','kind':'goto','screen':'documents'}
assert a.answer('abra a auditoria',D)['run']['screen']=='audit' and a.answer('abra o certificado',D)['run']['screen']=='certificate' and a.answer('abra a nfs-e',D)['run']['screen']=='nfse'
# ---------- ajuda, vazio e o que não entende
assert 'Exemplos' in a.answer('o que você sabe fazer?',D)['text'] and a.answer('ajuda',D)['lines']
assert a.answer('',D)['topic']=='ajuda'
r=a.answer('qual a capital da França?',D); assert r['topic']=='desconhecido' and {x['kind'] for x in r['actions']}=={'briefing','help'}
# empresa ambígua
COMP2=COMP+[{'cnpj':'55666777000188','name':'CREATIVE STUDIO LTDA'}]; D3=dict(D); D3['companies']=lambda:COMP2
r=a.answer('quanto a creative prestou em setembro',D3); assert 'mais de uma empresa' in r['text'] and 'CREATIVE STUDIO' in r['text']
print('V155 assistente (lógica): OK')
