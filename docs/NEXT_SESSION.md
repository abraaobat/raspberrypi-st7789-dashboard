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
- prévias RELÓGIO/POMODORO verificadas no computador; 84 testes aprovados também no ARM em cópia separada; observação das novas páginas no TFT permanece pendente.

Veja [DESK_MODE.md](DESK_MODE.md) para o checklist de um ciclo curto e os limites implementados.

## Retomada em 17/09/2026

A instalação v0.5.0 foi confirmada no Raspberry: checkout limpo `54bef83`, API `0.5.0`, dois serviços ativos, SPI disponível e estado do display sem erro. O usuário informou sucesso na atualização. Isso comprova implantação/saúde automática, não observação visual de PI-HOLE/CASA/RELÓGIO/POMODORO.

## Entregas adicionais da v0.6.0

- seis modelos para fontes HTTP/JSON: Métrica, Status, Temperatura, Energia, Node-RED e Item de uma lista;
- exemplos fictícios sem URLs/segredos/scripts, com aplicação explícita e preservação de URL/identificação ao editar;
- conferência de campos em JSON fornecido pelo usuário, sem consulta à fonte nem gravação, com sessão/CSRF, limite de 32 KiB e retorno somente dos escalares selecionados;
- confirmação antes de substituir campos, rascunho separado de aplicação e descarte do exemplo ao fechar;
- respostas antigas de testes descartadas após edição/fechamento;
- status desconhecidos/null neutros e detalhe visível no layout Status;
- 100 testes de software e fluxo de navegador com serviços fictícios; sem novas dependências nem mudanças de botões/driver.

Veja [CUSTOM_TEMPLATES.md](CUSTOM_TEMPLATES.md) para modelos, Node-RED via GET/JSON, limites e atualização da biblioteca. MQTT nativo não foi implementado por esse modelo.

## Próximas implementações

1. Homologar Pi-hole 6/Home Assistant reais e as duas novas páginas no TFT quando o usuário puder configurar suas credenciais.
2. Homologar Relógio/Pomodoro no TFT com um ciclo de 1 minuto, pausa e retomada; não alterar os dois gestos físicos existentes.
3. MQTT nativo em etapa independente e Docker detalhado; Node-RED via GET/JSON já tem modelo/roteiro, com teste real pendente.
4. Contratos específicos de outros apps, além dos seis modelos genéricos, mantendo contrato fechado e sem execução remota.
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

## Histórico da preparação v0.3.0 → v0.5.0

Em 16/09/2026, o Pi respondeu por SSH nos dois IPs conhecidos (`192.168.100.94` e `192.168.100.11`). A instalação ativa está limpa na revisão `6618be8`, a API responde `0.3.0`, os dois serviços estão ativos e a auditoria de SPI/estado/API foi aprovada.

Foi criada uma cópia privada completa do estado, fora do Git, com diretório `0700`. PIN, configuração e chave de sessão foram comparados sem exibir seus conteúdos e permaneceram intactos após os testes. A cópia usa o prefixo `~/.config/raspberrypi-st7789-dashboard.backup-v0.3-before-v0.5-`.

A revisão v0.5.0 `04fce39` foi preparada em `~/.cache/st7789-dashboard-update-v0.5.0`, como checkout separado. Os 84 testes passaram no ARM. Dependências e unidades de serviço não mudaram entre as duas revisões, e o ambiente Python não apresenta dependências quebradas. Esses resultados não representam implantação da v0.5.0 nem homologação visual no TFT.

Naquela preparação, o Raspberry exigiu senha para `sudo`; não houve alteração do checkout ativo, reinício dos serviços, cadastro de credenciais ou tentativa de contornar essa exigência. A instalação v0.5.0 foi concluída depois pelo usuário e confirmada nesta retomada.

## Instalar a biblioteca v0.6.0

O instalador continua exigindo senha de administrador no terminal, quando necessária. Como usuário `pi`:

```bash
cd ~/raspberrypi-st7789-dashboard
git status --short
git pull --ff-only
./scripts/install.sh
./scripts/validate_install.sh
```

Se o comando de status mostrar alterações próprias, não as descarte: preserve-as antes de atualizar. Informe a senha somente no terminal quando `sudo` pedir, nunca nesta conversa. O instalador usa o usuário/caminhos existentes e executa os testes antes de reiniciar os serviços; ele também reconfere dependências. O backup privado já foi preparado nesta retomada; se houver novos ajustes antes da instalação, faça outra cópia. Os novos módulos entram desativados e o PIN existente não precisa ser recriado.

Confira API com versão `0.6.0`, atualize o navegador e use o mesmo PIN. Veja [CUSTOM_TEMPLATES.md](CUSTOM_TEMPLATES.md) para criar uma fonte com exemplo, aplicar e conferir no TFT. Tetris foi cancelado e não foi implementado.
