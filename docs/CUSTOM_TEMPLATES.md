# Modelos para fontes personalizadas — desde v0.6.0

A lista não é fechada: as páginas integradas continuam disponíveis, e o usuário pode criar até oito páginas HTTP/JSON sem editar o código. Os seis modelos são pontos de partida, não plugins instaláveis nem contratos oficiais de APIs de terceiros. A v0.7.0 mantém os modelos e acrescenta a décima página integrada, Docker opcional.

## Modelos incluídos

| Modelo | Campo principal de exemplo | Detalhe de exemplo |
| --- | --- | --- |
| Métrica simples | `value` | `detail` |
| Status de serviço | `health.status` | `health.message` |
| Sensor de temperatura | `sensor.temperature` | `sensor.detail` |
| Consumo de energia | `meter.power` | `meter.detail` |
| Node-RED via HTTP | `dashboard.value` | `dashboard.detail` |
| Item de uma lista | `items.0.status` | `items.0.name` |

Cada modelo contém título, rótulo, unidade, layout, cor e exemplo fictício. Nenhum inclui endereço, token ou script. Unidades não são convertidas: o sensor deve fornecer a unidade indicada. Índices de listas só são adequados quando a ordem da API for estável.

## Criar uma página

1. No painel, clique em **Adicionar fonte** e escolha um modelo.
2. Clique em **Usar modelo** para preencher os campos. Somente escolher o modelo não altera seus campos. Se já estiver preenchido, a substituição pede confirmação; URL e identificação da fonte são preservadas.
3. Abra **Conferir caminhos em um exemplo JSON**. Confira o exemplo fictício ou cole uma resposta do seu app, removendo tokens e dados sensíveis.
4. Use **Conferir exemplo, sem conexão**. O servidor verifica os caminhos e retorna somente os valores selecionados. Não consulta a URL nem salva ajustes. Um caminho ausente, uma lista/objeto no destino ou JSON inválido são recusados.
5. Informe a URL GET/JSON real e adapte os caminhos. **Testar conexão** é um teste diferente: consulta essa URL usando as proteções existentes de HTTP/JSON.
6. Clique em **Guardar no rascunho** e depois em **Aplicar alterações**. Só então a página é salva e fica disponível para o carrossel/display.
7. Na prévia, selecione a página e use **Mostrar esta página no display**. Confirme texto e valor no TFT quando conveniente.

Cancelar o diálogo não aplica campos nem adiciona uma fonte. O exemplo digitado é descartado ao fechar e não faz parte do backup. Respostas antigas de testes não substituem o resultado depois de editar campos ou fechar o diálogo.

## Exemplo de Node-RED

Crie uma rota GET específica de leitura, por exemplo `/st7789-demo`, ligando **HTTP In → Template → Change → HTTP Response**. No Template, use este JSON fictício como `msg.payload`:

```json
{
  "dashboard": {
    "value": 23,
    "detail": "Sensor da bancada"
  }
}
```

No Change, configure `msg.headers` como objeto JSON `{"content-type":"application/json"}`. Use o endereço final da rota no painel. Esse exemplo é estático: não representa um sensor real. Para seus dados, adapte o fluxo para produzir o mesmo contrato ou ajuste os caminhos do modelo.

A dupla HTTP In/HTTP Response e o cabeçalho JSON seguem as receitas oficiais de [endpoint HTTP](https://cookbook.nodered.org/http/create-an-http-endpoint) e [servir conteúdo JSON](https://cookbook.nodered.org/http/serve-json-content). Isso não usa a API administrativa do Node-RED nem adiciona assinatura MQTT ao dashboard.

## Status e limites

No layout Status, valores reconhecidos como `OK`, `ONLINE`, `true` e `healthy` recebem indicador verde; `OFFLINE`, `false`, `error` e `unhealthy`, vermelho. Valores desconhecidos ficam cinza com **VERIFICAR**; `null` fica cinza com **SEM DADOS**. O texto original e o detalhe continuam visíveis; isso não substitui interpretação específica da API monitorada.

O exemplo admite objeto ou lista JSON de até 32 KiB em UTF-8; caminhos têm até 120 caracteres. Valores selecionados são escalares, e textos longos são limitados a 160 caracteres. A API de conferência exige sessão e CSRF. Não cole segredos: os dados são enviados ao painel local, mesmo sem conexão com a fonte externa.

Fontes reais continuam somente GET/JSON, sem headers de autenticação arbitrários, com limites de tempo/tamanho e bloqueio de destinos inseguros. Para serviços autenticados, use os conectores guiados existentes; não remova a autenticação de um serviço para adaptar este modelo.

Os modelos viram páginas personalizadas normais e entram no backup de configuração, sem incluir o catálogo ou o exemplo digitado. Não exigem novas dependências nem mudanças de GPIO/driver. MQTT, Docker detalhado, plugins executáveis e novos drivers permanecem etapas futuras.

## Atualização — roteiro da v0.6.0

A instalação v0.6.0 foi confirmada ativa e saudável no Raspberry em 17/09/2026. Antes dela, foi preparado backup privado e os 100 testes passaram no ARM em checkout separado. O roteiro abaixo é histórico; a atualização seguinte v0.7.0 já inclui estes modelos e pode ser agrupada às próximas entregas. Veja [DOCKER_MONITOR.md](DOCKER_MONITOR.md). Os testes visuais/fonte real foram adiados para o final pelo mantenedor.

Para instalar a biblioteca de modelos, como usuário `pi`, confirme antes que `git status --short` não mostra alterações próprias e prepare outro backup privado se mudou seus ajustes depois dessa preparação. Depois:

```bash
cd ~/raspberrypi-st7789-dashboard
git pull --ff-only
./scripts/install.sh
./scripts/validate_install.sh
curl --fail --silent --show-error http://127.0.0.1:8080/api/health
```

Informe a senha de administrador somente no terminal. Confira API com versão `0.6.0`, atualize o navegador e entre com o mesmo PIN. Testes com exemplos/serviços fictícios não homologam endpoints reais nem legibilidade no display físico.
