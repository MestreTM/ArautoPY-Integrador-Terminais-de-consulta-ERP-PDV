# ArautoPY — Servidor de integração de terminais de consulta

![imagem](https://i.imgur.com/QBTOUz6.png)

Servidor de integração para **terminais de consulta de preço** e automação de varejo (Atualmente compativel com modelos Gertec).
Recriação em Python do Gertec TC Server, com painel web, API REST, plugins e suporte a base externa (incluindo Firebird / DBWare).

> **⚠️ Aviso Importante:** Caso tenha um terminal Tanca, Elgin, Bematech, Honeywell, Zebra, etc., entre em contato. podemos integra-lo ao sistema! 

## Modelos compatíveis

| Marca | Modelo | Protocolo | Status |
|---|---|---|---|
| Gertec | **TC-506 Mídia** | SC504 (16510) | ✅ TESTADO E FUNCIONANDO |
| Gertec | **Busca Preço G2** | SC501 (6500) | ✅ TESTADO E FUNCIONANDO |
| Gertec | TC-406 | SC501 (6500) | ⚠️ COMPATÍVEL — SEM TESTES |
| Gertec | TC-502 | SC501 (6500) | ⚠️ COMPATÍVEL — SEM TESTES |
| Gertec | TC-505 | SC501 (6500) | ⚠️ COMPATÍVEL — SEM TESTES |
| Gertec | TC-507 | SC501 (6500) | ⚠️ COMPATÍVEL — SEM TESTES |
| Gertec | TC-504 | SC504 (16510) | ⚠️ COMPATÍVEL — SEM TESTES |
| Gertec | TC-508 | SC504 (16510) | ⚠️ COMPATÍVEL — SEM TESTES |
| Gertec | GB-600 / GB-601 | SC504 (16510) | ⚠️ COMPATÍVEL — SEM TESTES |
| Gertec | Linha G-BOT / G-BOT2 | SC504 (16510) | ⚠️ COMPATÍVEL — SEM TESTES |

> **TC-406:** consulta de preço somente texto (sem envio de imagem na consulta).

### Resumo por porta

| Porta | Protocolo | Modelos |
|------:|-----------|---------|
| **6500** | SC501 | TC-406, TC-502, TC-505, TC-507, Busca Preço G2 |
| **16510** | SC504 | TC-504, TC-506 Mídia, TC-508, GB-600/601, G-BOT/G-BOT2 |

### Observações

- **Testado de ponta a ponta:** TC-506 Mídia (consulta, imagem, mídia/propaganda) e Busca Preço G2 (handshake `#live`, consulta textual).
- Demais modelos usam o mesmo protocolo da família; devem funcionar, mas **não houve captura/validação** neste projeto.
- Resolução de layout de referência: TC-506 Mídia **480×272**; TC-504 **320×240** (layout escalado por modelo).

---

## Requisitos

- Python **3.10+**
- Rede acessível aos terminais Gertec
- (Opcional) Firebird client se for usar base DBWare / Firebird

---

## Instalação rápida

### Docker (recomendado para servidor / Linux)

```bash
docker compose up -d
```

Painel em http://localhost:6689/painel. Detalhes em [DOCKER.md](DOCKER.md).

Sem clonar o repositório, se a imagem já estiver no GitHub Container Registry:

```bash
docker run -d --name arauto --restart unless-stopped \
  -p 6689:6689 -p 5589:5589 -p 6500:6500 -p 16510:16510 \
  -v arauto-data:/data \
  ghcr.io/mestretm/arautopy:latest
```

### Local (Python)

```bash
pip install -r requirements.txt
python run.py
```

No Windows também existem atalhos:

| Script | Uso |
|---|---|
| `run_venv.bat` | Cria/usa `.venv\` interno e sobe o servidor |

### instruções de configuração rápida 

[![instruções e tutorial ArautoPY](https://img.youtube.com/vi/T3Bj4OTtG4E/maxresdefault.jpg)](https://www.youtube.com/watch?v=T3Bj4OTtG4E)

Após iniciar:

| Serviço | Porta | Função |
|---|---|---|
| **Painel / WebViewer** | **6689** | Consulta no navegador, configuração, layout, logs, plugins |
| **API** | **5589** | REST para PDV, e-commerce e apps |
| **SC501** | **6500** | TC-406, TC-502, TC-505, TC-507, Busca Preço G2 |
| **SC504** | **16510** | TC-504, TC-506 Mídia, TC-508, GB-600/601 |

Só um modo: `python run.py --modo webviewer` (ou `api`, `sc501`, `sc504`).

---

## Primeiros passos

### 1. Produtos

Formato texto compatível com o TC Server original (`código|descrição|preço1|preço2|`):

```
7891000100103|LEITE MOÇA LATA 395G|R$ 8,49|R$ 7,29|
7894900011517|COCA-COLA PET 2L|12,99||
```

```bash
python run.py --importar produtos.txt
```

Ou configure base **SQL externa** em **Configuração** (PostgreSQL, MySQL, SQL Server, Firebird…).

### 2. Painel

Abra **http://localhost:6689/config**.

- Senha padrão do painel: `admin` (troca obrigatória no primeiro acesso)
- Dados da instalação: `~/.arauto/` (`config.properties`, bases SQLite, imagens, plugins)
- Variável de ambiente alternativa: `ARAUTO_HOME` (ou legada `TCSERVER_HOME`)

### 3. Terminais

Aponte o terminal Gertec para o IP da máquina e as portas SC501/SC504.
SC504 e SC501 vêm ativos por padrão; há modo passivo para depuração.

---

## Funcionalidades

### Terminais e consulta

- Protocolos **SC501** e **SC504** (identificação, keep-alive, consulta)
- Busca Preço **G2** (handshake `#live`, resposta textual)
- Layout visual editável (posições, cores, guias de alinhamento)
- Imagem de produto no **TC-506 Mídia** (após o texto; EAN local + fallback Cosmos)
- TC-406: consulta só texto (sem envio de imagem na consulta)

### Base de produtos

- Arquivo texto, SQLite interno ou **EXTERNAL_SQL**
- **Firebird** via `firebird+firebird://…` (preset DBWare)
- Mapeamento assistido de tabela/colunas e botão **Testar** conexão
- Recarga periódica (padrão 1 min) e reaplicação a quente de várias configs

### Imagens

- Pasta local `~/.arauto/imagens/{ean13}.jpg`
- Pacote inicial no GitHub + download com barra de progresso
- Fallback Bluesoft Cosmos com redimensionamento (Pillow)

### Painel web

- Abas: Painel · Configuração · Layout · Logs/Monitor · Plugins
- Cabeçalho único (`base.html`) também para páginas de plugin
- Inicialização com o sistema (Windows: registro + Startup; Linux: XDG)
- Bandeja do sistema (`--tray` / build .exe)
- **Atualizações** a partir dos releases do GitHub + changelog remoto

### Plugins

Sistema extensível: instalar ZIP, ativar/desativar, atualizar, documentação em Markdown.

| Plugin padrão | Função |
|---|---|
| **Gerenciador de mídia TC-506M** | Enviar, listar, visualizar e apagar mídias; playlists de propaganda / sensor |
| **Explorador de banco** | Navegar tabelas do `DB_URL`, filtrar, editar e excluir (confirmação dupla) |

Plugins padrão **não podem ser desinstalados** — apenas desativados.
Documentação: no painel em **Plugins → Documentação** ou em [`docs/plugins.md`](docs/plugins.md).

---

## API (5589)

Documentação interativa: **http://localhost:5589/docs**

Principais rotas de consulta:

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/product/{codigo}` | Consulta por código de barras |
| `GET` | `/api/v1/products` | Listagem / busca |
| `POST` | `/api/v1/query` | Consulta em corpo JSON |

Se `API_KEY` estiver definida, envie o cabeçalho `X-API-Key`.

---

## Configuração relevante

Arquivo: `~/.arauto/config.properties` (editável também pela web).

| Chave | Uso |
|---|---|
| `STORE_NAME` | Nome da loja no terminal |
| `LABEL1` / `LABEL2` | Rótulos dos preços |
| `SHOW_PRODUCT_IMAGE` | Imagem no SC504 |
| `DB_MODE` / `DB_URL` | Base de produtos (texto, interna, SQL) |
| `AUTO_INIT_501` / `AUTO_INIT_504` | Subir protocolos na inicialização |
| `SC501_PASSIVE` / `SC504_PASSIVE` | Modo passivo (debug) |
| `PORT_WEBVIEWER` / `PORT_API` | Portas HTTP |

Preset DBWare (Firebird) — caminho do `.fdb` varia por instalação:

```properties
DB_MODE=EXTERNAL_SQL
DB_URL=firebird+firebird://SYSDBA:masterkey@localhost/C:/DBVenda/DB/dbvenda.fdb?charset=WIN1252
DB_COL_BARCODE=CODIGO_BARRA
DB_COL_BARCODE_ALT=REFERENCIA
DB_COL_DESCRIPITION=DESCRICAO
DB_COL_PRICE1=PRC_VENDA
DB_COL_PRICE2=PRC_VENDA
```

---

## Atualização

No painel: **Configuração → Atualizações**.

- Repositório oficial fixo (não configurável pelo usuário)
- Compara a tag do último release com a versão local
- Changelog carregado de [`changelog.md`](changelog.md) no GitHub
- Aplicação automática vale para instalação em Python (não para `.exe`)

Para publicar uma versão: crie um **Release** no GitHub com tag (`v1.0.1`) e, de preferência, anexe o asset `ArautoPY.zip`.

---

## Estrutura do projeto

```
ArautoPY/
  run.py                 entrada principal
  run.bat / run_venv.bat atalhos Windows
  requirements.txt
  changelog.md
  arauto/
    core/                serviço de consulta, settings, autostart, updater
    data/                repositórios (texto, SQLite, SQL/Firebird)
    protocol/            SC501, SC504, mídia
    plugins/             loader + exemplos (mídia TC-506, explorador BD)
    web/                 painel, API, templates, static
  docs/                  engenharia reversa e documentação de plugins
```

Dados do cliente ficam em `~/.arauto/` — atualizar o código não apaga configuração, produtos nem plugins instalados.

---

## Diferenças em relação ao TC Server original

**Mantido / compatível**

- Formato de `produtos.txt` e várias chaves de `config.properties`
- Comportamento de consulta SC501 / SC504 observado em captura real

**Novo**

- Painel web moderno, API REST, plugins, Firebird/DBWare, imagens locais, atualização via GitHub, autostart, tray

**Fora de escopo (por enquanto)**

- Interface Swing do original
- TTS / áudio MBROLA
- Atualização remota de firmware do terminal

Detalhes de protocolo e imagens: [`docs/engenharia-reversa.md`](docs/engenharia-reversa.md).

---

## Licença e créditos

Projeto comunitário de integração com terminais Gertec.
Protocolos documentados a partir do manual de desenvolvimento e de capturas com hardware real.

Veja o histórico completo em [`changelog.md`](changelog.md).


