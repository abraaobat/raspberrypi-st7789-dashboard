# Roadmap — Raspberry Pi ST7789 Dashboard

Este roadmap transforma o protótipo físico validado em uma plataforma configurável de microdashboards. Percentuais e fases representam maturidade de produto, não esforço linear.

## Princípios

- O display deve continuar útil sem internet e sem a interface web.
- Hardware validado não deve regredir durante a modularização.
- A mesma função de renderização deve alimentar o ST7789, testes e prévia web.
- Integrações externas são opcionais, possuem cache e falham de forma segura.
- Configuração e segredos locais nunca pertencem ao Git.
- Nenhum endpoint web pode executar comandos arbitrários.

## Fases

### D0 — MVP físico validado ✅

Entregas concluídas:

- ST7789 1,3" 240×240 via SPI;
- Raspberry Pi 3 Model B V1.2;
- páginas Status, Rede e Hardware;
- navegação física em GPIO23 e GPIO24;
- renderização com Pillow;
- inicialização automática por `systemd`;
- documentação de instalação, pinagem e fotos reais.

Critério de saída: dashboard inicia automaticamente e as três páginas são navegáveis no hardware real.

### D1 — Confiabilidade e legibilidade ✅

- detectar automaticamente Ethernet e Wi-Fi ativos; ✅
- acomodar adaptadores USB e nomes como `wlan1`/`wlx...`; ✅
- ajustar textos longos, especialmente modelo e kernel; ✅
- distinguir zero real, indisponibilidade e erro de coleta; ✅
- coletar armazenamento, conectividade e saúde de alimentação/throttling para os módulos seguintes; ✅
- centralizar limites de alerta; ✅
- garantir liberação limpa de GPIO no encerramento. ✅

Situação: homologado no Raspberry Pi 3 com Ethernet, Wi-Fi, textos ajustados, estados sem dados e navegação física.

Critério de saída: nenhuma métrica inválida é apresentada como valor real e todo texto permanece dentro da tela no hardware.

### D2 — Núcleo modular e testável ✅

- separar o entry point físico do núcleo testável; ✅
- criar catálogo de páginas e provedores de dados; ✅
- compartilhar o contrato `collect → render`; ✅
- suportar configuração JSON validada e atômica; ✅
- gerar PNGs sem acesso a SPI/GPIO; ✅
- cobrir configuração, renderização e API com testes automatizados; ✅

Arquitetura-alvo:

```text
Providers → Page Registry → Pillow Renderer → ST7789
                              └─────────────→ Preview PNG
Buttons ──→ Navigation/Scheduler
Config ───→ Pages, order, refresh and thresholds
```

Situação: testes automatizados aprovados no computador, no CI e no Raspberry Pi; botões e loop físico homologados.

Critério de saída: páginas podem ser ativadas, ordenadas e testadas sem alterar o loop principal, sem regressão física.

### D3 — Web Control Panel MVP ✅

- interface responsiva para computador e celular; ✅
- ativação, desativação e ordenação de páginas; ✅
- configuração de carrossel, retomada e intervalos; ✅
- prévia 240×240 usando o renderizador canônico; ✅
- API fechada de configuração, estado e saúde; ✅
- persistência atômica fora do repositório; ✅
- serviço web separado do serviço do display; ✅
- PIN local, sessão, CSRF e limite de tentativas; ✅

Situação: homologado em desktop e celular contra o Raspberry Pi real, incluindo PIN, prévia, ordem, seleção de página e carrossel.

Critério de saída: uma alteração feita no celular aparece no display em poucos segundos, sem reiniciar ou editar código.

### D4 — SysOps e Homelab Pack

- uso de disco, gateway, SSID, sinal e ping; ◐ disco, gateway e ping entregues
- saúde de alimentação e throttling; ✅
- estado de serviços `systemd` permitidos por configuração; ✅
- Docker local opcional: contêineres, filtros, saúde e cache; ✅ software v0.7.0; daemon real/TFT pendentes
- Tailscale opcional; ◐ endereço na página Rede; diagnóstico detalhado futuro
- integração guiada Pi-hole 6 com senha de aplicativo; ✅ software, homologação real pendente
- estados `OK`, `ALERTA`, `OFFLINE`, `SEM DADOS` e `DESATUALIZADO`; ◐
- cache e frequências de atualização específicas por provedor. ✅

Situação: primeiro corte implementado e homologado visualmente no ST7789 real na versão 0.3.0, com disco, gateway, alimentação/throttling, serviços limitados por allowlist e coleta assíncrona.

A v0.4.0 acrescenta coleta autenticada do resumo Pi-hole 6, sem controle de DNS, com cache e encerramento da própria sessão. Validado com API simulada; Pi-hole 5 não é suportado por este conector.

A v0.7.0 acrescenta uma página Docker local, com até quatro nomes exatos ou visão geral, execução/parados/saúde, problemas priorizados, cache e diagnóstico de socket/permissão. Emite somente dois GET fechados via Unix, sem bibliotecas adicionais, instalação de Docker, `sudo` ou concessão de privilégios. Acesso ao daemon continua podendo ser equivalente a administrador. Validado com Engine fictício; não é homologação real do Docker.

Critério de saída: falhas de serviços e rede são visíveis sem comprometer o loop do display.

### D5 — Desk e IoT Packs

- relógio/data com fuso e formato 12/24 h; ✅ software v0.5.0
- Pomodoro controlado pelo painel, persistente entre serviços, com interrupção segura após reboot; ✅ software v0.5.0
- gestos físicos para controlar Pomodoro sem alterar anterior/próxima; pendente, requer desenho de interação e homologação
- meteorologia com cache e localização explícita; ✅ hardware
- Home Assistant somente de leitura, até quatro entidades escolhidas; ✅ software
- MQTT 3.1.1 opcional, somente leitura, tópicos exatos/texto/JSON e cofre; ✅ software v0.8.0; broker real/TFT pendentes
- página Casa para sensores, portas, luzes e energia; ✅ software; notificações pendentes
- ticker financeiro opcional, com limites e indicação de atualização.
- páginas HTTP/JSON criadas pelo usuário a partir de modelos seguros; ✅ software
- seis modelos HTTP/JSON, conferência offline de caminhos e isolamento rascunho/aplicação; ✅ software v0.6.0
- modelos ESPHome/Shelly Gen2+/Prometheus escalar com montagem de URL offline, parâmetros fechados e sem instalar apps; ✅ software v0.9.0; serviços reais/TFT pendentes
- Node-RED via endpoint HTTP/JSON; ✅ modelo e roteiro; sensores MQTT também disponíveis na v0.8.0

MQTT usa assinaturas curtas QoS 0, sem PUBLISH/will/sessão persistente e sem dependências obrigatórias. Prefere valores retidos; não garante captura de eventos transitórios nem deduz idade da medição. TLS é validado, e MQTT sem TLS exige consentimento na LAN/tailnet. [Contrato e limites](docs/MQTT_MONITOR.md).

Critério de saída: módulos podem ser instalados e removidos sem aumentar a superfície obrigatória do núcleo.

### D6 — Distribuição e compatibilidade

- instalador e atualização segura;
- landing page bilíngue no GitHub Pages, preparada para indexação e apoio via Pix; ✅
- proteção da publicação contra fotos vazias, proporções incorretas e transbordamento em telas de computador/celular; ✅ testes automatizados
- configuração inicial assistida;
- cofre privado separado da configuração e credenciais vinculadas ao destino; ✅ software
- backup e restauração de configuração sem incluir PIN/cofre; ✅ software
- matriz de Raspberry Pi e módulos ST7789 validados;
- perfis desacoplados de resolução, cor, rotação e driver; ✅ fundação
- adaptação de framebuffer testada para 128×64 monocromático e 320×240 colorido; ✅ software
- layout 128×64 nativo e simulação segura no painel; ✅ software v0.8.0
- drivers opcionais Luma SSD1306/I2C e ILI9341/SPI escolhidos pelo administrador; ✅ software v0.8.0; homologação física pendente
- documentação de migração e troubleshooting;
- releases versionadas e rollback.

Critério de saída: uma nova instalação reproduz o sistema sem ajustes manuais fora da documentação.

## Foco atual

D0–D3 estão concluídos e homologados. SysOps e Clima da v0.3.0 estão homologados no ST7789 real. A instalação v0.6.0 foi confirmada ativa e saudável no Raspberry em 17/09/2026. Isso não substitui observação visual das novas páginas. Por decisão do mantenedor, os testes manuais ficam para o final e não bloqueiam as expansões independentes. A v0.7.0 acrescenta Docker local somente de leitura, filtros, contagem de saúde e cache. São 118 testes de software e fluxo completo de navegador isolado aprovados. O socket padrão Docker não existe no Pi; não houve instalação nem autorização de acesso. A biblioteca v0.9.0 oferece nove modelos HTTP/JSON, incluindo ESPHome, Shelly e Prometheus escalar, com montagem offline de URL. Não instala código de terceiros nem cria fontes automaticamente. A página bilíngue e o Pix confirmado são preservados. Search Console aguarda login. MQTT e drivers opcionais SSD1306/ILI9341 têm implementação v0.8.0, ainda sem homologação dos serviços/módulos reais. OLED tem resumo nativo, e simulação no painel não troca hardware. Gestos físicos do Pomodoro continuam futuros; Docker real e novas páginas ainda não estão homologados no TFT.

O deploy permanece automatizado por `scripts/install.sh`, seguido de `scripts/validate_install.sh` e da checagem manual dos dois botões físicos.

**Evidência v0.8.0:** 145 testes passaram no computador e no ARM em checkout separado; os três casos opcionais com Mosquitto foram ignorados nesses hosts. No [CI](https://github.com/abraaobat/raspberrypi-st7789-dashboard/actions/runs/35229790027), todos os 148 passaram, assim como o fluxo completo do painel. Backup privado recente e auditoria posterior confirmaram a instalação ativa v0.6.0 preservada. Simulação/layouts e construtores dos drivers extras têm testes de software, não homologação física. [Detalhes da preparação](docs/NEXT_SESSION.md).

## Sequência de retomada

**Evidência local v0.9.0:** 165 casos executados; 162 passaram e três opcionais Mosquitto foram ignorados. Fluxo de navegador com os três serviços fictícios aprovado, além de regressão dos conectores/MQTT/Docker/Desk e quatro tamanhos. Extração/renderização nos três perfis é prova de software, não teste de dispositivos reais. [Contratos de apps](docs/APP_RECIPES.md).

0. **Continuar o desenvolvimento:** distribuição/rollback, outros contratos de apps e refinamentos após os gates de uso real. MQTT e drivers extras têm implementação de software v0.8.0. Os testes abaixo ficam no checklist final, sem serem marcados como aprovados antes de execução real. A v0.6.0 já está instalada; a versão mais recente inclui as anteriores, sem atualizações intermediárias.
1. **Fonte personalizada no hardware:** criar pelo painel uma página HTTP/JSON de interesse real e confirmar sua legibilidade no ST7789. O núcleo, a extração e a API já possuem testes; esse gate é somente físico.
2. **Homologar integrações reais:** configurar Pi-hole 6 e Home Assistant pelos assistentes já implementados, comparar dados e observar estados de falha/legibilidade no TFT.
3. **Desk no hardware:** ativar Relógio/Pomodoro pelo painel, executar um ciclo curto, pausar/retomar e observar contagem/legibilidade no TFT. Os botões continuam anterior/próxima; não há novos gestos para homologar nesta versão.
4. **Docker real, opcional:** em um host onde o daemon e acesso local já estejam autorizados, comparar execução/saúde, nomes ausentes e cache com o monitor. Não instalar Docker nem conceder privilégios só para testar o display. Node-RED HTTP/JSON já tem modelo/roteiro, com fluxo real pendente; tokens arbitrários no assistente genérico continuam não habilitados.
5. **MQTT real, opcional:** usar broker existente e tópicos retidos, conferir valores/sem dados/cache e observar a página no TFT. Não instalar broker só para testar; não é captura contínua de eventos.
6. **Outros displays:** simular sem trocar hardware; homologar os drivers experimentais SSD1306/ILI9341 somente em montagens compatíveis próprias. A implementação e os testes de software não substituem evidência física. [Matriz de compatibilidade](docs/DISPLAY_COMPATIBILITY.md).

O roteiro de continuidade e os gates pendentes estão em [docs/NEXT_SESSION.md](docs/NEXT_SESSION.md).

O cofre é armazenamento protegido por permissões, não criptografia de disco. APIs externas não recebem comandos de controle; tokens continuam tendo as permissões concedidas no serviço de origem.

## Fora do escopo inicial

- editor visual livre por pixel;
- execução remota de comandos shell;
- exposição direta do painel à internet;
- dependência obrigatória de React, Node.js ou banco de dados;
- armazenamento de tokens e senhas no repositório.
