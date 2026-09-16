# Continuidade do projeto

## Estado validado em 16/09/2026

- versão 0.3.0 implantada no Raspberry Pi 3 Model B V1.2;
- ST7789 240×240 SPI e navegação GPIO23/GPIO24 homologados;
- painel web, PIN, prévia, ordem e carrossel aprovados;
- páginas Clima e SysOps fotografadas e homologadas no display real;
- 24 testes automatizados aprovados no computador, no CI e no ARM;
- configuração e PIN anteriores preservados na atualização;
- landing page bilíngue publicada com fotos reais, sitemap/robots e contribuição opcional por Pix confirmado;
- publicação GitHub Pages e testes de CI concluídos com sucesso; acesso público HTTP 200.
- correção das fotos pretas e imagens esticadas na landing page: originais restaurados, QR Pix preservado e proporções conferidas no navegador em 1440/980/390/320 px, em português e inglês (simulação de tamanhos, não novo teste físico no celular).

## Primeiro gate manual restante

No painel, use **Adicionar fonte** para criar uma página HTTP/JSON de um app ou serviço que o usuário realmente queira acompanhar. Selecione um caminho como `sensor.value` ou `items.0.status`, teste a conexão, ative a página e confirme a leitura no TFT.

Não é necessário repetir os testes já aprovados de Clima e SysOps. Esse teste personalizado pode ser feito depois da implementação dos próximos conectores, desde que não seja registrado como homologado antes de sua execução real.

## Entregas adicionais da v0.4.0

- cofre local `0600`, separado de `config.json`, com bloqueio/atômico e vínculo ao endereço;
- assistentes Pi-hole 6 e Home Assistant, até quatro entidades, teste sem gravação;
- páginas PI-HOLE/CASA e cache com espera mínima após falhas;
- HTTP autenticado exige consentimento; DNS fixado por conexão, sem redirect/proxy, HTTPS validado;
- backup/restauração preservando PIN e credenciais;
- correção de reentrada no painel após criar PIN e fazer logout;
- 55 testes automatizados e fluxo completo no navegador em ambiente isolado com serviços fictícios;
- cenários reais ainda não homologados; nenhum endpoint/token do usuário foi solicitado ou inventado.

## Entregas adicionais da v0.5.0

- Relógio offline com hora/data, dia da semana, fuso IANA e formato 12/24 h;
- Pomodoro de 1–120 minutos, controlado pelo painel sem mudar a navegação dos botões;
- tempo monotônico e estado privado compartilhado: reiniciar serviço preserva o ciclo; reboot interrompe execução, sem estimativa falsa;
- configurações de mesa no backup, sem exportar o ciclo ativo nem reiniciá-lo ao restaurar;
- 84 testes automatizados no computador e navegador isolado com comandos, resposta antiga de atualização, reload/login, backup e layout em quatro tamanhos;
- prévias RELÓGIO/POMODORO verificadas no computador; teste físico e execução no ARM permanecem pendentes.

Veja [DESK_MODE.md](DESK_MODE.md) para o checklist de um ciclo curto e os limites implementados.

## Próximas implementações

1. Homologar Pi-hole 6/Home Assistant reais e as duas novas páginas no TFT quando o usuário puder configurar suas credenciais.
2. Homologar Relógio/Pomodoro no TFT com um ciclo de 1 minuto, pausa e retomada; não alterar os dois gestos físicos existentes.
3. MQTT/Node-RED em etapa independente e Docker detalhado.
4. Templates de integrações adicionais, mantendo contrato fechado e sem execução remota.
5. Drivers físicos adicionais e matriz de compatibilidade por módulo/resolução.

## Limites a preservar

- O display deve continuar operando sem o painel web e sem internet.
- Fontes personalizadas genéricas consultam somente HTTP/JSON, sem headers de autenticação arbitrários; os dois conectores guiados usam o cofre.
- Não adicionar endpoints de shell ou instalação arbitrária.
- SSD1306/ILI9341 continuam experimentais até existir driver e evidência física.
- O painel permanece restrito à rede local ou tailnet; a landing page pública não expõe a API do Raspberry Pi.

## Publicação e Google

O fluxo de GitHub Pages publica `site/`. A indexação no Google é uma etapa separada: verificar a propriedade no Search Console e enviar o sitemap não garante inclusão imediata nos resultados. Consulte [site/README.md](../site/README.md).

O Search Console exige login no navegador disponível. Essa é a única etapa de publicação que ficou para o mantenedor; a propriedade não foi registrada nem o sitemap enviado durante esta sessão.

## Roteiro manual curto

Abra o painel existente com o mesmo PIN. Em **Integrações guiadas**, configure o serviço desejado, teste, marque a ativação, guarde os ajustes e aplique. Depois confirme PI-HOLE/CASA com os botões. Nenhuma dessas etapas exige enviar credenciais nesta conversa. Veja [checklist e backup](BACKUP_AND_CREDENTIALS.md).

## Atualização do Raspberry Pi pendente nesta retomada

O Pi não respondeu por SSH nos IPs anteriormente conhecidos (`192.168.100.94` e `192.168.100.11`), inclusive na nova tentativa da v0.5.0. Não houve reinício, alteração do estado, cadastro de credenciais nem execução dos 84 testes no ARM nesta retomada. A v0.3.0 continua sendo a última implantação comprovada.

Quando a conexão voltar, execute no próprio Raspberry Pi:

```bash
cd ~/raspberrypi-st7789-dashboard
git status --short
git pull --ff-only
./scripts/install.sh
./scripts/validate_install.sh
```

Se o primeiro comando de status mostrar alterações próprias, não as descarte: preserve-as antes de atualizar. O instalador usa o usuário/caminhos existentes e executa os testes antes de reiniciar os serviços; ele também reconfere dependências. Guarde privadamente um backup do estado antes de atualizar. Os novos módulos entram desativados e o PIN existente não precisa ser recriado.
