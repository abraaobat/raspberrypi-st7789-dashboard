# Checklist final — sem bloquear as próximas implementações

O mantenedor optou por adiar os testes manuais. Este documento reúne os gates restantes; nenhum item abaixo está marcado como homologado antes da observação real. Não é necessário repetir toda a homologação de Clima/SysOps: apenas reconferir rapidamente a navegação após a atualização.

## 1. Uma atualização, quando for conveniente

Use a versão mais recente publicada, que já inclui as anteriores. Confira checkout limpo e faça backup privado recente do diretório de estado, sem enviar PIN/cofre à conversa. Execute `scripts/install.sh` e depois `scripts/validate_install.sh` no terminal do Raspberry. A senha de administrador, se solicitada, fica somente no terminal. Atualize o navegador e entre com o mesmo PIN.

A auditoria de 17/09/2026 confirmou v0.6.0 ativa e saudável. A v0.8.0 já inclui Docker e as entregas anteriores; não houve instalação da atualização nos serviços ativos durante o desenvolvimento. A instalação pode ser agrupada com outras entregas, sem atualizar versão por versão. Para manter o ST7789 atual, não instale extras Luma nem defina perfil experimental. [Testes ARM/CI e backup preparados](NEXT_SESSION.md).

## 2. Novos recursos, só os que pretende usar

| Recurso | Teste manual curto | Resultado esperado |
|---|---|---|
| Fonte HTTP/JSON | Escolher modelo, conferir exemplo, testar uma URL de leitura real, guardar/aplicar e selecionar | Valor principal/detalhe legíveis na prévia e no TFT; editar/cancelar não aplica mudanças |
| Relógio | Escolher fuso e 12/24 h; ativar e selecionar | Hora/data coerentes com o relógio do Pi e inteiras na tela |
| Pomodoro | Aplicar duração de um minuto; iniciar, pausar, retomar e esperar concluir | Mesmo estado no painel/TFT, conclusão correta; sem mudança dos dois botões |
| Pi-hole 6 | Configurar endereço/senha de aplicativo no painel privado; testar/ativar/aplicar | Resumo coerente com a API real e legível; sem controle do DNS |
| Casa | Configurar endereço/token e até quatro entidades no painel privado | Estados/unidades correspondem ao Home Assistant; indisponível não vira desligado |
| Docker, opcional | Só em host com daemon/acesso já autorizados: filtros reais e comparação com a lista do Engine | Contagens do filtro, nomes ausentes e saúde coerentes; sem healthcheck mostra RODANDO, não SAUDÁVEL |
| MQTT, opcional | Usar broker já existente, conta de leitura e tópicos retidos reais; guardar credencial/aplicar/selecionar | Valores/unidades coerentes na prévia/TFT; RETIDO não implica medição recente; ausência não vira desligado |
| Simulação de display | Selecionar OLED/ILI9341 na prévia e voltar ao perfil físico | Imagem nativa sem esticar; hardware/configuração não mudam; botão envia somente a página |
| Outros displays físicos | Somente em montagem própria compatível, seguir a matriz de ativação do administrador | Orientação/texto/contraste/cores e navegação conferidos no módulo real; permanece experimental até registro |

Não cadastre URLs ou credenciais fictícias de teste como se fossem seus serviços reais. Não é necessário instalar Docker, Pi-hole, Home Assistant ou Node-RED apenas para homologar o display. Use os módulos de interesse que já possui.

MQTT não é coleta contínua de eventos: mensagens transitórias entre duas assinaturas podem não ser recebidas. Não o use como teste de alarmes de segurança. Drivers extras não devem ser habilitados na montagem ST7789 só para testar simulação. Consulte [MQTT](MQTT_MONITOR.md) e [compatibilidade](DISPLAY_COMPATIBILITY.md).

## 3. Regressão curta

- GPIO23 e GPIO24 continuam anterior/próxima.
- Uma página desativada não entra no carrossel; a ordem escolhida é preservada.
- **Mostrar esta página no display** seleciona a página aplicada no TFT.
- Carrossel alterna no intervalo escolhido e retoma após a pausa por interação física.
- Prévia tem os mesmos valores/layout do TFT, ressalvada a diferença de instante da coleta.
- Recarregar o painel mantém ajustes e PIN; backup/restauração preserva cofre e ciclo de Pomodoro.

## 4. Falhas sem ações destrutivas

Se uma fonte ficar naturalmente indisponível, observe a indicação de cache/sem dados. Não desligue serviços importantes, derrube a rede, altere permissões do socket nem reinicie o Pi só para testar. Timeout, reboot, respostas inválidas e concorrência já possuem cenários automatizados com ambiente/tempo simulados; reinicialização física continua não homologada.

No Pi auditado, o socket Docker padrão não existe: **SEM DADOS / socket não encontrado** é o resultado correto até existir um daemon autorizado. Não é uma falha das demais páginas. Acesso ao Docker pode equivaler a administrador; o dashboard não deve ganhar privilégios automaticamente.

Registre versão/data e quais módulos realmente observou no TFT. Falha em um módulo opcional deve ser tratada nele; não invalida os gates já homologados do MVP. Consulte [continuidade](NEXT_SESSION.md), [modelos](CUSTOM_TEMPLATES.md), [Desk](DESK_MODE.md), [credenciais](BACKUP_AND_CREDENTIALS.md) e [Docker](DOCKER_MONITOR.md).
