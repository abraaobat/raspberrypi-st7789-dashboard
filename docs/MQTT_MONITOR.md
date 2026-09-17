# MQTT — sensores e estados, somente leitura

Disponível como a 11ª página opcional na v0.8.0. Entra **desativada** na atualização; preserva páginas, ordem, PIN e navegação existentes. Não instala broker nem muda seus dispositivos.

## Configurar pelo computador ou celular

1. No painel privado, abra **MQTT** e informe `mqtts://servidor:8883`, sem usuário/senha na URL.
2. Escolha até quatro sensores: nome, tópico exato, formato e unidade. Texto simples usa o payload inteiro; JSON aceita caminhos como `sensor.power` ou `items.0.value`, terminando em um valor simples.
3. Se o broker exigir login, cadastre uma conta limitada à leitura e use **Guardar credencial MQTT**. Usuário/senha ficam no cofre privado `0600`, vinculados ao broker; guardar segredo não aplica ajustes nem ativa a página. Não envie credenciais nesta conversa.
4. Ative **MQTT** em Conteúdo e ordem e use **Aplicar alterações**.
5. Clique **Consultar MQTT aplicado**. A consulta considera somente os ajustes já aplicados, nunca o rascunho. Se indicar coleta em segundo plano, consulte novamente depois de alguns segundos.
6. Selecione a página na prévia e use **Mostrar esta página no display**.

Sem credencial guardada, o acesso é anônimo, se permitido pelo broker. Uma credencial vinculada a outro endereço bloqueia a consulta; ela não é enviada ao novo destino. Guarde a correta ou remova a anterior explicitamente. TLS verifica certificado e nome do servidor usando a confiança do sistema. Não há opção para ignorar certificado, enviar arquivos arbitrários ou escolher métodos/headers pelo navegador.

`mqtt://IP-local:1883` exige consentimento explícito e é permitido somente na LAN/loopback/tailnet, inclusive sem senha. Nesse modo, credencial e dados trafegam sem criptografia; prefira TLS. Cadastre segredos somente por uma conexão confiável com o painel local.

## O que esta primeira versão faz — e não faz

O conector usa um subconjunto fechado de **MQTT 3.1.1**: CONNECT com sessão limpa, SUBSCRIBE de tópicos exatos solicitando QoS 0 e DISCONNECT. Não envia PUBLISH, não define will, não controla luzes/portas e não cria sessões persistentes. São até quatro tópicos distintos, sem `+`, `#` ou assinatura compartilhada. Uma conta de leitura e ACL do broker continuam necessárias: o código não reduz permissões concedidas na origem.

Cada coleta abre uma assinatura curta de até quatro segundos após a resolução DNS, recebe um valor por tópico e fecha. Prefira sensores publicados como **retained**; não é um assinante contínuo, histórico de eventos, alarme em tempo real ou garantia de captura de mensagens transitórias. Um evento publicado entre duas coletas pode não ser visto. MQTT 5, WebSockets, certificados de cliente e discovery automático não são suportados neste corte.

**RETIDO** significa armazenado no broker, não medido agora. `receivedAt` indica quando o dashboard recebeu a consulta, não quando o sensor mediu. Para decisões que exigem atualidade, inclua horário da medição no sistema de origem e confira-o; esta versão não calcula idade da medição. Sem mensagem/null/ACL recusada mostra **SEM DADOS/ERRO**, nunca zero ou desligado inventado. Zero, `false` e `off` efetivamente recebidos são valores válidos. Texto é literal, não HTML/comando; JSON só retorna escalares.

Quando o broker falha, o último resultado pode permanecer com **CACHE / sem confirmação**, sem se passar por leitura atual. Frequência padrão: 30 s; mínima: 15 s. Falhas têm espera mínima de 30 s antes de nova tentativa. Display e painel têm caches/coletas separados e podem receber instantes diferentes. Nenhuma página local depende do MQTT para continuar funcionando.

## Limites e API

- 8 KiB por pacote, verificados antes de alocar o payload declarado; 32 KiB e 32 pacotes por consulta.
- Deadline único de conexão/TLS/cabeçalhos/payload após DNS; bytes lentos não renovam esse prazo.
- Destinos resolvidos são verificados e fixados na conexão; TLS mantém o nome original. Sem proxy/redirect e sem subprocesso no conector.
- `GET /api/mqtt/state`: sessão obrigatória, sem parâmetros, somente leitura dos ajustes aplicados.
- `GET /api/mqtt/credential/status`: apenas metadados, nunca usuário/senha.
- `PUT /api/mqtt/credential`: broker/usuário/senha com sessão e CSRF; `DELETE` remove explicitamente o segredo.
- Não existe endpoint de publicação ou controle MQTT. Configuração/backup exporta broker, tópicos, formato e unidades, não credenciais.

O cofre continua sendo proteção por permissões, não criptografia de disco. Depois de cadastrar MQTT, versões anteriores à v0.8.0 não compreendem essa entrada: rollback precisa considerar o backup privado anterior, sem descartar credenciais de outros conectores.

## Evidência e teste final

Software e navegador são verificados com broker fictício local, incluindo texto/JSON, autenticação, ACL recusada, falta de mensagem, pacotes inválidos/grandes/lentos, TLS, cache, backup e ausência de PUBLISH. O CI também executa interoperabilidade com Mosquitto isolado e contas/tópicos fictícios; ferramentas Mosquitto não fazem parte do instalador do Raspberry.

Seu broker/dispositivos reais e a página MQTT no TFT permanecem no [checklist final](FINAL_VALIDATION.md). Não instale broker nem configure serviços só para esse teste; use os que já possui. A instalação ativa do Pi foi preservada na v0.6.0 durante o desenvolvimento.

Em 17/09/2026, a revisão `90902db` passou em 145 casos no computador e no ARM em checkout separado; três casos opcionais de Mosquitto foram ignorados nestes hosts. No [CI](https://github.com/abraaobat/raspberrypi-st7789-dashboard/actions/runs/35229790027), os 148 passaram, incluindo os três casos com broker real isolado e o fluxo de navegador. [Preparação/backup e instalação preservada](NEXT_SESSION.md).

Referências primárias do contrato: [MQTT 3.1.1 — OASIS](https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html), [autenticação/ACL — Mosquitto](https://mosquitto.org/man/mosquitto-conf-5.html).
