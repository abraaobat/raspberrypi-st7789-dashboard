# Deploy e homologação no Raspberry Pi

Este roteiro instala o display físico e o Web Control Panel como serviços independentes. O instalador detecta o usuário, a home e o caminho real do clone; não depende de `/home/pi`.

## 1. Atualizar o clone no Raspberry Pi

```bash
cd ~/raspberrypi-st7789-dashboard
git pull --ff-only
```

## 2. Instalar

Execute como usuário normal, não com `sudo`:

```bash
./scripts/install.sh
```

O instalador:

- instala os pacotes do sistema necessários;
- cria ou atualiza `~/st7789-env`;
- instala as dependências Python;
- executa os testes que não exigem hardware;
- cria o diretório privado de configuração;
- adapta os serviços ao usuário e ao caminho do clone;
- habilita e inicia o display e o painel web.

## 3. Abrir o painel

Use o endereço mostrado pelo instalador:

```text
http://IP-DO-RASPBERRY:8080
```

No primeiro acesso, crie o PIN local. Depois:

1. altere a ordem das páginas;
2. ative o carrossel;
3. ajuste o intervalo;
4. salve;
5. use **Mostrar esta página no display**.

Na versão 0.3, as páginas novas permanecem desativadas após a atualização. Configure localização, serviços ou fontes em **Integrações**, ative as páginas desejadas e só então aplique as alterações.

## 4. Validar automaticamente

```bash
./scripts/validate_install.sh
```

O resultado esperado é `PASS` para SPI, os dois serviços, a API e o estado publicado pelo display.

## 5. Homologar fisicamente

- GPIO23 abre a página anterior;
- GPIO24 abre a próxima página;
- a página escolhida no navegador aparece no ST7789;
- alterações de ordem e carrossel entram em vigor sem reiniciar;
- o painel continua acessível pelo celular;
- após `sudo reboot`, os dois serviços voltam a `active (running)`.

## Diagnóstico

```bash
systemctl status bench-display.service --no-pager
systemctl status bench-display-web.service --no-pager
journalctl -u bench-display.service -n 50 --no-pager
journalctl -u bench-display-web.service -n 50 --no-pager
```

Se o usuário do Raspberry Pi mudar, execute novamente `./scripts/install.sh`; ele regenera os serviços sem apagar o PIN ou a configuração.

## Homologação registrada

O fluxo completo foi aprovado no Raspberry Pi 3 com a versão 0.2.0:

- SPI e os dois serviços ativos;
- API e estado do display sem erros;
- GPIO23/GPIO24 navegando corretamente;
- painel e prévia ao vivo acessíveis;
- carrossel automático funcionando;
- ativação e ordem do conteúdo aplicadas no display.

Na versão 0.3.0, já foram confirmados no hardware:

- legibilidade e dados da página Clima;
- disco, gateway, histórico de alimentação e serviços na página SysOps;
- navegação até as páginas 4/5 e 5/5 no ST7789;
- preservação da configuração e do PIN durante a atualização;
- serviços, API, carrossel, ordem e botões físicos sem regressão.

Estado em 16/09/2026: versão 0.3.0 implantada e homologada visualmente no Raspberry Pi 3, com 24 testes aprovados no ARM, serviços/API saudáveis e configuração anterior preservada. Clima e SysOps foram fotografados no ST7789 real. Resta como teste físico opcional da próxima etapa exibir uma fonte HTTP/JSON criada pelo usuário.
