# Integrações, clima e páginas personalizadas

## Princípios

- integrações são opcionais e entram desativadas em instalações existentes;
- nenhuma consulta externa bloqueia o loop do display;
- o último valor válido permanece disponível quando uma fonte fica offline;
- a API nunca executa shell, código Python ou conteúdo recebido da fonte;
- configuração e URLs ficam no diretório privado do usuário, nunca no Git.

## Clima

No painel web:

1. preencha um nome curto para a localização;
2. informe latitude e longitude;
3. escolha a frequência entre 10 e 60 minutos;
4. ative a página **Clima** em **Conteúdo e ordem**;
5. aplique as alterações.

A consulta usa o endpoint de previsão do Open-Meteo e solicita condição atual, temperatura aparente, código WMO, mínima, máxima e probabilidade máxima de precipitação. O provedor funciona em segundo plano: a primeira renderização mostra carregamento e a seguinte usa o dado recebido. Em falhas posteriores, a tela mostra `CACHE` e conserva a última leitura válida.

O endpoint gratuito do Open-Meteo é apropriado para uso pessoal e não comercial, possui limites de uso e exige atribuição CC BY 4.0. Uso comercial requer um plano ou provedor compatível. Consulte a [documentação](https://open-meteo.com/en/docs) e os [termos oficiais](https://open-meteo.com/en/terms).

## SysOps local

A página **SysOps** combina:

- ocupação da partição raiz;
- gateway detectado pela rota padrão e seu ping;
- resultado de `vcgencmd get_throttled` quando disponível, traduzido em `OK`, `ALERTA` atual ou `HISTÓRICO`;
- até quatro serviços `systemd` definidos no painel.

Os nomes dos serviços aceitam apenas letras, números, `@`, `_`, `.`, `-` e sufixo opcional `.service`. O backend chama `systemctl is-active` com argumentos separados e nunca interpola shell.

## Fonte HTTP/JSON

Use **Adicionar fonte** para cadastrar:

- título e rótulo exibidos;
- URL HTTP ou HTTPS;
- caminho do valor principal;
- caminho secundário opcional;
- unidade, cor e layout.

Exemplo de resposta:

```json
{
  "sensor": {
    "power": 318,
    "unit": "W"
  }
}
```

Configuração correspondente:

```text
Valor principal: sensor.power
Valor secundário: sensor.unit
Unidade: W
Layout: Métrica
```

Listas usam índice numérico: `items.0.status`.

O botão **Testar conexão** consulta a fonte sem salvar. Depois de aprovada, a página entra ativa no final do carrossel e pode ser desativada ou reordenada como qualquer página nativa.

### Limites de segurança

- somente `GET` HTTP/HTTPS;
- timeout de quatro segundos;
- resposta máxima de 128 KiB;
- raiz obrigatoriamente objeto ou lista JSON;
- redirecionamentos bloqueados;
- endereços link-local, multicast, reservados e não especificados bloqueados;
- loopback e redes privadas permitidos intencionalmente para homelab;
- no máximo oito páginas personalizadas;
- texto final limitado antes da renderização;
- credenciais embutidas na URL são rejeitadas.

APIs que exigem token ainda não são suportadas pelo assistente. A fase seguinte usará um cofre local separado do `config.json`, sem devolver o segredo à interface.

## Outros displays

`dashboard/display_profiles.py` descreve resolução, modo de cor, rotação e driver. O ST7789 240×240 continua sendo o único driver físico habilitado, enquanto perfis experimentais para SSD1306 128×64 e ILI9341 320×240 validam a adaptação do framebuffer em testes.

Para habilitar um novo display é necessário:

1. implementar o driver físico;
2. marcar o perfil como disponível;
3. validar legibilidade dos layouts adaptados;
4. testar botões, rotação e frequência de atualização no hardware.

Provedores, autenticação, configuração, carrossel e painel web permanecem reutilizáveis.
