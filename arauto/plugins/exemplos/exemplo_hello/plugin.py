"""Plugin de exemplo do ArautoPY — usa o cabeçalho universal."""

from fastapi import Request
from fastapi.responses import HTMLResponse


def setup(ctx):
    # Aba aparece no base.html de todas as telas (sistema + plugins)
    ctx.adicionar_aba("exemplo-hello", "Olá plugin", "/plugins/exemplo-hello/", ordem=90)

    @ctx.app.get("/plugins/exemplo-hello/", response_class=HTMLResponse)
    def pagina_hello(request: Request):
        # Nunca monte <header> próprio: ctx.render injeta base.html
        conteudo = """
<section class="cartao">
  <header class="config-secao-cab">
    <h2>Plugin de exemplo</h2>
    <p class="dica">
      Esta página usa o mesmo cabeçalho do Painel, Configuração, Logs, etc.
      A aba &quot;Olá plugin&quot; foi registrada com <span class="mono">ctx.adicionar_aba</span>.
    </p>
  </header>
  <p>Se você está vendo as abas do sistema acima, o <span class="mono">ctx.render</span> está funcionando.</p>
  <p class="meta-img">ID do plugin: exemplo_hello</p>
</section>
"""
        return ctx.render(
            request,
            titulo="Olá plugin",
            conteudo=conteudo,
            pagina="exemplo-hello",
        )


