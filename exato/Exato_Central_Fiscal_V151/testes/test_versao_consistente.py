"""Garante a regra de versão: o número do programa aparece em todos os lugares e a documentação da versão existe."""
import os, re, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ['EXATO_DATA_DIR']=tempfile.mkdtemp(prefix='exato_versao_')
sys.path.insert(0,str(ROOT))
import exato_central_fiscal as m
v=m.APP_VERSION
assert re.fullmatch(r'V\d+',v),v
assert ROOT.name==f'Exato_Central_Fiscal_{v}',f'pasta {ROOT.name} != {v}'
for name in ('VERSAO.txt','README.txt','EXECUTAR.bat','INICIAR.bat'):
    assert v in (ROOT/name).read_text(encoding='utf-8',errors='replace'),f'{name} não cita {v}'
for rel in (f'docs/{v}_NOTAS.txt',f'docs/CONTINUIDADE_PROJETO_{v}.txt',f'documentacao/{v}_CHECKLIST.txt',f'documentacao/{v}_PROTECAO_NUCLEOS_SHA256.txt'):
    assert (ROOT/rel).exists(),f'falta {rel}'
print(f'Versão consistente: {v}: OK')
