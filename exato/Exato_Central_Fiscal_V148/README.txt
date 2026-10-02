
EXATO CENTRAL FISCAL
Versão: V148

QUAL PACOTE USAR
- Use somente a V148. Cada pacote novo recebe um número novo; o número aparece no topo da tela, ao lado do nome da tela.
- A V148 evolui a V147 (que consolidou tudo o que foi entregue antes como V146).

NOVIDADES DA V148
- Atalhos de teclado: Ctrl+1 a Ctrl+9 trocam de tela (Início, Buscar XML, Documentos, Empresas, Auditoria, Pendências, Histórico, Relatórios, Certificado). F1 ou o botão "?" no topo mostra a lista.
- Avisos que somem sozinhos no canto da tela (busca concluída, XMLs salvos, auditoria, erros).
- Registro de erros: o programa grava um arquivo de registro em %LOCALAPPDATA%\Exato\Central Fiscal\Dados\Logs\exato.log. Se algo falhar, abra Manutenção > "Abrir registro de erros" e envie o arquivo exato.log. Em caso de erro o programa avisa e continua aberto.
- Histórico e Documentos Fiscais carregam bem mais rápido (Histórico: de ~0,7 s para ~0,05 s com 120 operações).
- Troca de abas faz menos trabalho de layout.
- Para quem mantém o projeto: testes automáticos rodam no GitHub a cada envio (testes/run_suite.py).

BASE
- Dados, Central Compartilhada, Arquivo Fiscal Local e os 13 núcleos fiscais protegidos permanecem idênticos aos da V145.

DOCUMENTAÇÃO
- docs/V148_NOTAS.txt
- docs/CONTINUIDADE_PROJETO_V148.txt
- documentacao/V148_CHECKLIST.txt
- documentacao/V148_PROTECAO_NUCLEOS_SHA256.txt
