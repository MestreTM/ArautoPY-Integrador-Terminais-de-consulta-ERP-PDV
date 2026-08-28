# Redesign do painel web — ArautoPY

Barra lateral no lugar do cabeçalho, tema escuro/claro e um padrão visual único
para todas as páginas. **Nada de backend foi alterado**: rotas, ids, classes e
contexto Jinja (`pagina`, `versao`, `loja`, `abas_plugins`) continuam os mesmos.

## Como instalar

Copie os arquivos por cima do projeto, mantendo os caminhos:

```
arauto/web/templates/base.html          (substitui)
arauto/web/templates/plugins.html       (substitui)
arauto/web/static/css/admin.css         (substitui)
arauto/web/static/js/ui.js              (novo)
```

Guarde uma cópia do `admin.css` e do `base.html` atuais antes de sobrescrever.
Depois basta recarregar o painel (`Ctrl+F5`) — nenhum passo de build.

## O que mudou

- **Barra lateral** com grupos (Operação · Configuração · Extensões · Plugins
  ativos), recolhível para faixa de ícones; o estado fica salvo em
  `localStorage` (`arauto.sidebar`) e `Ctrl+B` alterna. Em telas até 860 px ela
  vira gaveta com botão de menu no topo.
- **Tema escuro + claro** pelo botão no pé da barra, salvo em `arauto.tema` e
  aplicado antes da pintura (sem piscada). Todas as cores saem de variáveis:
  `--bg`, `--superficie`, `--texto`, `--texto-2`, `--texto-3`, `--borda`,
  `--acento`, `--ok`, `--alerta`, `--erro`. Os nomes que os scripts já usavam
  (`--texto-2`, `--ok`, `--alerta`) foram mantidos.
- **Barra superior** enxuta: trilha `loja / página` e versão instalada.
- **Padrão único de página**: cartões, títulos, campos, tabelas, consoles,
  interruptores e botões com a mesma régua em Painel, Configuração, Layout,
  Diagnóstico, Plugins e Documentação — inclusive nas páginas servidas por
  plugins, que herdam o `base.html`.
- **Plugins**: o checkbox "Atualizar se já existir" saiu da interface. Atualizar
  a versão existente passou a ser o padrão — o campo `#plugin-atualizar`
  continua no DOM, `hidden` e `checked`, para o `plugins.js` atual seguir
  funcionando sem alteração. Se preferir remover o campo de vez, fixe
  `atualizar=true` na chamada de `/api/plugins/instalar` dentro do
  `plugins.js`.

## Detalhes de compatibilidade

- Todas as classes dos templates e dos scripts continuam estilizadas: `cartao`,
  `grade`, `botao`/`--claro`/`--fantasma`/`--mini`, `campo`/`campos`,
  `interruptor`+`trilho`, `tabela`/`tabela-rolagem`, `console`, `evento`+`ev-*`,
  `pastilha`, `subabas`/`subaba`, `config-*`, `badge-img--ok/warn/no`,
  `plugin-card`, `plugin-modal-*`, `modal-sql-*`, `sql-*`, `update-*`,
  `regua`/`legenda`/`prontas`/`sim-saida`, `markdown-body`, `aviso`,
  `toast-download-*`.
- As classes antigas `cabeca`/`abas`/`aba` seguem definidas (o cabeçalho fica
  oculto) para não quebrar HTML de plugins que as use.
- Fonte: Inter (uma família só). Códigos, logs e caminhos usam a mono do
  sistema — nada é baixado além da Inter.
- `layout.js` posiciona os elementos da simulação por estilo inline; o novo CSS
  só cuida da moldura (`.tela-moldura`, `.tela`), então o arrasto continua igual.
  Se algum elemento do editor de layout aparecer sem cor, me diga qual classe
  ele usa (o `layout.js` não veio no envio) que eu ajusto.

## Não incluído de propósito

`comum.js`, `painel.js`, `layout.js`, `logs.js`, `diagnostico.js` e
`plugins_docs.js` não vieram no envio e **não foram tocados** — o painel
continua usando os seus. Os demais templates (`painel.html`, `config.html`,
`layout.html`, `diagnostico.html`, `logs.html`, `monitor.html`,
`plugins_docs.html`, `plugin_host.html`) também não precisaram de mudança:
herdam o novo `base.html`.
