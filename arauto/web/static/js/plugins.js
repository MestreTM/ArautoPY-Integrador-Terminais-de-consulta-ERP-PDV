(function () {
  "use strict";
  const { $, esc, json, aviso } = window.TC;

  async function recarregarModulos() {
    try {
      const r = await json("/api/plugins/recarregar", { method: "POST" });
      aviso(r.detail || "Plugins recarregados.");
      return r;
    } catch (e) {
      aviso(e.message, true);
      throw e;
    }
  }

  async function carregar() {
    const box = $("plugins-lista");
    if (!box) return;
    try {
      const r = await json("/api/plugins");
      const itens = r.plugins || [];
      if (!itens.length) {
        box.innerHTML = '<p class="meta-img">Nenhum plugin instalado. Arraste um ZIP acima ou baixe o exemplo na documentação.</p>';
        return;
      }
      box.innerHTML = itens.map((p) => {
        const status = p.erro
          ? `<span class="badge-img badge-img--no">Erro</span>`
          : (p.habilitado
            ? `<span class="badge-img badge-img--ok">Ativo</span>`
            : `<span class="badge-img badge-img--warn">Desativado</span>`);
        const abas = (p.abas || []).map((a) =>
          `<a class="mono" href="${esc(a.href)}">${esc(a.rotulo)}</a>`
        ).join(" · ") || "—";
        const toggle = p.habilitado
          ? `<button type="button" class="botao botao--fantasma" data-off="${esc(p.id)}">Desativar</button>`
          : `<button type="button" class="botao botao--claro" data-on="${esc(p.id)}">Ativar</button>`;
        const badgePadrao = p.padrao
          ? ` <span class="badge-img badge-img--warn" title="Plugin padrão do sistema">Padrão</span>`
          : "";
        const btnDel = p.padrao
          ? `<span class="meta-img" style="align-self:center">Não pode ser desinstalado — apenas desativado</span>`
          : `<button type="button" class="botao botao--fantasma" data-del="${esc(p.id)}" style="color:var(--alerta)">Desinstalar</button>`;
        return `<article class="plugin-card">
          <div class="plugin-card-cab">
            <div>
              <h3>${esc(p.nome)} <span class="mono" style="font-weight:400;font-size:.85rem">v${esc(p.versao)}</span>${badgePadrao}</h3>
              <p class="meta-img">${esc(p.descricao || "Sem descrição")}</p>
            </div>
            ${status}
          </div>
          <p class="meta-img">ID: <span class="mono">${esc(p.id)}</span>
            ${p.autor ? " · " + esc(p.autor) : ""}</p>
          <p class="meta-img">Abas: ${abas}</p>
          ${p.erro ? `<p class="meta-img" style="color:var(--alerta)">${esc(p.erro)}</p>` : ""}
          <p class="meta-img mono" style="font-size:.75rem">${esc(p.caminho || "")}</p>
          <div style="margin-top:.6rem;display:flex;flex-wrap:wrap;gap:.4rem">
            ${toggle}
            ${btnDel}
          </div>
        </article>`;
      }).join("");

      box.querySelectorAll("[data-off]").forEach((b) => {
        b.addEventListener("click", async () => {
          try {
            const r = await json("/api/plugins/" + encodeURIComponent(b.dataset.off) + "/desabilitar", { method: "POST" });
            aviso(r.detail || "Plugin desativado.");
            carregar();
          } catch (e) { aviso(e.message, true); }
        });
      });
      box.querySelectorAll("[data-on]").forEach((b) => {
        b.addEventListener("click", async () => {
          try {
            const r = await json("/api/plugins/" + encodeURIComponent(b.dataset.on) + "/habilitar", { method: "POST" });
            aviso(r.detail || "Plugin ativado.");
            carregar();
          } catch (e) { aviso(e.message, true); }
        });
      });
      box.querySelectorAll("[data-del]").forEach((b) => {
        b.addEventListener("click", async () => {
          if (!confirm("Desinstalar o plugin \"" + b.dataset.del + "\"? A pasta será apagada.")) return;
          try {
            const r = await fetch("/api/plugins/" + encodeURIComponent(b.dataset.del) + "/desinstalar", { method: "POST" });
            const corpo = await r.json().catch(() => ({}));
            if (!r.ok || corpo.ok === false) throw new Error(corpo.detail || "Falha ao desinstalar");
            aviso(corpo.detail || "Plugin removido.");
            carregar();
          } catch (e) { aviso(e.message, true); }
        });
      });
    } catch (e) {
      box.innerHTML = `<p class="meta-img" style="color:var(--alerta)">${esc(e.message)}</p>`;
    }
  }

  async function postZip(file, atualizar) {
    const fd = new FormData();
    fd.append("arquivo", file, file.name);
    const url = "/api/plugins/instalar?atualizar=" + (atualizar ? "true" : "false");
    const r = await fetch(url, { method: "POST", body: fd });
    const corpo = await r.json().catch(() => ({}));
    return { r, corpo };
  }

  function abrirModalAtualizar(file, idPlugin) {
    return new Promise((resolve) => {
      const fundo = document.createElement("div");
      fundo.className = "plugin-modal-fundo";
      fundo.innerHTML = `
        <div class="plugin-modal-caixa" role="dialog" aria-modal="true">
          <h3>Plugin já instalado</h3>
          <p>O plugin <strong class="mono">${esc(idPlugin || file.name)}</strong> já está no sistema.</p>
          <p>Deseja <strong>substituir / atualizar</strong> os arquivos e recarregar o módulo?</p>
          <div class="plugin-modal-acoes">
            <button type="button" class="botao botao--fantasma" data-x>Cancelar</button>
            <button type="button" class="botao botao--claro" data-ok>Atualizar</button>
          </div>
        </div>`;
      document.body.appendChild(fundo);
      const fechar = (val) => { fundo.remove(); resolve(val); };
      fundo.querySelector("[data-x]").onclick = () => fechar(false);
      fundo.querySelector("[data-ok]").onclick = () => fechar(true);
      fundo.addEventListener("click", (e) => { if (e.target === fundo) fechar(false); });
    });
  }

  async function instalarArquivo(file) {
    if (!file) return;
    const status = $("plugin-install-status");
    const forcar = !!($("plugin-atualizar") && $("plugin-atualizar").checked);
    if (status) {
      status.hidden = false;
      status.textContent = "Instalando " + file.name + "…";
      status.style.color = "var(--texto-2)";
    }
    try {
      let { r, corpo } = await postZip(file, forcar);
      if (!corpo.ok && corpo.ja_existe && !forcar) {
        const ok = await abrirModalAtualizar(file, corpo.id);
        if (!ok) {
          if (status) { status.textContent = "Instalação cancelada."; status.style.color = "var(--texto-2)"; }
          return;
        }
        ({ r, corpo } = await postZip(file, true));
      }
      if (!r.ok || corpo.ok === false) {
        throw new Error(corpo.detail || "Falha na instalação");
      }
      if (status) {
        status.textContent = corpo.detail || "OK";
        status.style.color = "var(--ok, #6ddea0)";
      }
      aviso(corpo.detail || "Plugin instalado e recarregado.");
      carregar();
    } catch (e) {
      if (status) {
        status.textContent = e.message;
        status.style.color = "var(--alerta, #ff8a80)";
      }
      aviso(e.message, true);
    }
  }

  const drop = $("plugin-drop");
  const input = $("plugin-arquivo");
  if ($("btn-plugin-escolher") && input) {
    $("btn-plugin-escolher").addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      if (input.files && input.files[0]) instalarArquivo(input.files[0]);
      input.value = "";
    });
  }
  if (drop) {
    ["dragenter", "dragover"].forEach((ev) => {
      drop.addEventListener(ev, (e) => {
        e.preventDefault();
        drop.classList.add("plugin-drop--over");
      });
    });
    ["dragleave", "drop"].forEach((ev) => {
      drop.addEventListener(ev, (e) => {
        e.preventDefault();
        drop.classList.remove("plugin-drop--over");
      });
    });
    drop.addEventListener("drop", (e) => {
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) instalarArquivo(f);
    });
  }
  carregar();
})();


