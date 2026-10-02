# Exato Central Fiscal — próximos passos (atualizado na V151)

Versão atual entregue: **V151** (`exato/Exato_Central_Fiscal_V151/`). Regras do projeto: `CLAUDE.md`. Estado detalhado: `exato/Exato_Central_Fiscal_V151/docs/CONTINUIDADE_PROJETO_V151.txt`.

## Feito (resumo)
- Tema moderno e layout responsivo para notebook; Exatinho flutuante; painel "Hoje"; contador de pendências; atalhos Ctrl+1..9 e Ctrl+0 (NFS-e).
- Registro de erros, modo técnico, mensagens sem linguagem de programação, datas/CNPJ com separador automático.
- NFS-e (Emissor Nacional): busca por certificado (funcionou no uso real: 301 documentos), por usuário/senha (em calibração), importação de XML/ZIP, filtros Prestados/Tomados/exportação, PDF de cada nota, exportação com PDF e consolidado, alerta de cancelada já exportada, buscar todas as empresas, resumo mensal e Excel, cartões no Início, cadastro individual de empresa.
- Testes automáticos no GitHub a cada envio (15 testes na V151).

## Pendente — depende do Bruno
1. **Enviar um XML real de NFS-e** (uma prestada e uma tomada) para calibrar nomes, valores e o PDF. Dúvida: valores baixos (R$ 0,23 etc.) podem ser leitura do campo errado.
2. **Primeiro acesso real por usuário e senha** (modo em calibração): se falhar, enviar a pasta `Dados\Logs\nfse_portal`.
3. **Autorizar mexer nos núcleos fiscais protegidos** para corrigir a coluna "Última busca" que mostra "Aguardando" mesmo quando deu certo (deferred_actor), e a auditoria com nota cancelada.
4. Decidir: em Documentos Fiscais, mostrar **Prestado/Tomado** na coluna Movimentação das NFS-e (hoje Entrada/Saída)?
5. Conferir no Windows fontes/escala da tela (o ambiente de desenvolvimento é Linux).

## Feedbacks do usuário para a V152 (registrados, ainda não feitos)
1. **NFS-e, lista de notas esmagada** (notebook ≈1366×768): com a busca concluída, os cartões (Notas no período / Prestados / Tomados / Canceladas) e a faixa de resultado ocupam quase toda a altura e a tabela fica com ~1 linha visível. Reorganizar para a lista ter altura útil (cartões compactos, seções recolhíveis, tabela com altura mínima e rolagem da página).

2. **NFS-e, relatório mensal de verdade**: hoje o "consolidado por pasta" (`NFS-e_<tipo>_<aaaa>-<mm>_consolidado.pdf`) é só um PDF com uma página de DANFSe por nota (sem soma), a "relação" (`generate_nfse_list_pdf`) é uma lista simples do filtro, e o "Resumo mensal" só traz totais por mês. Proposta: relatório mensal em lote = um PDF por mês e por tipo (Prestados/Tomados) com todas as notas do mês em lista + totais (quantidade, valor, canceladas separadas), gerado também ao salvar os XMLs (na pasta do mês) e por botão para o período escolhido (um arquivo por mês ou um só com seção por mês). **Formato confirmado pelo usuário** (um PDF por mês e tipo, lista de todas as notas + totais; automático ao salvar XMLs; botão para o período).

## Ideias ainda não feitas
- NFS-e no relatório e na auditoria (hoje separadas de propósito, por segurança).
- Busca em lote por usuário e senha (clientes sem certificado).
- Fluidez na troca de abas (Empresas ~220 ms); tema escuro (cores espalhadas no código); dividir o arquivo grande em módulos.
- Acesso automático ao SAT (código existe, nenhuma tela chama).

## Como retomar
1. Ler `CLAUDE.md` e a continuidade da V151.
2. Toda entrega recebe número novo (V152, V153...). Copiar a pasta, trocar `APP_VERSION`, `.bat`, `VERSAO.txt`, `README.txt` e criar NOTAS, CONTINUIDADE, CHECKLIST e PROTECAO. O teste `test_versao_consistente.py` confere.
3. Rodar `xvfb-run -a python testes/run_suite.py` na pasta da versão e conferir o GitHub Actions antes de entregar o ZIP.
