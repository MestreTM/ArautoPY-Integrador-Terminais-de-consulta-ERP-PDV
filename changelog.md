# Changelog — ArautoPY

---

## [1.1.0] — 2026-08-25

### Redesign do painel web

- **Barra lateral moderna** no lugar do cabeçalho de abas (grupos Operação · Configuração · Extensões · Plugins ativos)
- Barra recolhível (Ctrl+B), estado em `localStorage`; em telas ≤860px vira gaveta
- **Tema escuro e claro** com tokens CSS (`--bg`, `--superficie`, `--texto`, `--acento`, …)
- Fonte única Inter; classes legadas (`cartao`, `botao`, `interruptor`, `console`, …) mantidas
- Página Plugins: atualizar versão existente é o padrão (checkbox oculto)
- Compatibilidade: aliases `--fundo-2`, `--ink-2`, `--ink-3`, `--line` para plugins de exemplo
- Scripts de casca: `ui.js` (tema/sidebar) + `comum.js` (`window.TC`)
- Ajustes de altura nos plugins de cartaz/propagandas para o novo chrome

---

## [1.0.0] — 2026-08-19

Primeira linha estável pública do ArautoPY (evolução do antigo TCPY / tcserver-py).

### Protocolos e terminais

- Servidor **SC504** (TC-506 Mídia e variantes) com enquadramento B-H-I-LE
- Servidor **SC501** / Busca Preço G2 (porta 6500), handshake `#live` e consulta textual
- Modo **passivo** para SC501 e SC504 (debug / proxy)
- Depuração de protocolo com dumps hex
- Layout visual editável para o terminal (posições, fontes, cores padrão)
- Guias de alinhamento (centro e bordas) e handles nos quatro cantos dos elementos
- Imagens de produto no TC-506 Mídia (envio após o texto, payload otimizado)
- Suporte a cartão de memória / caminhos de mídia no aparelho
- Sem envio de imagem em consulta para dispositivos identificados como **TC-406 / TC406**

### Base de produtos

- Modos **arquivo texto**, base interna e **SQL externo** (SQLAlchemy)
- Conexão **Firebird** (`firebird+firebird://…`, charset WIN1252, client library)
- Preset **DBWare** (colunas `CODIGO_BARRA`, `DESCRICAO`, `PRC_VENDA`)
- Mapeamento assistido de tabelas e colunas (buscar tabelas, selecionar campos)
- Teste de conexão em tempo real antes de salvar
- Recarga periódica da base (padrão 1 minuto)
- Aplicação a quente de alterações de base/terminais sem reiniciar o processo inteiro

### Imagens de produto

- Banco local de imagens `{ean13}.jpg` (zeros à esquerda)
- Download do pacote no GitHub (`Prod-EAN-Imagens`) com barra de progresso
- Fallback **Bluesoft Cosmos** com redimensionamento via Pillow
- Ferramentas: limpar banco, apagar por EAN, baixar/atualizar pacote sem apagar o restante

### Painel web

- Abas: **Painel · Configuração · Layout · Logs/Monitor · Plugins**
- Cabeçalho universal (`base.html`) compartilhado com páginas de plugins
- Configuração com barra lateral de seções
- Consulta web otimizada para leitores 2D (sem teclado virtual)
- Autenticação com senha (padrão `admin`, troca no primeiro acesso)
- **Inicialização com o sistema** (Windows: registro HKCU + pasta Startup; Linux: XDG autostart)
- Ícone na bandeja e notificação (versão com `--tray` / compilada)
- Scripts `run.bat` e `run_venv.bat` com instalação automática de dependências

### Sistema de plugins

- Carregamento dinâmico, habilitação/desabilitação e instalação por ZIP (arrastar ou selecionar)
- Plugins **padrão** protegidos: só desativar, não desinstalar
- Sincronização automática do código dos plugins padrão na subida
- Documentação em Markdown com leitor formatado e busca
- Reinício de módulos de plugin sem reiniciar o servidor inteiro
- Modal de confirmação ao atualizar plugin já instalado

### Plugins incluídos

| Plugin | Descrição |
|--------|-----------|
| **Gerenciador de mídia TC-506M** | Lista, envia, visualiza, apaga mídias e monta playlist de propaganda / sensor de presença |
| **Explorador de banco** | Navega tabelas do `DB_URL` (Firebird e outros), filtra, edita e exclui com confirmação dupla |

### Atualização

- Verificação e download a partir do repositório oficial no GitHub
- Seção **Atualizações** no painel (última da configuração)
- Changelog remoto exibido com o mesmo leitor Markdown da documentação de plugins

### Outros

- Projeto renomeado de TCPY para **ArautoPY**
- Banco de dados de aplicação `arauto.db`
- Cores de layout alinhadas à tabela de referência do projeto
- Logs e monitor unificados em uma aba com alternância

---

## Próximos passos (não versionados)

Sugestões em aberto — podem entrar em releases futuras:

- Publicar assets `ArautoPY.zip` em cada tag de release
- Ampliar presets de ERP além do DBWare
- Mais plugins de integração (outros terminais, ferramentas de depuração)

---

Repositório: [MestreTM/ArautoPY---Integrador-Terminais-de-consulta-ERP-PDV](https://github.com/MestreTM/ArautoPY---Integrador-Terminais-de-consulta-ERP-PDV)

