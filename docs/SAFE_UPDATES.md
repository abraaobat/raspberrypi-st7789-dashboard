# Atualização segura — v0.10.0

Ferramenta do **terminal do operador**, não API ou botão do painel. Separa preparação e ativação. Implementação e falhas têm testes simulados; troca/retorno reais ainda são gates finais. A instalação auditada continua v0.6.0.

| Etapa | Ação | Serviços ativos |
|---|---|---|
| `preflight` | Confere instalação padrão, código limpo, compatibilidade privada e saúde recente | Não altera |
| `prepare` | Extrai SHA escolhido, cria ambiente Python exclusivo, instala dependências nele, testa e guarda backup privado | Não altera |
| `activate … --confirm` | Pede autorização local, registra troca, para serviços, guarda backup recente e troca os dois arquivos de serviço | Pausa e inicia nova versão |
| Falha na ativação | Tenta retornar ao código/ambiente anteriores e verificar saúde | Não restaura configuração/cofre antigos |
| `rollback … --confirm` | Retorno explícito, se versão anterior entende dados atuais e serviços ainda pertencem àquela troca | Pausa e volta à versão anterior |

Checkout/ambiente anteriores não são atualizados. Nenhum pacote do sistema, grupo, broker, app ou driver extra é instalado. O ambiente novo é criado no caminho definitivo: ambientes virtuais contêm caminhos absolutos e não devem ser movidos. [Documentação Python](https://docs.python.org/3.11/library/venv.html).

## Montagens suportadas neste corte

- Linux/systemd, usuário normal, ST7789 padrão com SPI `/dev/spidev0.0` e painel na porta 8080.
- Dois serviços padrão em `/etc/systemd/system`, de root, sem drop-ins/personalizações; usuário/home/caminhos adaptados pelo instalador original são aceitos.
- Home/código próprios sem escrita por terceiros, espaços ou links simbólicos; estado privado `0700`, arquivos regulares privados.
- Configuração/cofre válidos; versão anterior/nova precisam compreender dados atuais sem perder campos.
- Dependências de sistema e acesso SPI/GPIO já autorizados. Pacote Python que exige biblioteca/ferramenta ausente pode impedir preparação, sem alterar a versão em execução.

Perfis experimentais, porta/binding modificados, migração de usuário e unidades personalizadas precisam de roteiro administrado próprio. A ferramenta recusa essas montagens, sem remover escolhas para forçar compatibilidade.

## 1. Obter ferramenta sem mexer no código em execução

No terminal **do Raspberry**, confirme checkout limpo. Se houver alterações próprias, preserve-as e não prossiga. Não faça `git pull` na pasta usada pelo serviço: alteraria arquivos do processo antes da preparação.

```bash
cd ~/raspberrypi-st7789-dashboard
git status --short
git fetch origin
git worktree add --detach ~/.cache/st7789-update-tool-v0.10.0 origin/main
cd ~/.cache/st7789-update-tool-v0.10.0
python3 -B scripts/update_dashboard.py preflight
```

Se a pasta separada já existir, não apague/force substituição. Use cópia válida já preparada ou nome exclusivo. `fetch` atualiza referências, não o checkout ativo.

## 2. Preparar revisão confiável

Veja SHA completo com `git rev-parse HEAD`, confira revisão e substitua marcador abaixo. Só SHA de 40 caracteres é aceito; não há busca automática da “última versão”. Instalar dependências/executar testes não é sandbox nem verificação de assinatura: use código confiável do projeto.

```bash
git rev-parse HEAD
python3 -B scripts/update_dashboard.py prepare --revision SHA_COMPLETO_ESCOLHIDO
python3 -B scripts/update_dashboard.py status
```

Pode levar minutos; requer rede/espaço para ambiente separado. Não solicita administrador nesta etapa. Só release `prepared` pode ser ativado. Guarde identificador impresso `release-…-…`.

Estrutura privada `~/.config/raspberrypi-st7789-updates/release-…/`:

```text
code/                  código extraído, fora do checkout ativo
venv/                  dependências exclusivas; nunca mover
before/ + after/       dois arquivos de serviço conhecidos
backup-preparation/    cópia privada anterior aos testes
backup-activation/     cópia privada com serviços parados, criada ao ativar
test-state/            destino isolado de estado padrão dos testes
packages.txt           inventário dos pacotes preparados
manifest.json          revisão, versões, integridade e fase da troca
```

Backups incluem PIN/cofre/chave de sessão: **não publique nem envie ao suporte**. Preparação copia arquivos individualmente, não é fotografia global instantânea com serviços ativos. Na ativação, backup é refeito após parar serviços, sem outros processos escrevendo no estado. Mudanças posteriores à preparação são reconferidas.

## 3. Ativar somente no teste final

Não precisa atualizar versão por versão. Na mesma cópia da ferramenta, substitua marcador pelo identificador realmente preparado:

```bash
python3 -B scripts/update_dashboard.py activate IDENTIFICADOR_DO_RELEASE --confirm
```

Senha somente no terminal, na solicitação de `sudo`. Antes de parar serviços, reconfere código/unidades/pacotes/compatibilidade e recusa preparação alterada/desatualizada. Não habilita grupos nem modifica exposição do painel.

Exige dois serviços ativos, SPI, API com **versão esperada** e quadro sem erro publicado **depois** do início e com menos de 30 s. API antiga respondendo 200 ou arquivo antigo não aprovam troca. Janela de conferência de aproximadamente um minuto; não homologa legibilidade/botões/serviços reais.

Atualize navegador e entre com mesmo PIN. Siga [FINAL_VALIDATION.md](FINAL_VALIDATION.md). `validate_install.sh` continua auditoria geral; gates de versão/frescura da troca são mais estritos.

## 4. Retorno e recuperação

```bash
python3 -B scripts/update_dashboard.py status
python3 -B scripts/update_dashboard.py rollback IDENTIFICADOR_DO_RELEASE --confirm
```

Retorna **código/ambiente/unidades**, não escolhas/segredos antigos. Configuração/cofre atuais precisam ser compreendidos pela versão anterior. V0.6.0 não entende entrada MQTT do cofre ou campos posteriores: após aplicar ajustes novos, retorno pode ser recusado. Isso exige migração local explícita, não descarte de dados.

Falha de saúde/instalação parcial tenta retorno automático e só informa sucesso após saúde da versão anterior. Incompatibilidade, código anterior modificado, autorização expirada ou falha de recuperação deixam `recovery-required`; preserve tudo e diagnostique localmente. Não há garantia de disponibilidade em falhas de disco/energia/dados incompatíveis.

Journal é salvo antes de parar serviços. Após interrupção, novas preparações/ativações ficam bloqueadas até recuperar release pendente. Retorno reconhece unidades anteriores/novas e combinações completas entre elas; não sobrescreve arquivos desconhecidos/truncados. Corrupção durante escrita exige reparo administrado conferido. Não interrompa/reinicie Pi deliberadamente para testar: cenários de software usam serviços fictícios.

`install.sh` agora recusa serviços existentes antes de alterar dependências. Não faça reset destrutivo, não restaure backup antigo por cima de credenciais recentes e não apague ambientes usados por serviços. Retenção/limpeza automática, releases assinadas e migrações de esquemas ficam para próximos cortes.
