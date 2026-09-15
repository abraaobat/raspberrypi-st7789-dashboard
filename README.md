# Raspberry Pi ST7789 Dashboard

Dashboard compacto para Raspberry Pi com display TFT ST7789 1.3" 240×240 via SPI e navegação por dois botões físicos.

![Raspberry Pi ST7789 Dashboard](docs/images/hero.jpg)

O projeto foi desenvolvido e validado em um **Raspberry Pi 3 Model B V1.2**, usando Raspberry Pi OS Lite 32-bit, e exibe informações de sistema em três páginas.

## Visão do produto

O projeto evoluirá de um monitor fixo de recursos para um **microdashboard modular, offline-first e controlado por dois botões**. O núcleo continuará leve e funcional sem internet, enquanto páginas opcionais poderão acrescentar monitoramento de homelab, relógio, Pomodoro, meteorologia e integrações de IoT.

Uma interface web responsiva está planejada para permitir que o usuário, pelo computador ou celular:

- escolha quais páginas e recursos aparecem no display;
- altere a ordem das páginas e o intervalo do carrossel;
- configure limites de alerta e integrações opcionais;
- visualize uma prévia fiel de 240×240 gerada pelo mesmo renderizador Pillow usado no ST7789;
- aplique mudanças sem editar o código-fonte.

O MVP físico descrito abaixo está validado. A interface web e os módulos adicionais ainda fazem parte do roadmap.

- [Roadmap do produto](ROADMAP.md)
- [Especificação do Web Control Panel](docs/WEB_CONTROL_PANEL.md)

## Recursos

### 1. STATUS

- uso de CPU
- temperatura do SoC
- uso de RAM
- uptime
- barras de progresso
- alertas visuais de temperatura

![Página Status](docs/images/status.jpg)

### 2. REDE

- hostname
- IPv4 da Ethernet
- IPv4 do Wi-Fi
- IPv4 do Tailscale, quando instalado

![Página Rede](docs/images/network.jpg)

### 3. HARDWARE

- modelo do Raspberry Pi
- versão do kernel
- quantidade de dispositivos USB
- estado da interface SPI

![Página Hardware](docs/images/hardware.jpg)

## Hardware usado

- Raspberry Pi 3 Model B V1.2
- display TFT ST7789 1.3" 240×240 SPI
- dois botões integrados ao módulo
- cartão microSD com Raspberry Pi OS

Display usado no protótipo:

https://pt.aliexpress.com/item/1005008209370173.html

> O anúncio pode mudar ou deixar de estar disponível. Confirme a pinagem do seu módulo antes de energizar o circuito.

## Pinagem validada

A configuração abaixo corresponde ao módulo usado neste projeto.

| Função | GPIO BCM |
|---|---:|
| SPI MOSI | GPIO10 |
| SPI SCLK | GPIO11 |
| SPI CS0 | GPIO8 |
| TFT DC | GPIO25 |
| TFT RESET | GPIO27 |
| Botão A | GPIO23 |
| Botão B | GPIO24 |

Os botões utilizam `PULL_UP`:

- solto: `ACTIVE`
- pressionado: `INACTIVE`

No dashboard:

- **GPIO23 / botão superior:** página anterior
- **GPIO24 / botão inferior:** próxima página

### Atenção ao GPIO24

Neste módulo o **GPIO24 é um botão**, portanto ele não deve ser usado como `backlight` no construtor do ST7789.

## Software testado

- Raspberry Pi OS Lite 32-bit
- Debian 13 / Trixie
- Python 3
- `st7789` 1.0.1
- Pillow 12.3.0
- spidev 3.8
- NumPy 2.5.3
- gpiod 2.5.0
- gpiodevice 0.1.0

## Instalação

### 1. Atualize o sistema

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip libopenblas0 fonts-dejavu-core usbutils
```

### 2. Habilite SPI

```bash
sudo raspi-config
```

Acesse:

`Interface Options -> SPI -> Enable`

Depois reinicie:

```bash
sudo reboot
```

Confirme:

```bash
ls /dev/spidev*
```

O esperado é encontrar pelo menos:

```text
/dev/spidev0.0
/dev/spidev0.1
```

### 3. Clone o repositório

```bash
git clone https://github.com/abraaobat/raspberrypi-st7789-dashboard.git
cd raspberrypi-st7789-dashboard
```

### 4. Crie o ambiente virtual

```bash
python3 -m venv ~/st7789-env
source ~/st7789-env/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Teste manualmente

```bash
python bench_display.py
```

O display deve abrir na página `STATUS`. Use os dois botões para navegar pelas três telas.

## Inicialização automática com systemd

Copie o serviço:

```bash
sudo cp systemd/bench-display.service /etc/systemd/system/bench-display.service
```

Se seu usuário não for `pi`, ajuste `User`, `WorkingDirectory` e `ExecStart` no arquivo antes de ativá-lo.

Ative o serviço:

```bash
sudo systemctl daemon-reload
sudo systemctl enable bench-display.service
sudo systemctl start bench-display.service
```

Verifique:

```bash
systemctl status bench-display.service --no-pager
```

O esperado é:

```text
Active: active (running)
```

Depois reinicie para testar o autostart:

```bash
sudo reboot
```

## Próximas evoluções

O próximo ciclo prioriza a confiabilidade do núcleo antes da interface web:

- detectar automaticamente a interface de rede ativa, sem depender de `wlan0` ou `wlan1`;
- ajustar, truncar ou quebrar textos que excedam os 240 pixels;
- representar falhas como `SEM DADOS`, sem confundi-las com valor zero;
- separar páginas, provedores de dados, botões e renderização em módulos testáveis;
- gerar screenshots de teste sem exigir o display físico;
- introduzir configuração persistente e prévia web antes das integrações externas.

## Comandos úteis

Reiniciar o dashboard:

```bash
sudo systemctl restart bench-display.service
```

Parar:

```bash
sudo systemctl stop bench-display.service
```

Logs em tempo real:

```bash
journalctl -u bench-display.service -f
```

Desabilitar o autostart:

```bash
sudo systemctl disable bench-display.service
```

## Solução de problemas

### Tela não acende ou não atualiza

Confirme se SPI está habilitado:

```bash
ls /dev/spidev0.0
```

E confira o serviço:

```bash
systemctl status bench-display.service --no-pager
```

### `libopenblas.so.0` ausente

Instale:

```bash
sudo apt install -y libopenblas0
```

### Botões não respondem

Este projeto foi validado com:

- GPIO23 = botão A
- GPIO24 = botão B
- entrada com `PULL_UP`
- pressionado = nível baixo / `Value.INACTIVE`

Módulos visualmente semelhantes podem usar pinagens diferentes.

### Tailscale mostra `-`

Isso é normal quando o Tailscale não está instalado, não está conectado ou não possui IPv4 ativo.

## Fotos da montagem

![Visão geral](docs/images/overview.jpg)

## Estrutura

```text
.
├── bench_display.py
├── requirements.txt
├── LICENSE
├── README.md
├── ROADMAP.md
├── project-status.json
├── systemd/
│   └── bench-display.service
└── docs/
    ├── WEB_CONTROL_PANEL.md
    └── images/
        ├── hero.jpg
        ├── status.jpg
        ├── network.jpg
        ├── hardware.jpg
        └── overview.jpg
```

## Licença

MIT License. Consulte [LICENSE](LICENSE).
