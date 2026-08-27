# FC SERV Enterprise 5.0 BETA

> Antes da primeira execução, defina `FC_SERV_OWNER_PASSWORD` com uma senha forte de pelo menos 8 caracteres. Nenhuma senha real é armazenada neste repositório.

# FC SERV 3.2.3 — versão local e servidor em Python

Sistema para Windows, construído com Python, SQL (SQLite/PostgreSQL), HTML, CSS e JavaScript. Possui identidade visual azul e preta e pode funcionar localmente ou como servidor central para várias máquinas.

## Como abrir no Windows

1. Extraia toda a pasta do arquivo ZIP.
2. Dê dois cliques em `INSTALAR_E_INICIAR.bat`.
3. Na primeira execução, aguarde a instalação dos componentes.
4. O navegador abrirá automaticamente.
5. Crie o usuário administrador.

Nas próximas vezes, use `INICIAR.bat`.

## Servidor central para várias máquinas

1. Escolha um computador da empresa para ser o servidor. Ele deve permanecer ligado.
2. Instale normalmente e feche a execução local.
3. Abra `INICIAR_SERVIDOR.bat`.
4. A janela mostrará um endereço parecido com `http://192.168.1.20:8080`.
5. Nas outras máquinas, abra esse endereço no navegador. Não é necessário instalar o aplicativo nelas.
6. O primeiro usuário criado no banco central é o único administrador proprietário. Todos os usuários criados depois são contas comuns.

Se o Firewall do Windows perguntar, permita o acesso apenas em **redes privadas**. Para acesso pela internet, use o `docker-compose.yml` com PostgreSQL atrás de um domínio e HTTPS; não encaminhe diretamente a porta 8080 do roteador.

## Funcionalidades

- Banco SQLite local e automático.
- Login de administrador e usuários.
- Um único administrador proprietário, protegido no banco e na API.
- Histórico administrativo de login, importações, alterações e exclusões, com usuário e endereço da máquina.
- Faturas a liberar e faturas concluídas.
- Liberação manual GKO e SAVE.
- Uma fatura só passa para **Faturas** depois de GKO e SAVE.
- Bloqueio de duplicidade por transportadora + número normalizado.
- Gerenciamento de `Controle de Faturas.xlsx`: adicionar/atualizar, substituir ou remover somente os registros vindos do Excel.
- Backup automático antes de substituir ou remover os dados importados do Excel.
- `STATUS FINAL SAVE = OK` entra em **Faturas**; demais registros entram em **Faturas a liberar**.
- Exportação para Excel.
- Conexão com uma conta específica ou com todas as contas do Outlook clássico do Windows.
- Outlook sem senha e sem autenticação IMAP: utiliza a sessão já aberta no Windows.
- Gmail e outros provedores continuam disponíveis via IMAP.
- Busca sem marcar os e-mails como lidos.
- Senhas IMAP de Gmail e outros provedores criptografadas no banco; o Outlook não armazena senha.
- Sem painel de log.
- Sem log técnico exposto aos usuários; somente o histórico administrativo de atividades.
- Logo azul do FC SERV aplicada também ao ícone da aba do navegador e ao atalho do Windows.

## E-mail

A tela de cadastro abre com **Outlook / Microsoft 365** selecionado. Abra antes o Outlook clássico no mesmo computador do FC SERV, confirme que a conta desejada está adicionada e informe o endereço completo dela. O sistema localiza essa caixa no perfil do Windows, não solicita senha e não usa IMAP. A opção **Todas as contas do Outlook instalado** busca em todas as caixas configuradas nesse perfil.

Para Gmail ou outro provedor IMAP, selecione o provedor correspondente e informe a senha de aplicativo. A integração local do Outlook exige o Outlook clássico; o Novo Outlook do Windows não disponibiliza a automação usada pelo FC SERV.

## Importação de planilhas

O arquivo deve ser `.xlsx` e possuir uma aba chamada exatamente `CONTROLE DE FATURAS`. No botão **Planilha Excel**, o administrador pode:

- **Adicionar ou atualizar:** inclui somente faturas novas e mantém os dados atuais.
- **Substituir:** remove somente as faturas de origem Excel e importa a nova planilha.
- **Remover dados do Excel:** apaga somente as faturas importadas do Excel.

Faturas manuais e capturadas por e-mail são preservadas nas opções de substituir e remover. O sistema cria um backup automático antes da alteração. A versão 3.1 processa a planilha em modo econômico, ignora formatação aplicada muito abaixo dos dados e limita a leitura a 100.000 linhas para impedir travamentos.

## Dados

No Windows, o banco, os backups das planilhas e a chave de criptografia ficam em:

`%LOCALAPPDATA%\Fatura Control Pro`

Não exclua a chave `secret.key`; ela é necessária para acessar as senhas de e-mail criptografadas.

## Gerar EXE

Execute `GERAR_EXE.bat`. O executável será criado na pasta `dist`.
