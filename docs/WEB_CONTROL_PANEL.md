# Web Control Panel

## Objetivo

Permitir que o usuário configure o ST7789 pelo computador ou celular, mantendo o display operacional mesmo quando o painel web estiver parado ou indisponível.

O painel é um configurador local, não um substituto do display físico.

## Experiência entregue no MVP

### Display

- prévia fiel de 240×240;
- página atualmente selecionada;
- navegação anterior/próxima para inspecionar páginas;
- estado atual do serviço do display.

### Páginas

- catálogo de módulos disponíveis;
- ativação e desativação;
- ordenação por controles subir/descer;
- catálogo extensível com páginas nativas, integrações e fontes personalizadas;
- remoção e edição de páginas HTTP/JSON criadas pelo usuário.

### Comportamento

- carrossel automático;
- intervalo do carrossel;
- retomada automática após interação física;
- limites de alerta;
- unidade de temperatura.

### Integrações entregues na versão 0.3

- serviços `systemd` explicitamente permitidos;
- meteorologia opcional com cache;
- assistente genérico HTTP/JSON com teste de conexão;
- indicador de conexão, erro e uso do último dado em cache.

### Novidades da versão 0.4

- assistentes fechados de Pi-hole 6 e Home Assistant, somente monitoramento;
- até quatro entidades do Home Assistant selecionadas por ID;
- cofre privado, separado dos ajustes, com credenciais vinculadas ao endereço do serviço;
- teste sem gravação e consentimento explícito para HTTP autenticado na LAN/tailnet;
- exportação dos ajustes aplicados e restauração validada sem modificar PIN ou cofre.

### Novidades da versão 0.5

- módulos opcionais Relógio/Pomodoro, desativados na atualização;
- fuso IANA ou do sistema, segundos opcionais e formato 12/24 h;
- duração do próximo ciclo aplicada com os demais ajustes;
- iniciar/pausar/retomar/reiniciar com efeito imediato, sessão e CSRF;
- ciclo preservado entre serviços e ao restaurar ajustes; execução interrompida com aviso após reboot do Pi;
- navegação física e carrossel não mudam por iniciar um ciclo.

Detalhes e teste físico pendente: [DESK_MODE.md](DESK_MODE.md).

## Arquitetura

```text
Browser on LAN or tailnet
          │
          ▼
Web UI ── API autenticada de configuração
          │
          ├── config.json (sem segredos)
          ├── auth.json + session-secret.bin (permissão 0600)
          ├── credentials.json (privado; sem endpoint de leitura)
          ├── pomodoro.json (estado privado compartilhado)
          ├── control.json + display-state.json
          └── preview endpoint
                    │
                    ▼
System + async integrations → Extensible Page Registry → Pillow Renderer
                                                           ├── Display profile → ST7789
                                                           └── Preview PNG
```

### Serviços separados

`bench-display.service` controla SPI, GPIO, navegação e atualização do ST7789.

`bench-display-web.service` fornece a interface web e a API. Reiniciar o painel web não deve apagar, congelar ou reiniciar o display.

## Persistência

Arquivos locais usados:

```text
/home/pi/.config/raspberrypi-st7789-dashboard/
├── config.json
├── auth.json
├── session-secret.bin
├── credentials.json
├── .credentials.lock
├── pomodoro.json
├── .pomodoro.lock
├── control.json
└── display-state.json
```

Requisitos:

- gravação atômica usando arquivo temporário e substituição;
- validação contra uma allowlist de páginas, temas e opções;
- defaults seguros quando o arquivo não existir ou estiver inválido;
- segredos com permissão `0600` e nunca retornados pela API;
- nenhuma gravação em arquivos rastreados pelo Git.

## API inicial

| Método | Endpoint | Finalidade |
|---|---|---|
| `GET` | `/api/health` | saúde e versão dos serviços |
| `GET` | `/api/auth/status` | estado da autenticação local |
| `POST` | `/api/auth/setup` | criar o PIN no primeiro acesso |
| `POST` | `/api/auth/login` | iniciar sessão local |
| `POST` | `/api/auth/logout` | encerrar sessão local |
| `GET` | `/api/catalog` | páginas e opções disponíveis |
| `GET` | `/api/config` | configuração pública atual |
| `PUT` | `/api/config` | validar e salvar configuração |
| `GET` | `/api/preview?page=status` | PNG 240×240 da página |
| `POST` | `/api/display/page` | selecionar página ativa permitida |
| `POST` | `/api/sources/test` | validar e consultar uma fonte HTTP/JSON sem salvá-la |
| `GET` | `/api/integrations/status` | presença da credencial e endereço vinculado, sem segredo |
| `PUT` | `/api/integrations/<id>/credential` | guardar/substituir `{baseUrl, secret}` para ID fechado |
| `DELETE` | `/api/integrations/<id>/credential` | apagar somente a credencial local |
| `POST` | `/api/integrations/<id>/test` | testar `{settings, secret?}` sem persistir |
| `GET` | `/api/config/export` | baixar os ajustes aplicados, sem PIN/cofre |
| `POST` | `/api/config/import` | restaurar configuração validada, preservando PIN/cofre |
| `GET` | `/api/pomodoro/state` | estado, duração do ciclo, restante e progresso; sem boot/prazo interno |
| `POST` | `/api/pomodoro/command` | ação fechada `start`, `pause`, `resume` ou `reset`; usa duração aplicada |

IDs permitidos: `pihole` e `homeassistant`. Todos esses endpoints exigem sessão autenticada; mudanças e testes também exigem CSRF. O teste usa a credencial digitada ou, se ausente, a credencial local vinculada ao endereço. Não há `GET` de credencial. Exemplo de ajustes não secretos:

```json
{
  "pihole": {"baseUrl": "http://pi.hole", "allowInsecureHttp": true},
  "homeassistant": {"baseUrl": "https://home.example", "allowInsecureHttp": false, "entities": ["sensor.energia", "binary_sensor.porta"]}
}
```

Não haverá endpoint de shell, instalação arbitrária ou escrita de caminhos fornecidos pelo cliente.

## Configuração inicial

Exemplo conceitual:

```json
{
  "schemaVersion": 1,
  "theme": "dark",
  "displayProfile": "st7789-240x240",
  "temperatureUnit": "celsius",
  "carousel": {
    "enabled": true,
    "intervalSeconds": 8,
    "resumeAfterSeconds": 30
  },
  "pages": [
    {"id": "status", "enabled": true, "refreshSeconds": 1},
    {"id": "network", "enabled": true, "refreshSeconds": 5},
    {"id": "hardware", "enabled": true, "refreshSeconds": 30},
    {"id": "sysops", "enabled": false, "refreshSeconds": 15},
    {"id": "weather", "enabled": false, "refreshSeconds": 600}
  ],
  "weather": {"locationName": "", "latitude": null, "longitude": null, "refreshMinutes": 15},
  "sysops": {"services": []},
  "customPages": []
}
```

## Tecnologia implementada

- Flask organizado por application factory;
- HTML, CSS e JavaScript sem framework pesado;
- Pillow como renderizador canônico;
- Waitress como servidor WSGI;
- JSON para configuração;
- `systemd` para os dois serviços.

Um banco de dados não é necessário no MVP. Estado transitório pode permanecer em memória e configuração persistente deve continuar legível e exportável.

## Segurança

- acesso pela LAN por padrão;
- autenticação/PIN configurado no primeiro uso;
- proteção CSRF para operações de mudança;
- sessão com cookie `HttpOnly` e `SameSite=Lax`;
- rate limit para autenticação;
- integração remota preferencialmente via Tailscale;
- nenhuma porta deve ser exposta diretamente na internet;
- tokens externos não entram em logs, respostas ou commits.

## Critérios de aceite do MVP

- funciona em navegador móvel e desktop;
- mostra prévia igual ao framebuffer enviado ao ST7789;
- permite ativar e ordenar páginas nativas e personalizadas;
- salva carrossel, intervalos, páginas ativas e ordem;
- aplica a mudança ao display sem reinicialização manual;
- display continua funcionando se o painel web cair;
- configuração inválida é rejeitada sem corromper o último estado válido;
- não existe execução de comandos arbitrários pela API.

Todos os itens do MVP foram homologados no Raspberry Pi 3 real em desktop e celular. Clima e SysOps também foram homologados visualmente no ST7789 físico. Fontes personalizadas e perfis experimentais de display possuem testes automatizados e verificação em navegador; resta somente a homologação física de uma página HTTP/JSON e de futuros drivers adicionais.

Os assistentes/cofre/backup da v0.4.0 passaram por testes de API e navegador com serviços simulados, em 1440/980/390/320 px. Acesso a Pi-hole/Home Assistant reais e leitura das novas páginas no TFT permanecem pendentes. Veja [limites e recuperação das credenciais](BACKUP_AND_CREDENTIALS.md).

A v0.5.0 acrescenta Relógio/Pomodoro, com 84 testes de software aprovados também no ARM em checkout separado e fluxo de comandos verificado no navegador isolado. Testes de reboot/conclusão usam tempo injetado; não representam reinicialização física nem observação do TFT. O Pi está acessível, mas os serviços ativos continuam na v0.3.0; a atualização exige senha de administrador no terminal. Veja o [roteiro de implantação](UPDATE_TO_V05.md).
