
EXATO CENTRAL FISCAL
Versão: V149

QUAL PACOTE USAR
- Use somente a V149. Cada pacote novo recebe um número novo; o número aparece no topo da tela, ao lado do nome da tela.

NOVIDADE DA V149: ABA NFS-e (EMISSOR NACIONAL)
- Nova aba "NFS-e" no menu (atalho Ctrl+0), no grupo Documentos.
- Duas formas de acesso, escolhidas na própria aba:
  1) CERTIFICADO DIGITAL: usa o certificado instalado no Windows (o mesmo da NF-e) para consultar o ADN (Ambiente de Dados Nacional). Automático, sem captcha. Cada busca continua de onde a anterior parou.
  2) USUÁRIO E SENHA: abre o Microsoft Edge, entra no portal do Emissor Nacional e baixa os XMLs do período. A senha NÃO é salva. Se o portal pedir captcha, resolva na janela. Este modo está em CALIBRAÇÃO: se algum passo falhar, o Exato guarda o que viu em Dados\Logs\nfse_portal e mostra o caminho. Exige o componente Playwright (py -m pip install playwright).
- IMPORTAR XMLs / ZIP: lê os XMLs ou ZIPs baixados do portal e guarda no Arquivo Fiscal Local (só entram notas da empresa escolhida).
- As NFS-e ficam no Arquivo Fiscal Local como tipo "NFS-e": aparecem em Documentos Fiscais (filtro "NFS-e"), entram no backup e na Central Compartilhada, e "Salvar XMLs" grava em Empresa > Ano > Mês > Entrada/Saída > NFS-e.
- Cancelamentos (eventos) marcam a nota como Cancelada.
- O PDF (DANFSe) ainda não é gerado pelo Exato; use "Abrir XML" ou o portal.
- Relatórios, auditoria e exportações de NF-e/NFC-e/CT-e NÃO recebem NFS-e (separação de segurança).

IMPORTANTE (VALIDAÇÃO)
- A comunicação com o ADN foi construída a partir de documentação pública e testada com respostas simuladas; os sites do governo não são acessíveis no ambiente de desenvolvimento. Na primeira busca real, se algo vier diferente do esperado, envie o arquivo exato.log (Manutenção > Abrir registro de erros).

BASE
- Evolui a V148. Dados, Central Compartilhada, Arquivo Fiscal Local e os 13 núcleos fiscais protegidos permanecem idênticos aos da V145.

DOCUMENTAÇÃO
- docs/V149_NOTAS.txt
- docs/CONTINUIDADE_PROJETO_V149.txt
- documentacao/V149_CHECKLIST.txt
- documentacao/V149_PROTECAO_NUCLEOS_SHA256.txt
