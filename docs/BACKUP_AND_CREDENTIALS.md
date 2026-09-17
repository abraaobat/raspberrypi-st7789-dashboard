# Backup e credenciais — v0.5.0

## Backup pelo painel

**Baixar configuração** exporta os ajustes já aplicados, não o rascunho. Inclui páginas, ordem, carrossel, alertas, localização do clima, serviços, URLs de fontes personalizadas e endereços/entidades das integrações. Não inclui o PIN, a chave de sessão ou o arquivo do cofre.

O backup pode revelar localização e endereços do seu homelab. Não coloque tokens em URLs de fontes personalizadas e não publique o arquivo indiscriminadamente.

Relógio (fuso/formatos) e duração do próximo Pomodoro também são incluídos. O ciclo ativo, identificação de boot e prazo monotônico não são exportados. Restaurar a configuração preserva o ciclo local em andamento/pausado; mudar duração vale somente para o próximo ciclo. Um backup local completo pode conter `pomodoro.json`, mas seu ciclo em execução não é portável entre dispositivos/boots. Veja [modo de mesa](DESK_MODE.md).

**Restaurar configuração** pede confirmação e aceita JSON de até 64 KiB. O servidor valida tudo antes da substituição atômica; arquivo inválido é recusado sem substituir os ajustes válidos. Ao restaurar no mesmo Pi, PIN e cofre são preservados. Em outro Pi, cadastre o PIN e as credenciais separadamente. Uma credencial existente só será usada se o endereço do backup coincidir com o endereço ao qual ela foi vinculada.

## O que o cofre protege

`~/.config/raspberrypi-st7789-dashboard/credentials.json` pertence ao usuário do serviço e usa permissão `0600`; o diretório usa `0700`. Gravações têm bloqueio entre processos, arquivo temporário único e substituição atômica. Arquivos corrompidos, de outro proprietário, com permissão pública ou atalhos simbólicos são recusados, não sobrescritos silenciosamente.

Os segredos precisam ser legíveis pelo coletor: **não há criptografia de disco**, isolamento contra o próprio usuário `pi`, contra `root` nem contra comprometimento do computador. O painel permite guardar, substituir e apagar, mas não recuperar os valores. Eles não ficam em `config.json`, cookies, respostas ou revisões usadas no cache.

Guardar/remover tem efeito imediato, mesmo sem aplicar os ajustes. Cancelar o assistente descarta o texto digitado, mas não desfaz uma credencial já guardada pelo botão próprio. Apagar do cofre não revoga o token ou a senha no serviço de origem: faça essa revogação no Home Assistant/Pi-hole, se necessário.

## Transporte das credenciais

O consentimento HTTP no assistente refere-se à ligação **Pi → serviço monitorado**, não à ligação **navegador → painel**. O painel instalado usa HTTP local; só cadastre tokens em uma rede confiável ou através de transporte protegido. LAN não é sinônimo de criptografia. Para proteger a travessia da rede com SSH, no computador:

```bash
ssh -N -L 8081:127.0.0.1:8080 pi@192.168.100.94
```

Abra `http://127.0.0.1:8081` enquanto a conexão estiver ativa. Também é possível configurar HTTPS por reverse proxy confiável; não desative a validação de certificados no coletor. Tailnet ajuda a proteger o tráfego entre os dispositivos, mas a configuração precisa usar seu caminho efetivamente protegido.

## Atualização e rollback

Atualizações preservam o diretório de estado. Integrações novas permanecem opt-in e não exigem credenciais para o núcleo iniciar. Antes de atualizar, guarde uma cópia privada do diretório completo fora do Git; ela inclui segredos e deve continuar com acesso restrito. Não envie essa cópia ao suporte nem à página pública.

O backup pelo navegador serve para ajustes; o backup local completo serve para recuperação do dispositivo. Se precisar restaurar a versão anterior, pare os serviços, volte à revisão conhecida e recupere o estado a partir da cópia local validada. Não execute rollback destrutivo em um checkout com alterações próprias.

Na preparação da atualização v0.3.0 → v0.5.0 em 16/09/2026, foi criado no próprio Pi um backup completo com acesso privado, fora do Git. PIN, configuração e chave de sessão foram comparados sem exibir conteúdos e não mudaram. Os 84 testes rodaram em checkout separado, sem alterar a instalação ativa. O instalador ainda precisa ser executado no terminal com senha de administrador; veja [UPDATE_TO_V05.md](UPDATE_TO_V05.md). Se mudar a configuração antes dessa instalação, prepare outro backup privado.

## Checklist manual pendente

1. Pi-hole **6 real**: gerar senha de aplicativo, testar, ativar e comparar resumo do painel/display com a API local.
2. Home Assistant real: token de usuário adequado, selecionar até quatro entidades e confirmar unidades/estados; testar uma entidade indisponível sem tratá-la como desligada.
3. Confirmar legibilidade das páginas PI-HOLE/CASA no ST7789; o teste de navegador não substitui observação física.
4. Fonte HTTP/JSON de interesse real: criar pelo assistente e confirmar o texto no TFT.
5. Backup: exportar os ajustes, guardar privadamente e testar a restauração quando conveniente. O fluxo automatizado já cobre preservação do PIN e cofre em ambiente isolado.
6. Relógio/Pomodoro: verificar hora/fuso e concluir um ciclo de 1 minuto no TFT, com pausa/retomada pelo painel. Os botões permanecem anterior/próxima página.

Não é necessário repetir a homologação anterior de Status/Rede/Hardware/Clima/SysOps apenas para cadastrar os novos serviços.
