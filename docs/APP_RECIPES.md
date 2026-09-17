# ESPHome, Shelly e Prometheus — modelos HTTP/JSON v0.9.0

Modelos opcionais dentro de **Adicionar fonte**, não novas páginas nativas ou instalação de apps. O núcleo mantém 11 páginas integradas e até oito fontes personalizadas. Exemplos são fictícios. **Usar modelo**, **Montar URL, sem conexão**, **Conferir exemplo**, **Testar conexão** e **Guardar/Aplicar** são ações distintas. Cancelar não altera o display. O endereço base aceita somente origem HTTP/HTTPS, sem caminho/credenciais; proxies com prefixo exigem URL manual.

## Sensor ESPHome

Requer `web_server` já habilitado. O contrato atual usa o nome YAML exato do sensor, incluindo espaços/UTF-8, em GET `/sensor/<nome>`; subdispositivos usam `/sensor/<dispositivo>/<nome>`. O helper codifica cada segmento e não oferece ações. Extrai `value` e detalhe `state`. Confira unidade e nome: firmwares antigos podem usar outra identificação, exigindo URL manual. Baseado na [Web Server API oficial](https://esphome.io/web-api/).

Exemplo fictício:

```json
{"id":"sensor/Temperatura externa","state":"28.1 °C","value":28.1}
```

A unidade começa vazia porque o modelo serve a sensores numéricos diferentes. Se o valor real for Celsius, informe `°C`; não há conversão automática. Não há assinatura SSE ou descoberta de entidades.

## Potência Shelly Gen2+

GET `/rpc/Switch.GetStatus?id=0` fornece o estado do componente Switch. O campo `apower` representa watts somente nos modelos com medição; Gen1 e equipamentos sem esse campo não são abrangidos. Baseado no [contrato oficial Switch](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Switch/).

O helper aceita canal decimal 0–63 e fixa `Switch.GetStatus`: sem `Set`, `Toggle` ou seletor RPC livre. Extrai `apower`, com unidade `W` e layout Métrica. Campo ausente causa erro de extração, nunca consumo zero inventado. Exemplo fictício:

```json
{"id":0,"source":"init","output":true,"apower":318,"voltage":230}
```

## Prometheus escalar

GET `/api/v1/query` com `query` codificada e `timeout=2s`. O modelo extrai `data.result.1` do par escalar timestamp/valor, não o primeiro item de um vetor. A ordem dos vetores não é garantida. Selecione a série desejada, por exemplo `scalar(up{job="prometheus",instance="pi:9090"})`: sem exatamente uma amostra float, `scalar()` retorna `NaN`, não zero nem saúde aprovada. [HTTP API oficial](https://prometheus.io/docs/prometheus/latest/querying/api/) e [função scalar](https://prometheus.io/docs/prometheus/latest/querying/functions/#scalar).

O exemplo padrão precisa ser adaptado ao seu seletor. Exemplo fictício:

```json
{"status":"success","data":{"resultType":"scalar","result":[1710000000,"1"]}}
```

Layout Métrica é neutro; unidade começa vazia. O helper não interpreta/executa PromQL nem converte `NaN` em falha/sucesso. Vetores, matrizes e histogramas não seguem este contrato. O timeout solicitado não amplia os limites do cliente HTTP.

## Proteções e autenticidade dos dados

Não adicionamos autenticação ESPHome, Digest Shelly ou headers Bearer Prometheus ao assistente genérico. Não remova autenticação para adaptar um dispositivo. Prefira uma integração autorizada já existente, como Home Assistant/MQTT, ou uma ponte própria somente de leitura. Não cole senhas/tokens nos campos ou exemplos.

A montagem exige sessão/CSRF mas não faz DNS/HTTP nem escreve estado. O teste real faz GET pelo cliente limitado existente: HTTPS validado, destino fixado por conexão, sem proxy/redirect e bloqueio de endereços inseguros. A página aplicada usa o cache assíncrono existente. Mesmo um GET pode ter efeitos em APIs mal desenhadas: use apenas rotas de leitura documentadas e serviços sob sua autorização.

Testes locais verificam nomes UTF-8/subdispositivos, limites, query sem injeção de parâmetros, GET em três servidores fictícios, nenhum acesso/gravação durante montagem e renderização nos três perfis de software. O navegador verifica cancelamento/respostas antigas e quatro tamanhos. Isso não homologa equipamentos reais. Teste final: escolher apenas os apps que já possui, comparar valor/unidade e observar a página no TFT; [checklist](FINAL_VALIDATION.md).
