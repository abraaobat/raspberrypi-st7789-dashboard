# Concluir a atualização para v0.5.0

**Atualizações atuais:** siga [SAFE_UPDATES.md](SAFE_UPDATES.md). Comandos antigos abaixo são registros históricos, não instruções para repetir `git pull`/`install.sh` na instalação ativa.

**Atualização concluída:** API `0.5.0`, serviços, SPI e estado do display foram confirmados em 17/09/2026. Este roteiro é histórico; para os modelos da v0.6.0, veja [CUSTOM_TEMPLATES.md](CUSTOM_TEMPLATES.md). Observação visual das novas páginas continua pendente.

## Preparação concluída

Em 16/09/2026, o Raspberry respondeu por SSH. Os 84 testes da revisão `04fce39` passaram no ARM em uma cópia separada, e a instalação atual v0.3.0 passou na auditoria automática. Foi criado backup privado completo do estado; PIN, configuração e chave de sessão foram preservados. Não houve troca do código ativo nem reinício dos serviços.

A etapa restante precisa da senha de administrador no terminal. Não envie essa senha ou o PIN na conversa. Execute como `pi`, não como `root`.

## 1. Instalar no Raspberry

No computador, conecte ao Pi:

```bash
ssh pi@192.168.100.94
```

No terminal do Raspberry:

```bash
cd ~/raspberrypi-st7789-dashboard
git status --short
```

Se aparecerem alterações próprias, preserve-as antes de continuar. Se estiver limpo:

```bash
git pull --ff-only
./scripts/install.sh
./scripts/validate_install.sh
```

O instalador pedirá a senha de administrador quando necessário. Ele reconfere dependências, executa os testes e reinicia os dois serviços. Não use `sudo ./scripts/install.sh`: o script deve iniciar como usuário normal.

Se qualquer etapa falhar, não considere a atualização concluída. Guarde a mensagem do erro, sem expor segredos, e interrompa o roteiro antes de ativar os novos módulos.

## 2. Conferir a versão e abrir o painel

```bash
curl --fail --silent --show-error http://127.0.0.1:8080/api/health
```

A resposta precisa indicar `"version":"0.5.0"`; a auditoria precisa terminar com **Validação automática aprovada**. Se ainda indicar `0.3.0`, os processos antigos continuam ativos: não registre a v0.5.0 como implantada.

Abra `http://192.168.100.94:8080/` e atualize a página. Entre com o mesmo PIN; não é necessário recriá-lo. Os módulos novos começam desativados.

## 3. Enviar conteúdo para o display físico

Em **Conteúdo e ordem**, ative as páginas desejadas e clique em **Aplicar alterações**. Na prévia, selecione uma página e clique em **Mostrar esta página no display**. O carrossel usa somente páginas ativas; os botões físicos continuam anterior/próxima.

Para Relógio, escolha o fuso desejado (por exemplo, `America/Boa_Vista`) e aplique. Para Pomodoro, aplique uma duração de 1 minuto antes de iniciar o teste.

## 4. Testes manuais finais

- Conferir hora, data, fuso e legibilidade de RELÓGIO no TFT.
- Iniciar um Pomodoro de 1 minuto; pausar, retomar e observar a conclusão no TFT.
- Confirmar navegação pelos dois botões, sem alterar os gestos existentes.
- Criar uma fonte HTTP/JSON de interesse real e comparar o valor com o app monitorado.
- Se esses serviços existirem, configurar Pi-hole 6/Home Assistant no painel privado e comparar PI-HOLE/CASA com os dados reais.

Não é necessário repetir toda a homologação de Status/Rede/Hardware/Clima/SysOps. Conectores reais e leitura das novas páginas ainda não foram homologados. Search Console continua dependendo de login do mantenedor; MQTT, Docker detalhado e drivers adicionais são etapas futuras. Tetris foi cancelado.
