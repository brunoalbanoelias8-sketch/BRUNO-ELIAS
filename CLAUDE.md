# Exato Central Fiscal — regras do projeto

- Código em `exato/Exato_Central_Fiscal_Vxxx/` (Python + Tkinter, Windows). Cada versão é uma pasta; a anterior fica intacta.
- **Regra de versão (pedido do usuário):** todo pacote novo entregue recebe um número novo (V148, V149...). Nunca reenviar um ZIP diferente com o mesmo número. Ao criar a versão: copiar a pasta, trocar `APP_VERSION`, `.bat`, `VERSAO.txt`, `README.txt`, e criar `docs/Vxxx_NOTAS.txt`, `docs/CONTINUIDADE_PROJETO_Vxxx.txt`, `documentacao/Vxxx_CHECKLIST.txt` e `documentacao/Vxxx_PROTECAO_NUCLEOS_SHA256.txt`.
- **Não alterar os 13 núcleos fiscais protegidos** (lista em `documentacao/*_PROTECAO_NUCLEOS_SHA256.txt`) nem os `assets/` sem autorização expressa; conferir por AST/SHA-256 a cada versão.
- Não criar banco novo por versão; dados persistentes ficam em `%LOCALAPPDATA%\Exato\Central Fiscal\Dados`.
- Suíte de testes: `testes/SUITE_ATUAL.txt` + `testes/run_suite.py` (GitHub Actions roda a cada envio, `.github/workflows/tests.yml`). `test_versao_consistente.py` confere a regra de versão. Ao criar uma versão nova, renomear os `test_vNNN_*` e atualizar a lista.
- Testes de interface: Python 3.12 + `python3-tk` + `pillow` + `reportlab` com `xvfb-run`; `EXATO_DATA_DIR` aponta para uma pasta temporária. O programa exige Python 3.12+.
- NFS-e (V149+): `exato_nfse.py` (núcleo) e `exato_nfse_portal.py` (portal por usuário/senha, em calibração; endereços em `PORTAL`). Gov.br/ADN/portal são bloqueados no ambiente de desenvolvimento: tudo foi testado só com simulação; ajustar com o retorno real do usuário (exato.log e Logs/nfse_portal).
- NFS-e segue a lógica da NF-e (V151): XML + PDF por nota (`exato_nfse_pdf.py`) + consolidado por pasta, registro de exportação em `document_exports`, alerta de cancelada já exportada; planilhas por `exato_xlsx.py`. Em NFS-e usar Prestados/Tomados na tela e nas pastas (internamente Saída/Entrada). Ferramentas só para o suporte ficam no Modo técnico (Manutenção).
- O usuário não quer linguagem de programação visível (nomes de erro, siglas técnicas): mensagens sempre em português claro (`friendly_message`, `log_exception`).
- O usuário usa notebook (≈1366×768): toda tela nova deve funcionar em 1366×650 e em janelas estreitas (usar `make_flow` para linhas de botões; ver `docs/CONTINUIDADE_PROJETO_*`).
- **Diretriz do usuário: automatizar ao máximo.** A Central Exato deve exigir o mínimo de cliques e de trabalho manual (lembrar escolhas, preencher sozinho, ações encadeadas, tentar de novo sozinho, avisar só quando houver decisão). Pense nisso em toda tela nova.
- Responder em português.
