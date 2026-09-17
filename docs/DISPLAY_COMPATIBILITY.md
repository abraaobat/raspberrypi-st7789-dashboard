# Outros displays — v0.8.0

O ST7789 atual continua sendo o padrão. A v0.8.0 entrega drivers físicos opcionais para dois módulos adicionais e simulação de layout no painel. **Driver implementado/testado em software não significa módulo físico homologado.** Nenhum hardware, pacote opcional ou unidade do Raspberry existente foi alterado para esta entrega.

| Perfil | Renderização | Driver / barramento | Evidência física |
|---|---|---|---|
| `st7789-240x240` | 240×240 RGB canônico | st7789 / SPI0 CS0, DC25, RST27, 40 MHz | Raspberry Pi 3 + módulo original homologados |
| `ssd1306-128x64` | 128×64 monocromático nativo, até quatro linhas | luma.oled / I2C1, endereço 0x3C | Experimental; módulo ainda não testado |
| `ili9341-320x240` | 240×240 RGB centralizado em 320×240, sem esticar | luma.lcd / SPI0 CS0, DC25, RST27, 16 MHz | Experimental; módulo ainda não testado |

O OLED não usa uma miniatura ilegível do ST7789: recebe resumos próprios de Status/Rede/Hardware/SysOps/Clima/Pi-hole/Casa/Docker/MQTT/fontes personalizadas e layouts de Relógio/Pomodoro. Texto é abreviado para caber; status de temperatura tem palavras **ALERTA/CRIT**, pois não há cores. Casa indisponível continua SEM DADOS, e MQTT/cache não passam a ser leitura confirmada. O ILI9341 mantém a arte canônica com margens laterais; ocupar toda a largura com novo design fica para uma evolução posterior.

## Simulação segura pelo painel

Em **Prévia ao vivo → Visualização do display**, escolha uma simulação. Ela gera PNG no tamanho/modo correspondente, sem abrir SPI/I2C/GPIO, trocar configuração física ou reiniciar serviço. A proporção é preservada. **Mostrar esta página no display** envia somente a seleção da página ao hardware já configurado, nunca o perfil simulado.

API autenticada: `GET /api/preview?page=status&profile=ssd1306-128x64` (ou ILI9341). Perfil desconhecido é rejeitado. Sem `profile`, a prévia usa o perfil físico definido pelo administrador. O catálogo distingue `previewAvailable`, `driverImplemented` e `hardwareValidated`; o campo legado `available` continua reservado ao perfil homologado selecionável pela configuração web.

## Ativação física — somente com o módulo correto

Não execute este roteiro na montagem ST7789 atual só para simular. Não conecte dois displays ao mesmo chip select. Confira datasheet, alimentação e pinagem exata: GPIO do Pi não tolera 5 V; módulos aparentemente iguais podem ter reguladores, backlight, endereço ou orientação diferentes.

1. Prepare uma montagem compatível e confira acesso de usuário normal ao barramento necessário. I2C/novos grupos, quando necessários, são decisões do administrador; o dashboard não concede isso automaticamente.
2. No ambiente Python do host experimental, instale os extras opcionais:

   ```bash
   ~/st7789-env/bin/python -m pip install -r requirements-displays.txt
   ```

3. Escolha o perfil no ambiente de **ambos** os serviços com um drop-in administrado via `sudo systemctl edit bench-display.service` e `sudo systemctl edit bench-display-web.service`, preservando os campos existentes:

   ```ini
   [Service]
   Environment=ST7789_DISPLAY_PROFILE=ssd1306-128x64
   ```

   Para ILI9341, use `ili9341-320x240`. A seleção não vem do navegador/backup JSON. Perfil inválido ou dependência ausente produz erro explícito, não fallback silencioso para outro barramento.
4. Reinicie os dois serviços apenas quando a montagem estiver pronta. Teste prévia nativa, orientação, contraste/cores, texto e navegação/carrossel. GPIO23/GPIO24 continuam anterior/próxima; módulos sem botões exigem dois botões externos compatíveis ou navegação pelo painel/carrossel.
5. Para voltar ao ST7789, restaure a montagem original e remova **somente** a linha de seleção experimental dos dois drop-ins (não apague outras personalizações). Reinicie os dois serviços quando seguro.

Imports de drivers são tardios, só no entry point físico. Encerramento libera GPIO e chama limpeza do driver quando disponível; falha na inicialização de um driver opcional libera a interface serial criada. Luma/stack GPIO e versões/placas fora do módulo de referência ainda exigem homologação: não se anuncia compatibilidade automática com Raspberry Pi 5 ou qualquer variante SSD1306/ILI9341.

O instalador padrão segue exclusivo da montagem homologada ST7789; não instala Luma, não muda perfil e não concede acesso a I2C. `validate_install.sh` audita SPI/ST7789 e não é auditoria completa do OLED. Nenhuma integração externa é obrigatória para renderizar essas páginas.

Referências primárias: [Luma.OLED — SSD1306](https://luma-oled.readthedocs.io/en/stable/api-documentation.html), [Luma.LCD — ILI9341](https://luma-lcd.readthedocs.io/en/latest/api-documentation.html), [interfaces I2C/SPI — Luma.Core](https://luma-core.readthedocs.io/en/latest/interface.html).
