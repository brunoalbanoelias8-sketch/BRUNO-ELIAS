# Exato Central Fiscal — regras do projeto

- Código em `exato/Exato_Central_Fiscal_Vxxx/` (Python + Tkinter, Windows). Cada versão é uma pasta; a anterior fica intacta.
- **Regra de versão (pedido do usuário):** todo pacote novo entregue recebe um número novo (V148, V149...). Nunca reenviar um ZIP diferente com o mesmo número. Ao criar a versão: copiar a pasta, trocar `APP_VERSION`, `.bat`, `VERSAO.txt`, `README.txt`, e criar `docs/Vxxx_NOTAS.txt`, `docs/CONTINUIDADE_PROJETO_Vxxx.txt`, `documentacao/Vxxx_CHECKLIST.txt` e `documentacao/Vxxx_PROTECAO_NUCLEOS_SHA256.txt`.
- **Não alterar os 13 núcleos fiscais protegidos** (lista em `documentacao/*_PROTECAO_NUCLEOS_SHA256.txt`) nem os `assets/` sem autorização expressa; conferir por AST/SHA-256 a cada versão.
- Não criar banco novo por versão; dados persistentes ficam em `%LOCALAPPDATA%\Exato\Central Fiscal\Dados`.
- Testes de interface: Python 3.12 + `python3-tk` + `pillow` + `reportlab` com `xvfb-run`; `EXATO_DATA_DIR` aponta para uma pasta temporária. O programa exige Python 3.12+.
- O usuário usa notebook (≈1366×768): toda tela nova deve funcionar em 1366×650 e em janelas estreitas (usar `make_flow` para linhas de botões; ver `docs/CONTINUIDADE_PROJETO_*`).
- Responder em português.
