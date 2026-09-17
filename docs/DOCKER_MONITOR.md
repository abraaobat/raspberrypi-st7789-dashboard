# Monitor Docker local — v0.7.0

Uma página opcional para acompanhar o homelab, sem controlar contêineres. A v0.7.0 acrescenta **Docker** às nove páginas existentes, mantendo a navegação e o carrossel. Novas instalações/migrações deixam esta página desativada.

## O que aparece

- quantidade em execução, parados e explicitamente não saudáveis;
- até quatro nomes, estado e resultado de saúde;
- problemas priorizados antes dos contêineres saudáveis;
- total, contêineres adicionais e outros estados no rodapé;
- nomes escolhidos mas não encontrados;
- `CACHE · DADOS ANTIGOS` quando a última consulta falhou ou está sendo renovada.

`RODANDO` não significa `SAUDÁVEL`: sem um healthcheck reconhecido, a página informa somente execução. `FALHA` pode representar saúde `unhealthy` ou estado `dead`; `PARADO` não é uma falha automática, pois pode ser intencional. O contador **SAÚDE !** conta somente os contêineres em execução cujo healthcheck informou `unhealthy`, não todos os problemas. Contêineres pausados/reiniciando/removidos ou de estado desconhecido entram em **OUTROS**, não em **PARADOS**.

Uma lista válida vazia gera zero. Socket ausente, falta de permissão ou resposta inválida geram **SEM DADOS**, nunca um zero inventado. Quando há filtros, os números correspondem somente aos nomes encontrados, não ao host inteiro.

## Configurar pelo painel

1. Em **Contêineres Docker**, deixe os nomes vazios para acompanhar o host inteiro ou informe até quatro nomes exatos, separados por vírgula. Exemplos fictícios: `pihole, homeassistant, jellyfin`.
2. Escolha atualização de 15, 30 ou 60 segundos. O padrão é 30; configurações importadas válidas de 15–3600 segundos são preservadas.
3. Ative **Docker** em **Conteúdo e ordem** e aplique. Os filtros permanecem no rascunho até **Aplicar alterações**.
4. **Consultar Docker aplicado** consulta os ajustes já salvos, mesmo se houver um rascunho diferente. A primeira resposta pode indicar coleta em segundo plano; consulte novamente depois de alguns segundos.
5. Selecione Docker na prévia e use **Mostrar esta página no display**. A observação do TFT pode ser feita no checklist final.

Nomes diferenciam maiúsculas/minúsculas e não aceitam curingas, caminhos ou comandos. Use o nome do contêiner, não o nome do serviço Compose, da imagem ou um ID. Ausência de um nome significa que ele não apareceu na lista recebida; não comprova que um serviço externo caiu.

Os filtros e a frequência entram no backup da configuração. Não se exportam caminho do socket, metadados brutos do Engine, labels, portas, comandos, variáveis ou credenciais. As consultas selecionam nomes somente depois de receber a lista local: o filtro não é um mecanismo de autorização do daemon.

## Pré-requisito e limite de segurança

O Docker deve existir no mesmo host e o usuário dos serviços do dashboard precisa ter acesso **já autorizado** ao socket Unix. O dashboard não instala/inicia Docker, não usa `sudo`, não concede grupo `docker` e não modifica permissões ou unidades de serviço.

Importante: o fato de este conector emitir somente GET não transforma o socket do Docker em uma credencial somente de leitura. Acesso ao daemon convencional pode conceder privilégios equivalentes a administrador. Não execute o painel como root, não faça `chmod 666` no socket e não conceda acesso automaticamente. Avalie rootless ou um intermediário local realmente restrito aos dois endpoints antes de decidir conceder novas permissões. [Aviso oficial sobre privilégios do grupo Docker](https://docs.docker.com/engine/install/linux-postinstall/).

O padrão é `/var/run/docker.sock`. Docker rootless ou um proxy Unix podem usar outro caminho absoluto por `ST7789_DOCKER_SOCKET`, configurado **somente pelo administrador no ambiente dos dois serviços**. O caminho não é aceito na interface, na API ou em `config.json`, não é exportado, e deve apontar para um socket Unix. Alterações no ambiente dos serviços exigem reinício autorizado; este recurso não faz esse reinício. Não existem suporte a TCP remoto, socket do Docker Desktop do Mac, TLS remoto ou Podman homologado nesta entrega. `DOCKER_HOST`, proxies HTTP e variáveis do Docker CLI são ignorados.

## Contrato implementado

O provedor negocia a versão anunciada por `GET /version`, aceita somente formato `1.N`, e consulta `GET /v1.N/containers/json?all=1`. Não consulta inspect, logs, stats, secrets nem configuração dos contêineres. Nenhum caminho ou método é fornecido pelo navegador. Referência: [Docker Engine API](https://docs.docker.com/reference/api/engine/), [lista de contêineres](https://docs.docker.com/reference/api/engine/version/v1.46/).

- quatro segundos no total das duas requisições, incluindo cabeçalhos e corpo;
- watchdog contra respostas que enviam bytes lentamente;
- resposta máxima de 256 KiB por requisição e 256 contêineres;
- lista maior/inválida falha explicitamente, sem apresentar totais parciais;
- sem redirects, DNS, proxy, subprocessos ou bibliotecas Docker adicionais;
- coleta assíncrona; atualização mínima de 15 segundos e espera de 30 segundos após falhas;
- última leitura válida conservada e identificada como cache;
- filtro alterado descarta a leitura do filtro anterior;
- somente nome/estado/saúde normalizados chegam à tela; no máximo quatro linhas.

`GET /api/docker/state` exige sessão com PIN e retorna esse resumo/cache. Não aceita parâmetros. POST/PUT/PATCH/DELETE não são implementados; ele não grava ajustes nem muda contêineres. O acesso ao socket só ocorre ao consultar/visualizar esta página, não ao simplesmente abrir o painel com Docker desativado. O provedor não faz varredura de CPU/rede para essa página.

## Estado de entrega e testes finais

118 testes de software passaram no computador, no ARM do Raspberry em checkout separado e no CI; o fluxo completo no navegador passou com um Engine Unix fictício. Casos incluem saúde ausente/desconhecida, problemas, aliases, nomes ausentes, permissões, respostas inválidas/excessivas/incompletas, cabeçalhos lentos, cache após falha, API autenticada, backup e layouts de 1440/980/390/320 px. Esses resultados não homologam um Docker real nem a leitura no TFT.

A revisão `b339eab` foi preparada em `~/.cache/st7789-dashboard-update-v0.7.0`; os 118 testes passaram no ARM em 50,746 s. Dependências e unidades de serviço não mudaram. Um backup privado completo foi criado fora do Git, com prefixo `~/.config/raspberrypi-st7789-dashboard.backup-v0.6-before-v0.7-`. PIN, configuração e chave de sessão foram comparados sem mostrar conteúdos; os serviços ativos não foram atualizados. [CI de testes/navegador](https://github.com/abraaobat/raspberrypi-st7789-dashboard/actions/runs/35226090881) e [GitHub Pages](https://github.com/abraaobat/raspberrypi-st7789-dashboard/actions/runs/35226090871) concluíram com sucesso. Página pública v0.7.0 conferida, com fotos/Pix preservados.

Na auditoria de 17/09/2026, a instalação v0.6.0 do Raspberry estava ativa e saudável, e o socket padrão do Docker não existia. Nenhuma instalação ou mudança de privilégio foi feita. É possível continuar usando todas as páginas anteriores sem Docker. **Não é necessário instalar Docker apenas para testar o display.**

Quando o mantenedor optar por instalar a nova versão:

```bash
cd ~/raspberrypi-st7789-dashboard
git status --short
git pull --ff-only
./scripts/install.sh
./scripts/validate_install.sh
```

Preserve alterações próprias caso o status não esteja limpo. Faça um backup privado recente antes de atualizar. Informe senhas somente no terminal/painel privado, nunca na conversa. A v0.7.0 inclui todos os modelos da v0.6.0, portanto não exige uma instalação intermediária. Depois confira a API `0.7.0` e use o mesmo PIN.

Checklist para o final: fonte HTTP/JSON de interesse real; PI-HOLE/CASA com credenciais privadas; ciclo de Pomodoro de um minuto; Docker real somente onde já autorizado; prévia, legibilidade, seleção, carrossel e os dois botões. MQTT nativo e drivers adicionais continuam futuros.
