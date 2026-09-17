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
- Docker e Tailscale opcionais;
- integração guiada Pi-hole 6 com senha de aplicativo; ✅ software, homologação real pendente
- estados `OK`, `ALERTA`, `OFFLINE`, `SEM DADOS` e `DESATUALIZADO`; ◐
- cache e frequências de atualização específicas por provedor. ✅

Situação: primeiro corte implementado e homologado visualmente no ST7789 real na versão 0.3.0, com disco, gateway, alimentação/throttling, serviços limitados por allowlist e coleta assíncrona.

A v0.4.0 acrescenta coleta autenticada do resumo Pi-hole 6, sem controle de DNS, com cache e encerramento da própria sessão. Validado com API simulada; Pi-hole 5 não é suportado por este conector.

Critério de saída: falhas de serviços e rede são visíveis sem comprometer o loop do display.

### D5 — Desk e IoT Packs

- relógio/data com fuso e formato 12/24 h; ✅ software v0.5.0
- Pomodoro controlado pelo painel, persistente entre serviços, com interrupção segura após reboot; ✅ software v0.5.0
- gestos físicos para controlar Pomodoro sem alterar anterior/próxima; pendente, requer desenho de interação e homologação
- meteorologia com cache e localização explícita; ✅ hardware
- Home Assistant somente de leitura, até quatro entidades escolhidas; ✅ software
- MQTT/Node-RED opcionais; pendente
- página Casa para sensores, portas, luzes e energia; ✅ software; notificações pendentes
- ticker financeiro opcional, com limites e indicação de atualização.
- páginas HTTP/JSON criadas pelo usuário a partir de modelos seguros; ✅ software

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
- documentação de migração e troubleshooting;
- releases versionadas e rollback.

Critério de saída: uma nova instalação reproduz o sistema sem ajustes manuais fora da documentação.

## Foco atual

D0–D3 estão concluídos e homologados. SysOps e Clima da v0.3.0 estão homologados no ST7789 real. A v0.5.0 soma Relógio/Pomodoro offline ao cofre, Pi-hole 6/Home Assistant e backup/restauração da v0.4.0. São 84 testes automatizados aprovados no computador e no ARM, mais fluxo de navegador isolado, incluindo comandos do timer e persistência. No Pi, os testes usaram uma cópia separada, sem substituir a instalação ativa. A página bilíngue e o Pix confirmado permanecem publicados. O Raspberry voltou a responder por SSH; backup privado e auditoria da instalação atual estão aprovados. A implantação da v0.5.0 aguarda execução local do instalador com senha de administrador; os serviços ativos continuam na v0.3.0. Search Console aguarda login do mantenedor; conectores reais, fonte personalizada e novas páginas aguardam observação física. MQTT, Docker detalhado, gestos físicos do Pomodoro e drivers adicionais continuam como evoluções, não como recursos prontos.

O deploy permanece automatizado por `scripts/install.sh`, seguido de `scripts/validate_install.sh` e da checagem manual dos dois botões físicos.

## Sequência de retomada

0. **Concluir atualização:** executar o [roteiro v0.5.0](docs/UPDATE_TO_V05.md) no terminal do Pi, informando a senha de administrador somente quando o instalador pedir. Confirmar versão `0.5.0` na API e auditoria aprovada antes dos testes abaixo.
1. **Fonte personalizada no hardware:** criar pelo painel uma página HTTP/JSON de interesse real e confirmar sua legibilidade no ST7789. O núcleo, a extração e a API já possuem testes; esse gate é somente físico.
2. **Homologar integrações reais:** configurar Pi-hole 6 e Home Assistant pelos assistentes já implementados, comparar dados e observar estados de falha/legibilidade no TFT.
3. **Desk no hardware:** ativar Relógio/Pomodoro pelo painel, executar um ciclo curto, pausar/retomar e observar contagem/legibilidade no TFT. Os botões continuam anterior/próxima; não há novos gestos para homologar nesta versão.
4. **Expansões independentes:** MQTT/Node-RED, Docker detalhado e templates para outros apps. Tokens arbitrários no assistente HTTP/JSON não estão habilitados.
5. **Outros displays:** implementar e homologar drivers SSD1306 e ILI9341. Os perfis e a adaptação do framebuffer não substituem o teste físico de cada módulo.

O roteiro de continuidade e os gates pendentes estão em [docs/NEXT_SESSION.md](docs/NEXT_SESSION.md).

O cofre é armazenamento protegido por permissões, não criptografia de disco. APIs externas não recebem comandos de controle; tokens continuam tendo as permissões concedidas no serviço de origem.

## Fora do escopo inicial

- editor visual livre por pixel;
- execução remota de comandos shell;
- exposição direta do painel à internet;
- dependência obrigatória de React, Node.js ou banco de dados;
- armazenamento de tokens e senhas no repositório.
