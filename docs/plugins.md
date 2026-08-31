# Sistema de plugins do ArautoPY

O ArautoPY pode ser estendido sem alterar o código-fonte principal. Plugins
ficam em pastas no disco, são descobertos na subida do servidor e podem:

- registrar **rotas HTTP** (páginas, APIs, terminais de consulta alternativos)
- adicionar **abas** no cabeçalho da administração
- reagir a **consultas de preço** (hooks)
- oferecer **ferramentas de depuração** ou integração com ERPs

---

## Instalar pelo painel

Na aba **Plugins** você pode:

- **Instalar** arrastando um `.zip` ou escolhendo o arquivo
- **Atualizar** (marque “Atualizar se já existir”)
- **Ativar / desativar** sem apagar a pasta
- **Desinstalar** (remove a pasta do plugin)
- **Baixar o plugin exemplo** (`docs/plugin-exemplo-hello.zip`)

Após instalar ou atualizar, **reinicie o servidor** para o código entrar em vigor.

O ZIP pode ter `plugin.py` na raiz ou em uma subpasta (`meu_plugin/plugin.py`).

---

## Onde ficam os plugins

```text
%USERPROFILE%\.arautopy\plugins\
    meu_plugin\
        plugin.json      # metadados (obrigatório recomendado)
        plugin.py        # código com setup(ctx)
        ...              # arquivos extras do plugin
```

Na primeira execução, o servidor copia um plugin de exemplo para essa pasta.

Estado ligado/desligado:

```text
%USERPROFILE%\.arautopy\plugins_estado.json
```

---

## Anatomia de um plugin

### `plugin.json`

```json
{
  "id": "meu_plugin",
  "nome": "Meu plugin",
  "versao": "1.0.0",
  "descricao": "Faz algo útil na loja.",
  "autor": "Sua empresa",
  "icone": "icon.jpg"
}
```

Ícone: o padrão é `icon.jpg` na raiz do plugin (também vale `icon.png` / `icons/icon.jpg`). Se o arquivo tiver outro nome, informe em `icone` (ex.: `"icons/gerador_de_cartaz.jpg"`). Sem arquivo, o painel mostra um placeholder.

### `plugin.py`

Forma recomendada — função `setup`:

```python
from fastapi.responses import HTMLResponse, JSONResponse

def setup(ctx):
    from fastapi import Request

    # Aba no cabeçalho universal (base.html)
    ctx.adicionar_aba("meu-plugin", "Meu plugin", "/plugins/meu-plugin/", ordem=50)

    @ctx.app.get("/plugins/meu-plugin/", response_class=HTMLResponse)
    def pagina(request: Request):
        return ctx.render(
            request,
            titulo="Meu plugin",
            conteudo="<section class=\"cartao\"><h2>Olá do plugin</h2></section>",
            pagina="meu-plugin",
        )

    @ctx.app.get("/plugins/meu-plugin/api/ping")
    def ping():
        return {"ok": True, "produtos": ctx.service.repo.count()}

    @ctx.ao_consultar
    def depois_da_consulta(resultado, origem, canal):
        # resultado é o objeto QueryResult
        if resultado.found:
            print("Consulta:", resultado.barcode, resultado.price1)
```

Forma alternativa — classe `Plugin`:

```python
from arauto.plugins import Plugin

class Plugin(Plugin):
    id = "meu_plugin"
    nome = "Meu plugin"
    versao = "1.0.0"

    def setup(self, ctx):
        ctx.adicionar_aba("x", "X", "/plugins/x/")
```

---

## Contexto (`ctx`)

| Atributo / método | Descrição |
|-------------------|-----------|
| `ctx.app` | Instância FastAPI do WebViewer — use para registrar rotas |
| `ctx.service` | `QueryService` (consultas, repositório, máscara de balança) |
| `ctx.plugin_id` | Identificador da pasta do plugin |
| `ctx.adicionar_aba(id, rotulo, href, ordem=100)` | Nova aba no cabeçalho |
| `ctx.ao_consultar(fn)` | Callback após cada consulta de preço |
| `ctx.mapeamento_colunas()` | Colunas SQL: `barcode`, `barcode_alt`, descrição, preços, tabela |
| `ctx.service.repo` | Repositório de produtos (`get`, `search`, `count`) |

### Consultar produto

```python
r = ctx.service.query("001100", origin="plugin", channel="meu_plugin")
if r.found:
    print(r.description, r.price1)
    # PLU de balança (quando CODIGO_BARRA está vazio e DB_COL_BARCODE_ALT=REFERENCIA):
    print(getattr(r, "extra", {}) or {})
    # r.extra["codigo_adicional"], r.extra["origem_codigo"]
```

`origem_codigo` vale `"barcode"` ou `"adicional"`. `codigo_adicional` é o valor
da coluna extra (ex.: `REFERENCIA` no DBware).

### Listar produtos

```python
itens = ctx.service.repo.search("arroz", limit=20)
```

---

## Boas práticas

1. **Prefixe rotas** com `/plugins/<seu_id>/` para não colidir com o núcleo.
2. **Não bloqueie** a thread em hooks de consulta (I/O longo → thread/fila).
3. **Trate erros** dentro do plugin; exceções no `setup` desabilitam só aquele plugin.
4. **Evite** gravar em pastas do código-fonte; use `Path.home() / ".arautopy"`.
5. **Reinicie o servidor** após criar ou editar um plugin (o código Python é importado na subida).

---

## Habilitar e desabilitar

Na interface **Plugins** do painel, ou via API:

```http
POST /api/plugins/{id}/habilitar
POST /api/plugins/{id}/desabilitar
```

Plugins desabilitados não executam `setup` e não expõem abas. A mudança de
habilitação exige **reinício do servidor** para carregar/descarregar o código.

---

## Ideias de plugins

| Tipo | Exemplos |
|------|----------|
| Terminal | Consulta com layout customizado, totem multi-idioma |
| Integração | Enviar consulta para webhook, ERP, planilha |
| Depuração | Dump de frames SC504, simulador de etiquetas |
| Operação | Painel de ruptura, lista de promoções do dia |

---

## API HTTP do gerenciador

| Método | Caminho | Função |
|--------|---------|--------|
| GET | `/plugins` | Página de gerenciamento |
| GET | `/plugins/docs` | Esta documentação (HTML) |
| GET | `/api/plugins` | Lista plugins (JSON) |
| GET | `/api/plugins/docs` | Markdown bruto |
| POST | `/api/plugins/{id}/habilitar` | Liga o plugin |
| POST | `/api/plugins/{id}/desabilitar` | Desliga o plugin |

---

## Solução de problemas

**Plugin não aparece**  
Confira se existe `plugin.py` (ou `__init__.py`) dentro de uma subpasta de
`~/.arautopy/plugins/`.

**Erro no carregamento**  
Abra **Logs** e procure por `arauto.plugins`. A tela Plugins também mostra a
mensagem de erro do `setup`.

**Aba não surge**  
O plugin precisa chamar `ctx.adicionar_aba(...)` e estar habilitado. Dê
Ctrl+F5 no navegador após reiniciar o servidor.

**Conflito de rota**  
Duas rotas iguais: a última registrada vence. Use sempre o prefixo
`/plugins/<id>/`.


---

## Servidor TCP / outros terminais

Além de rotas HTTP (`ctx.app`), o plugin pode abrir um **socket TCP** próprio:

```python
def setup(ctx):
    def handle(conn, addr):
        try:
            data = conn.recv(4096)
            # parse do protocolo do terminal...
            r = ctx.service.query(codigo, origin=addr[0], channel="meu-tcp")
            conn.sendall(resposta)
        finally:
            conn.close()

    ctx.registrar_tcp("0.0.0.0", 9100, handle, nome="meu-terminal")
```

Isso **não** substitui os protocolos SC501/SC504 do núcleo, mas permite
integrar equipamentos com protocolo próprio (impressoras, totems, etc.).


---

## Acesso a terminais SC504 vivos

`TerminalInfo` no `QueryService` só guarda metadados. A **conexão TCP viva**
fica no servidor SC504 e é exposta assim:

```python
def setup(ctx):
    for t in ctx.peers_sc504():
        print(t["peer"], t["modelo"])

    conn = ctx.conexao_sc504("192.168.10.18:34327")
    if conn:
        estado = conn.ler_estado_midia()
        conn.enviar_arquivo("INT_MEM/foto.jpg", dados)
        conn.apagar_arquivo("INT_MEM/foto.jpg")
        conn.atualizar_midias()
```

Também disponível em `arauto.core.runtime.conexao_sc504(peer)`.


---

## Cabeçalho universal (obrigatório)

Todas as telas da administração — **sistema e plugins** — compartilham o mesmo
`base.html`. O cabeçalho e as abas são renderizados uma vez só; o plugin entrega
apenas o **conteúdo** do `<main>`.

### O que o cabeçalho mostra

```text
Painel · Configuração · Layout · Logs · Monitor · Plugins
· [abas registradas por plugins] · Abrir terminal
```

Abas de plugins vêm de `ctx.adicionar_aba(...)` e aparecem em **todas** as
páginas que usam `base.html` (incluindo outras páginas de plugins).

### Como criar uma página de plugin

1. Registre a aba (opcional, mas recomendado).
2. Na rota, use `ctx.render(...)` — **não** devolva HTML completo com `<html>` / `<header>`.

```python
from fastapi import Request
from fastapi.responses import HTMLResponse

def setup(ctx):
    # 1) Aba no cabeçalho universal (visível em todo o painel)
    ctx.adicionar_aba(
        id="meu-plugin",          # deve coincidir com pagina= abaixo
        rotulo="Meu plugin",      # texto da aba
        href="/plugins/meu/"),
        ordem=50,                 # menor = mais à esquerda entre plugins
    )

    @ctx.app.get("/plugins/meu/", response_class=HTMLResponse)
    def pagina(request: Request):
        # 2) Só o miolo da página (HTML de conteúdo)
        conteudo = """
        <section class="cartao">
          <header class="config-secao-cab">
            <h2>Título da seção</h2>
            <p class="dica">Texto de ajuda.</p>
          </header>
          <p>Conteúdo do plugin.</p>
        </section>
        """
        return ctx.render(
            request,
            titulo="Meu plugin",           # <h1> e <title>
            conteudo=conteudo,
            pagina="meu-plugin",           # marca a aba ativa (mesmo id)
            scripts='<script src="/plugins/meu/app.js"></script>',  # opcional
        )
```

### Parâmetros de `ctx.render`

| Parâmetro | Função |
|-----------|--------|
| `request` | Objeto FastAPI `Request` da rota |
| `titulo` | Título da página (`<h1>` e `<title>`) |
| `conteudo` | HTML do miolo (vai dentro de `<main>`) |
| `pagina` | Id da aba ativa; use o mesmo `id` de `adicionar_aba` |
| `scripts` | HTML extra no final (tags `<script>`, etc.) |

### O que **não** fazer

```python
# ERRADO — cabeçalho próprio, abas do sistema somem
@ctx.app.get("/plugins/meu/")
def pagina():
    return """<!DOCTYPE html><html>...<header class="cabeca">..."""
```

### Resumo

| Objetivo | API |
|----------|-----|
| Nova aba no topo | `ctx.adicionar_aba(id, rotulo, href, ordem=100)` |
| Página com o mesmo cabeçalho | `ctx.render(request, titulo=..., conteudo=..., pagina=id)` |
| Só API JSON | rotas normais em `ctx.app` (sem `render`) |

O plugin de exemplo (`plugin-exemplo-hello.zip`) e o gerenciador de mídia
TC-506M já seguem este padrão.



