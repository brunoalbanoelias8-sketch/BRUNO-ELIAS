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

3. **NFS-e por usuário e senha: opção de salvar a senha vinculada à empresa.** Muda a decisão antiga ("não guardar senha"), agora por pedido do usuário. Proposta: opcional (caixa "Lembrar a senha desta empresa"), nunca no log nem em texto puro; guardar criptografada com a proteção do Windows (DPAPI, só abre no mesmo usuário do Windows, via PowerShell/ctypes), vinculada ao CNPJ da empresa, em tabela/arquivo dentro de `Dados` (sem banco novo); botões "Esquecer senha salva" e indicação "senha salva" na empresa; preencher o campo automaticamente ao escolher a empresa; base para a busca em lote por usuário/senha. Não vai no backup/exportação em claro. Confirmar com o usuário: salvar só CPF/CNPJ de acesso + senha.

4. **Portal por usuário e senha — primeiro teste real (CREATIVE HUB LTDA, 01/09 a 30/09/2026, Tomados): login e listagem funcionaram (17 chaves encontradas), mas os 17 XMLs não baixaram** ("Alguns XMLs não foram baixados"; `info['falhas']=17`). O download usa `PORTAL['xml_url']` (`.../Notas/Download/NFSe/{chave}`) via `ctx.request.get`; falha por status != 200 ou conteúdo que `parse_nfse` não aceita (ex.: redirecionamento ao login/HTML). A primeira falha grava página+motivo em `Dados\Logs\nfse_portal\download_*`. Pedir esses arquivos ao usuário (ou o texto do motivo) para calibrar. Possíveis correções: clicar no link de download na própria página (`expect_download`) em vez de requisição direta, enviar `Referer`, ou achar a URL real do link na página da lista. Melhorar também a mensagem: dizer quantos baixaram/falharam e orientar a enviar a pasta de diagnóstico. Obs.: a tela mostrava a data em inglês ("Friday, 02 de october") no cabeçalho — traduzir para português.

## Ideias ainda não feitas
- NFS-e no relatório e na auditoria (hoje separadas de propósito, por segurança).
- Busca em lote por usuário e senha (clientes sem certificado).
- Fluidez na troca de abas (Empresas ~220 ms); tema escuro (cores espalhadas no código); dividir o arquivo grande em módulos.
- Acesso automático ao SAT (código existe, nenhuma tela chama).

## Como retomar
1. Ler `CLAUDE.md` e a continuidade da V151.
2. Toda entrega recebe número novo (V152, V153...). Copiar a pasta, trocar `APP_VERSION`, `.bat`, `VERSAO.txt`, `README.txt` e criar NOTAS, CONTINUIDADE, CHECKLIST e PROTECAO. O teste `test_versao_consistente.py` confere.
3. Rodar `xvfb-run -a python testes/run_suite.py` na pasta da versão e conferir o GitHub Actions antes de entregar o ZIP.
