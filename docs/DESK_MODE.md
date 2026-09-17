# Relógio e Pomodoro — v0.5.0

Dois módulos opcionais, sem consulta à internet e desativados por padrão. Use o painel existente com o mesmo PIN; a navegação de GPIO23/GPIO24 continua sendo anterior/próxima página.

## Relógio

1. Ative **Relógio** em **Conteúdo e ordem**.
2. Em **Relógio e Pomodoro offline**, escolha mostrar segundos e formato de 24 horas.
3. Informe um fuso IANA, como `America/Boa_Vista`, ou deixe vazio para usar o fuso configurado no Raspberry Pi.
4. Aplique os ajustes e confira a prévia. A página mostra hora, data, dia da semana e fuso; atualiza a cada segundo enquanto selecionada.

A hora vem do sistema operacional. Não depende de uma API externa, mas precisa estar correta no Pi: sincronização do sistema ou relógio de hardware continuam sendo responsabilidade do dispositivo. O Raspberry Pi 3 de referência não passa a ter um RTC por causa deste módulo. Fusos nomeados usam a base `tzdata` do sistema; um nome ausente ou inválido é recusado sem substituir os ajustes aplicados. O formato de 12 horas mostra AM/PM.

## Pomodoro

1. Ative **Pomodoro** na lista se quiser vê-lo no display.
2. Escolha uma duração inteira entre 1 e 120 minutos (padrão: 25) e **aplique** os ajustes.
3. Use **Iniciar**, **Pausar**, **Retomar** ou **Reiniciar**. Esses controles têm efeito imediato, mesmo que a página esteja desativada.
4. Navegue até Pomodoro ou use **Mostrar esta página no display**. O carrossel não é interrompido automaticamente pelo cronômetro.

Alterar a duração não muda um ciclo em andamento ou pausado: vale para o próximo ciclo. **Reiniciar** descarta o ciclo atual, pede confirmação no navegador e volta ao estado pronto com a duração aplicada. Concluir um ciclo mostra `CICLO CONCLUÍDO`; outro só começa por ação explícita. Não há pausa automática de 5 minutos, som, notificação de IoT ou novo gesto nos botões físicos nesta versão.

O cronômetro utiliza tempo monotônico, não a hora civil. Ajustes de fuso, sincronização de hora e mudanças de data não encurtam ou prolongam o ciclo.

| Situação | Comportamento |
|---|---|
| Fechar o navegador ou sair do painel | O ciclo continua |
| Reiniciar os serviços web/display no mesmo boot | O ciclo continua; ambos leem o mesmo estado |
| Reiniciar o Pi com ciclo em execução | `PI REINICIADO` / `--:--`; inicie outro ciclo explicitamente |
| Reiniciar o Pi com ciclo pausado | Mantém o restante; **Retomar** é explícito |
| Restaurar um backup de configuração | Preserva o ciclo local; a nova duração vale para o próximo |

Não existe tentativa de adivinhar quanto tempo passou com o Pi desligado. Sem identificação confiável do boot, o início/retomada são recusados. Linux e macOS possuem identificação implementada; outras plataformas não têm suporte de execução persistente garantido.

## Estado e API

`pomodoro.json` e `.pomodoro.lock` ficam no diretório privado de estado, fora do Git, com permissão `0600`. Gravações de comandos usam bloqueio entre processos, arquivo temporário exclusivo e substituição atômica. A consulta calcula o restante sem regravar o cronômetro a cada segundo. Arquivo inválido, público ou link simbólico é recusado e preservado para recuperação local.

- `GET /api/pomodoro/state`: estado, duração do ciclo, segundos restantes e progresso; exige sessão.
- `POST /api/pomodoro/command`: somente `{"action":"start|pause|resume|reset"}`; exige sessão e CSRF. O servidor usa a duração aplicada, não valores enviados no comando.

O backup pelo painel inclui `clock` e `pomodoro.minutes`, não o ciclo ativo, sua identificação de boot ou prazo monotônico. Não copie `pomodoro.json` para outro dispositivo esperando retomar um ciclo em execução.

## Evidência e teste físico pendente

A v0.5.0 tem 84 testes automatizados aprovados no computador e no ARM do Raspberry em checkout separado, incluindo tempo injetado para conclusão/reboot, persistência entre processos, permissões, concorrência, configuração, API e renderização. O fluxo de navegador isolado cobre ativação, iniciar/pausar/retomar/reiniciar, proteção contra resposta antiga de atualização, recarregamento, login, restauração e layout em 1440/980/390/320 px. Serviços externos e credenciais desse teste são fictícios.

A instalação atual v0.6.0 foi confirmada no Raspberry em 17/09/2026, com auditoria automática aprovada. Faça um ciclo de 1 minuto no painel, confirme a contagem e o estado final no TFT, pause/retome e confira Relógio com os botões. Esses testes visuais foram adiados para o final pelo mantenedor e não foram registrados como homologados. Modelos v0.6.0 e Docker v0.7.0 não mudam o comportamento do timer; veja o [checklist final consolidado](FINAL_VALIDATION.md).
