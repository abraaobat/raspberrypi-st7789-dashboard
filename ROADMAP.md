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

### D1 — Confiabilidade e legibilidade 🔄

- detectar automaticamente Ethernet e Wi-Fi ativos;
- acomodar adaptadores USB e nomes como `wlan1`/`wlx...`;
- ajustar textos longos, especialmente modelo e kernel;
- distinguir zero real, indisponibilidade e erro de coleta;
- adicionar armazenamento, conectividade e saúde de alimentação/throttling;
- centralizar limites de alerta;
- garantir liberação limpa de GPIO e display no encerramento.

Critério de saída: nenhuma métrica inválida é apresentada como valor real e todo texto permanece dentro da tela.

### D2 — Núcleo modular e testável

- extrair driver do display, botões, scheduler e cache;
- criar registro de páginas e provedores de dados;
- definir contrato comum `collect → render`;
- suportar configuração JSON validada;
- gerar PNGs de referência sem acesso a SPI/GPIO;
- cobrir navegação, coleta e renderização com testes automatizados.

Arquitetura-alvo:

```text
Providers → Page Registry → Pillow Renderer → ST7789
                              └─────────────→ Preview PNG
Buttons ──→ Navigation/Scheduler
Config ───→ Pages, order, refresh and thresholds
```

Critério de saída: páginas podem ser ativadas, ordenadas e testadas sem alterar o loop principal.

### D3 — Web Control Panel MVP

- interface responsiva para computador e celular;
- ativação, desativação e ordenação de páginas;
- configuração de carrossel, página inicial e intervalos;
- prévia 240×240 usando o renderizador canônico;
- API fechada de configuração e saúde;
- persistência atômica fora do repositório;
- serviço web separado do serviço do display;
- autenticação local inicial e proteção de mudanças.

Critério de saída: uma alteração feita no celular aparece no display em poucos segundos, sem reiniciar ou editar código.

### D4 — SysOps e Homelab Pack

- uso de disco, gateway, SSID, sinal e ping;
- estado de serviços `systemd` permitidos por configuração;
- Docker e Tailscale opcionais;
- integração Pi-hole compatível com a versão local;
- estados `OK`, `ALERTA`, `OFFLINE`, `SEM DADOS` e `DESATUALIZADO`;
- cache e frequências de atualização específicas por provedor.

Critério de saída: falhas de serviços e rede são visíveis sem comprometer o loop do display.

### D5 — Desk e IoT Packs

- relógio/data e Pomodoro controlado pelos botões;
- meteorologia com cache e localização explícita;
- Home Assistant e MQTT/Node-RED opcionais;
- páginas para portas, luzes, energia e notificações;
- ticker financeiro opcional, com limites e indicação de atualização.

Critério de saída: módulos podem ser instalados e removidos sem aumentar a superfície obrigatória do núcleo.

### D6 — Distribuição e compatibilidade

- instalador e atualização segura;
- configuração inicial assistida;
- backup e restauração de configuração;
- matriz de Raspberry Pi e módulos ST7789 validados;
- documentação de migração e troubleshooting;
- releases versionadas e rollback.

Critério de saída: uma nova instalação reproduz o sistema sem ajustes manuais fora da documentação.

## Foco atual

O foco é **D1 → D2**. O Web Control Panel depende primeiro de um renderizador desacoplado do hardware e de uma configuração estável. A primeira entrega de D3 deve permanecer pequena: páginas, ordem, carrossel, prévia e salvamento.

## Fora do escopo inicial

- editor visual livre por pixel;
- execução remota de comandos shell;
- exposição direta do painel à internet;
- dependência obrigatória de React, Node.js ou banco de dados;
- armazenamento de tokens e senhas no repositório.
