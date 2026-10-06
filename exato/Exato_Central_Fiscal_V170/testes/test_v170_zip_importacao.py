"""V168: ZIP para importação na Domínio — um por empresa/mês/tipo/direção, na própria pasta, sem mexer nos XMLs soltos."""
import os, sys, tempfile, shutil, zipfile, sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ['EXATO_DATA_DIR']=tempfile.mkdtemp(prefix='exato_v170_zip_'); sys.path.insert(0,str(ROOT/'programa')); sys.path.insert(0,str(ROOT/'programa'/'third_party')); sys.path.insert(0,str(Path(__file__).parent))
import exato_zip_importacao as Z
import exato_central_fiscal as m
from test_v170_nfse_core import nfse_xml, chave, PREST
tmp=Path(tempfile.mkdtemp(prefix='exato_v170_clientes_'))
# ---------- módulo isolado
pasta=tmp/'EMPRESA TESTE'/'2026'/'09 - Setembro'/'Saída'/'NF-e'; pasta.mkdir(parents=True)
for i in range(3): (pasta/('%044d.xml'%i)).write_bytes(b'<nfe n="%d"/>'%i)
(pasta/('%044d.pdf'%0)).write_bytes(b'%PDF'); (pasta/'Relatorio_consolidado.pdf').write_bytes(b'%PDF')
salvos=[str(pasta/('%044d.xml'%i)) for i in range(3)]
r=Z.montar_zips(salvos,'12.345.678/0001-95'); assert r['criados']==1 and not r['erros'],r
zp=pasta/'12345678000195_2026-09_NF-e_Saída.zip'; assert zp.exists() and r['zips']==[str(zp)]
with zipfile.ZipFile(zp) as z: nomes=sorted(z.namelist()); assert nomes==[('%044d.xml'%i) for i in range(3)] and all('/' not in n for n in nomes)      # XMLs soltos, sem PDF, sem subpastas
assert all((pasta/('%044d.xml'%i)).exists() for i in range(3))                    # XMLs soltos continuam
# repetir não refaz; nota nova refaz; ZIP danificado refaz; nunca fica arquivo temporário
mt=zp.stat().st_mtime_ns; r=Z.montar_zips(salvos,'12345678000195'); assert r['iguais']==1 and r['criados']==0 and zp.stat().st_mtime_ns==mt
(pasta/('%044d.xml'%9)).write_bytes(b'<nfe n="9"/>'); r=Z.montar_zips([str(pasta/('%044d.xml'%9))],'12345678000195'); assert r['atualizados']==1
with zipfile.ZipFile(zp) as z: assert len(z.namelist())==4                     # tem TODOS os XMLs da pasta, não só o novo
zp.write_bytes(b'lixo'); r=Z.montar_zips(salvos,'12345678000195'); assert r['atualizados']==1 and zipfile.is_zipfile(zp)
assert not list(pasta.glob('.*.tmp')) and not list(pasta.glob('*.tmp'))
# eventos de cancelamento entram no ZIP
ev=lambda cnpj,chaves: [('evento_1.xml',b'<evento/>')]
r=Z.montar_zips(salvos,'12345678000195',eventos_fn=ev)
with zipfile.ZipFile(zp) as z: assert 'evento_1.xml' in z.namelist() and len(z.namelist())==5
# pasta fora do padrão é ignorada; entrada/saída, prestados/tomados e tipos ficam cada um no seu ZIP
outra=tmp/'solto'; outra.mkdir(); (outra/'a.xml').write_bytes(b'<a/>'); assert Z.montar_zips([str(outra/'a.xml')],'1')['criados']==0
for direc,tipo in (('Entrada','NF-e'),('Saída','NFC-e'),('Prestados','NFS-e'),('Tomados','NFS-e')):
    f=tmp/'EMPRESA TESTE'/'2026'/'10 - Outubro'/direc/tipo; f.mkdir(parents=True); (f/('%050d.xml'%1)).write_bytes(b'<x/>')
    Z.montar_zips([str(f/('%050d.xml'%1))],PREST); assert (f/f'{PREST}_2026-10_{tipo}_{direc}.zip').exists(),(direc,tipo)
# ---------- integração: salvar de verdade (NF-e + NFS-e) deixa os ZIPs; desligado não deixa
m.init_database(); m.db_register_company(PREST,'PRESTADORA SERVICOS LTDA')
nfse=[{'xml':nfse_xml(i,prest=PREST,toma='98765432000110',valor='100.00',dh='2026-09-%02dT10:00:00-03:00'%(5+i)),'family':'nfse','chave':chave(i),'cnpj':PREST} for i in range(1,4)]
dest=tmp/'clientes'; saved,errors=m.save_documents_any(nfse,str(dest),PREST,{'zip_importacao':True},None); assert not errors
zips=sorted(dest.rglob('*.zip')); assert len(zips)==1 and zips[0].name==f'{PREST}_2026-09_NFS-e_Prestados.zip' and zips[0].parent.name=='NFS-e' and zips[0].parent.parent.name=='Prestados',zips
with zipfile.ZipFile(zips[0]) as z: assert len(z.namelist())==3
dest2=tmp/'clientes2'; m.save_documents_any(nfse,str(dest2),PREST,{'zip_importacao':False},None); assert not list(dest2.rglob('*.zip')) and list(dest2.rglob('*.xml'))
assert m.zip_importacao_ativo({}) is True and m.zip_importacao_ativo({'zip_importacao':False}) is False       # ligado por padrão
# cancelada: o evento entra no ZIP
c=sqlite3.connect(m.DB_PATH)
c.execute("INSERT INTO documents(doc_id,cnpj,family,doc_type,direction,status,access_key,xml,first_seen_at,last_seen_at) VALUES('n1',?,?,?,?,?,?,?,?,?)",(PREST,'nfse','NFS-e','Saída','Cancelado',chave(1),nfse[0]['xml'],'x','x'))
c.execute("INSERT INTO documents(doc_id,cnpj,family,doc_type,direction,status,access_key,xml,first_seen_at,last_seen_at) VALUES('ev1',?,?,?,?,?,?,?,?,?)",(PREST,'nfse','Evento','','Evento',chave(1),b'<evento tipo="cancelamento"/>','x','x')); c.commit(); c.close()
m.save_documents_any(nfse,str(dest),PREST,{'zip_importacao':True},None)
with zipfile.ZipFile(zips[0]) as z: assert any(n.startswith('evento_') for n in z.namelist()) and len(z.namelist())==4
shutil.rmtree(tmp,ignore_errors=True); shutil.rmtree(os.environ['EXATO_DATA_DIR'],ignore_errors=True)
print('V169 zip importação: OK')
