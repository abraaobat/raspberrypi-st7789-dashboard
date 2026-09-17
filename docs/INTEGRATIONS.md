# Integrações, clima e páginas personalizadas

## Princípios

- integrações são opcionais e entram desativadas em instalações existentes;
- nenhuma consulta externa bloqueia o loop do display;
- o último valor válido permanece disponível quando uma fonte fica offline;
- a API nunca executa shell, código Python ou conteúdo recebido da fonte;
- configuração e URLs ficam no diretório privado do usuário, nunca no Git.

## Clima

No painel web:

1. preencha um nome curto para a localização;
2. informe latitude e longitude;
3. escolha a frequência entre 10 e 60 minutos;
4. ative a página **Clima** em **Conteúdo e ordem**;
5. aplique as alterações.

A consulta usa o endpoint de previsão do Open-Meteo e solicita condição atual, temperatura aparente, código WMO, mínima, máxima e probabilidade máxima de precipitação. O provedor funciona em segundo plano: a primeira renderização mostra carregamento e a seguinte usa o dado recebido. Em falhas posteriores, a tela mostra `CACHE` e conserva a última leitura válida.

O endpoint gratuito do Open-Meteo é apropriado para uso pessoal e não comercial, possui limites de uso e exige atribuição CC BY 4.0. Uso comercial requer um plano ou provedor compatível. Consulte a [documentação](https://open-meteo.com/en/docs) e os [termos oficiais](https://open-meteo.com/en/terms).

## SysOps local

A página **SysOps** combina:

- ocupação da partição raiz;
- gateway detectado pela rota padrão e seu ping;
- resultado de `vcgencmd get_throttled` quando disponível, traduzido em `OK`, `ALERTA` atual ou `HISTÓRICO`;
- até quatro serviços `systemd` definidos no painel.

Os nomes dos serviços aceitam apenas letras, números, `@`, `_`, `.`, `-` e sufixo opcional `.service`. O backend chama `systemctl is-active` com argumentos separados e nunca interpola shell.

## Docker local (versão 0.7.0)

A página opcional **Docker** consulta somente o Engine local via socket Unix já autorizado, com até quatro filtros por nome, contagem de execução/parados/saúde e cache assíncrono. Não instala Docker nem concede permissões. Acesso ao daemon pode equivaler a administrador, mesmo usando somente GET. Veja [DOCKER_MONITOR.md](DOCKER_MONITOR.md) para configuração, limites, ausência de socket e testes reais adiados.

## Fonte HTTP/JSON

Use **Adicionar fonte** para cadastrar:

- título e rótulo exibidos;
- URL HTTP ou HTTPS;
- caminho do valor principal;
- caminho secundário opcional;
- unidade, cor e layout.

Exemplo de resposta:

```json
{
  "sensor": {
    "power": 318,
    "unit": "W"
  }
}
```

Configuração correspondente:

```text
Valor principal: sensor.power
Valor secundário: sensor.unit
Unidade: W
Layout: Métrica
```

Listas usam índice numérico: `items.0.status`.

O botão **Testar conexão** consulta a fonte sem salvar. **Guardar no rascunho** prepara a página no final do carrossel; ela só chega ao display após **Aplicar alterações**. Pode ser desativada ou reordenada como qualquer página nativa.

### Limites de segurança

- somente `GET` HTTP/HTTPS;
- timeout de quatro segundos;
- resposta máxima de 128 KiB;
- raiz obrigatoriamente objeto ou lista JSON;
- redirecionamentos bloqueados;
- endereços link-local, multicast, reservados e não especificados bloqueados;
- loopback e redes privadas permitidos intencionalmente para homelab;
- no máximo oito páginas personalizadas;
- texto final limitado antes da renderização;
- credenciais embutidas na URL são rejeitadas.

O assistente genérico continua sem headers/tokens arbitrários. APIs autenticadas são atendidas pelos conectores fechados abaixo; para outros apps, use uma API de leitura compatível ou um adaptador local dedicado. Não coloque tokens em parâmetros da URL: URLs fazem parte do backup da configuração.

## Pi-hole 6 (versão 0.4.0)

Em **Integrações guiadas → Configurar Pi-hole**:

1. Informe o endereço base final do serviço, por exemplo `http://pi.hole`, sem `/admin`, `/api`, senha ou parâmetros. Prefixos simples de reverse proxy são aceitos.
2. No Pi-hole 6, gere uma senha de aplicativo nas configurações de API e copie-a para o campo privado. Não use o hash legado do Pi-hole 5.
3. Prefira HTTPS. Se o serviço só oferece HTTP, autorize explicitamente seu uso na rede local/tailnet.
4. Use **Testar conexão**. O teste não salva a senha nem os ajustes.
5. Marque a ativação da página, use **Guardar ajustes** e depois **Aplicar alterações**. Uma senha digitada é guardada ao confirmar os ajustes; o botão **Guardar credencial agora** permite fazê-lo separadamente.

O conector faz `POST /api/auth`, coleta `GET /api/stats/summary` com `X-FTL-SID` e encerra apenas sua sessão com `DELETE /api/auth`. A página mostra bloqueios, consultas, porcentagem, clientes ativos e domínios na lista de bloqueio. A janela temporal é a fornecida pelo resumo da API, não um cálculo próprio de “hoje”. Não há mudança de bloqueio DNS nem outros comandos administrativos.

Referências oficiais: [autenticação e senhas de aplicativo](https://docs.pi-hole.net/api/auth/), [API Pi-hole 6 e documentação local](https://docs.pi-hole.net/api/). Pi-hole 5 requer um conector separado e não é suportado por este assistente.

## Home Assistant (versão 0.4.0)

Em **Configurar Home Assistant**, informe a raiz final, por exemplo `http://homeassistant.local:8123`, um token de acesso de longa duração criado no perfil e até quatro IDs distintos de entidades. Copie os IDs em **Ferramentas do desenvolvedor → Estados**:

```text
sensor.temperatura, sensor.energia, binary_sensor.porta, light.sala
```

Teste a conexão, guarde os ajustes e aplique. HTTP também exige autorização explícita. O cliente usa apenas `GET /api/states/<entity_id>` com `Authorization: Bearer ...`; não envia ações, eventos, comandos ou alterações de estado. Somente nome amigável, estado e unidade das entidades escolhidas entram no resultado. Não se busca o inventário inteiro da casa.

IDs inexistentes (`404`), `unknown` e `unavailable` são exibidos como `SEM DADOS`. Erros de autenticação/conexão conservam o último quadro válido com `CACHE`, quando houver. O token herda as permissões do usuário no Home Assistant: um conector somente de leitura **não transforma o token em uma credencial somente de leitura**. Use o menor privilégio viável e revogue tokens que não utiliza.

Referência oficial: [REST API do Home Assistant](https://developers.home-assistant.io/docs/api/rest/).

## Proteções e atualização

- Configuração de integração aceita somente endereço, consentimento HTTP e IDs de entidades; segredos usam endpoints próprios e arquivo privado separado.
- A credencial fica vinculada ao endereço base canônico, incluindo protocolo, porta e prefixo. Alterar o destino não transfere o segredo automaticamente; é necessário cadastrá-lo para o novo destino.
- Respostas do painel não incluem segredo, SID ou revisão interna. Não há endpoint para ler uma credencial salva.
- Destinos verificados são fixados por IP durante cada conexão, sem redirecionamentos ou proxies de ambiente. HTTPS mantém validação de certificado e nome do servidor.
- Conexão/leitura têm orçamento de quatro segundos após resolução DNS e corpo máximo de 128 KiB por requisição. A resolução DNS depende do sistema; coletas em segundo plano não param o display. Testes Pi-hole podem fazer três requisições; Home Assistant, até quatro.
- Pi-hole atualiza a cada 60 segundos por padrão (mínimo 30); Home Assistant, a cada 30 (mínimo 15). Após erro, o cache aguarda pelo menos 30 segundos antes de nova tentativa automática.
- Retirar ou substituir a credencial descarta o cache anterior; configurações migradas mantêm as novas páginas desativadas.

Armazenamento, transporte e recuperação estão em [Backup e credenciais](BACKUP_AND_CREDENTIALS.md).

## Outros displays

`dashboard/display_profiles.py` descreve resolução, modo de cor, rotação e driver. O ST7789 240×240 continua padrão e único módulo homologado. A v0.8.0 inclui drivers opcionais SSD1306/I2C e ILI9341/SPI, selecionados somente pelo ambiente do administrador, não pela configuração web. OLED tem layout nativo 128×64; ILI9341 centraliza o quadro RGB sem esticar. A simulação no painel não troca hardware nem abre barramentos. [Matriz e limites](DISPLAY_COMPATIBILITY.md).

## MQTT nativo (v0.8.0)

Página opcional para até quatro tópicos exatos, texto simples ou escalares JSON, nome/unidade e credencial privada vinculada ao broker. TLS verifica certificados; MQTT sem TLS exige consentimento explícito e permanece local/tailnet. A consulta do painel usa somente os ajustes aplicados. Sem mensagem aparece SEM DADOS; erro/cache/retido são identificados.

O conector não envia PUBLISH ou comandos: faz assinaturas curtas MQTT 3.1.1 / QoS 0, preferindo mensagens retidas. Não é escuta contínua/histórico de eventos e não calcula idade da medição. Não instala broker nem adiciona dependências obrigatórias. [Configuração, API e limites](MQTT_MONITOR.md); seus sensores reais/TFT continuam no checklist final.

Para habilitar um novo display é necessário:

1. implementar o driver físico;
2. marcar o perfil como disponível;
3. validar legibilidade dos layouts adaptados;
4. testar botões, rotação e frequência de atualização no hardware.

Provedores, autenticação, configuração, carrossel e painel web permanecem reutilizáveis.
