# Web Control Panel

## Objetivo

Permitir que o usuário configure o ST7789 pelo computador ou celular, mantendo o display operacional mesmo quando o painel web estiver parado ou indisponível.

O painel é um configurador local, não um substituto do display físico.

## Experiência prevista

### Display

- prévia fiel de 240×240;
- página atualmente selecionada;
- navegação anterior/próxima para inspecionar páginas;
- estado do serviço do display e última atualização.

### Páginas

- catálogo de módulos disponíveis;
- ativação e desativação;
- ordenação por arrastar ou controles subir/descer;
- página inicial;
- perfis prontos como SysOps, Homelab, Mesa e IoT.

### Comportamento

- carrossel automático;
- intervalo por página;
- retomada automática após interação física;
- limites de alerta;
- unidade de temperatura e formato de hora.

### Integrações

- serviços `systemd` explicitamente permitidos;
- Pi-hole, Home Assistant, MQTT, meteorologia e mercado como módulos opcionais;
- indicador de conexão, erro, cache e idade do último dado.

## Arquitetura

```text
Browser on LAN or tailnet
          │
          ▼
Web UI ── API de configuração
          │
          ├── config.json (sem segredos)
          ├── secrets.env (permissão 0600)
          └── preview endpoint
                    │
                    ▼
Providers → Page Registry → Pillow Renderer
                                 ├── ST7789
                                 └── PNG 240×240
```

### Serviços separados

`bench-display.service` controla SPI, GPIO, navegação e atualização do ST7789.

`bench-display-web.service` fornece a interface web e a API. Reiniciar o painel web não deve apagar, congelar ou reiniciar o display.

## Persistência

Arquivos locais sugeridos:

```text
/home/pi/.config/raspberrypi-st7789-dashboard/
├── config.json
└── secrets.env
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
| `GET` | `/api/catalog` | páginas e opções disponíveis |
| `GET` | `/api/config` | configuração pública atual |
| `PUT` | `/api/config` | validar e salvar configuração |
| `GET` | `/api/preview?page=status` | PNG 240×240 da página |
| `POST` | `/api/display/page` | selecionar página ativa permitida |

Não haverá endpoint de shell, instalação arbitrária ou escrita de caminhos fornecidos pelo cliente.

## Configuração inicial

Exemplo conceitual:

```json
{
  "schemaVersion": 1,
  "theme": "dark",
  "temperatureUnit": "celsius",
  "carousel": {
    "enabled": true,
    "intervalSeconds": 8,
    "resumeAfterSeconds": 30
  },
  "pages": [
    {"id": "status", "enabled": true, "refreshSeconds": 1},
    {"id": "network", "enabled": true, "refreshSeconds": 5},
    {"id": "hardware", "enabled": true, "refreshSeconds": 30}
  ]
}
```

## Tecnologia proposta

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
- sessão com cookie seguro quando HTTPS estiver disponível;
- rate limit para autenticação e gravação;
- integração remota preferencialmente via Tailscale;
- nenhuma porta deve ser exposta diretamente na internet;
- tokens externos não entram em logs, respostas ou commits.

## Critérios de aceite do MVP

- funciona em navegador móvel e desktop;
- mostra prévia igual ao framebuffer enviado ao ST7789;
- permite ativar e ordenar as três páginas atuais;
- salva carrossel, intervalo e página inicial;
- aplica a mudança ao display sem reinicialização manual;
- display continua funcionando se o painel web cair;
- configuração inválida é rejeitada sem corromper o último estado válido;
- não existe execução de comandos arbitrários pela API.
