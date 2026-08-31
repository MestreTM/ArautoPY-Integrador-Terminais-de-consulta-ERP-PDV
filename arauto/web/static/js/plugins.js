(function () {
  "use strict";
  const { $, esc, json, aviso } = window.TC;

  let instalados = [];
  let catalogo = [];
  let filtroInst = "";
  let buscaCat = "";

  function aba(nome) {
    document.querySelectorAll(".plugins-tab[data-aba]").forEach((b) => {
      const on = b.dataset.aba === nome;
      b.classList.toggle("plugins-tab--ativa", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    const inst = $("painel-instalados");
    const add = $("painel-instalar");
    if (inst) inst.hidden = nome !== "instalados";
    if (add) add.hidden = nome !== "instalar";
    try { history.replaceState(null, "", nome === "instalar" ? "#instalar" : "#instalados"); } catch (e) {}
  }

  document.querySelectorAll(".plugins-tab[data-aba]").forEach((b) => {
    b.addEventListener("click", () => aba(b.dataset.aba));
  });
  if (location.hash === "#instalar") aba("instalar");

  function abrirZip() {
    const m = $("modal-zip");
    if (m) m.hidden = false;
  }
  function fecharZip() {
    const m = $("modal-zip");
    if (m) m.hidden = true;
  }
  if ($("btn-abrir-zip")) $("btn-abrir-zip").addEventListener("click", abrirZip);
  if ($("modal-zip-fechar")) $("modal-zip-fechar").addEventListener("click", fecharZip);
  if ($("modal-zip-cancelar")) $("modal-zip-cancelar").addEventListener("click", fecharZip);
  if ($("modal-zip-fundo")) $("modal-zip-fundo").addEventListener("click", fecharZip);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && $("modal-zip") && !$("modal-zip").hidden) fecharZip();
  });

  function badge(txt, cls) {
    return `<span class="badge-img ${cls || ""}">${esc(txt)}</span>`;
  }

  function renderInstalados() {
    const box = $("plugins-lista");
    if (!box) return;
    const n = $("tab-n-instalados");
    if (n) n.textContent = String(instalados.length);
    let lista = instalados.slice();
    if (filtroInst === "ativos") lista = lista.filter((p) => p.habilitado);
    if (filtroInst === "inativos") lista = lista.filter((p) => !p.habilitado);
    if (filtroInst === "atualizacao") lista = lista.filter((p) => p.atualizavel);
    if (!lista.length) {
      box.innerHTML = '<p class="meta-img">Nenhum plugin neste filtro. Use a aba <strong>Instalar plugins</strong> para adicionar.</p>';
      return;
    }
    box.innerHTML =
      `<table class="tabela plugins-tabela">
        <thead>
          <tr>
            <th>Plugin</th>
            <th>Estado</th>
            <th>Ações</th>
          </tr>
        </thead>
        <tbody>` +
      lista.map((p) => {
        const tags = [
          p.origem === "online" ? badge("Online", "badge-img--ok") : badge("Local"),
          p.atualizavel ? badge("Atualização", "badge-img--warn") : "",
          p.modificado_localmente ? badge("Editado", "badge-img--warn") : "",
        ].filter(Boolean).join(" ");
        const estado = p.erro
          ? badge("Erro", "badge-img--no")
          : (p.habilitado ? badge("Ativo", "badge-img--ok") : badge("Inativo", "badge-img--warn"));
        const abas = (p.abas || []).map((a) =>
          `<a class="mono" href="${esc(a.href)}">${esc(a.rotulo)}</a>`
        ).join(" · ");
        const toggle = p.habilitado
          ? `<button type="button" class="botao botao--fantasma botao--mini" data-off="${esc(p.id)}">Desativar</button>`
          : `<button type="button" class="botao botao--claro botao--mini" data-on="${esc(p.id)}">Ativar</button>`;
        const upd = p.atualizavel
          ? `<button type="button" class="botao botao--claro botao--mini" data-upd-online="${esc(p.id)}">Atualizar</button>`
          : "";
        const del = `<button type="button" class="botao botao--fantasma botao--mini" data-del="${esc(p.id)}" style="color:var(--erro)">Excluir</button>`;
        const ico = p.icone
          ? `<img class="plugin-ico" src="${esc(p.icone)}" alt="" onerror="this.classList.add('plugin-ico--vazio');this.removeAttribute('src')">`
          : `<span class="plugin-ico plugin-ico--vazio" aria-hidden="true"></span>`;
        return `<tr class="${p.habilitado ? "" : "linha-falha"}">
          <td>
            <div class="plugin-linha-nome">${ico}<div>
            <strong>${esc(p.nome)}</strong>
            <span class="mono">v${esc(p.versao)}</span>
            ${tags}
            <p class="meta-img" style="margin:.25rem 0 0">${esc(p.descricao || "Sem descrição")}</p>
            <p class="meta-img">ID <span class="mono">${esc(p.id)}</span>${p.autor ? " · " + esc(p.autor) : ""}${abas ? " · Abas: " + abas : ""}</p>
            ${p.erro ? `<p class="meta-img" style="color:var(--erro)">${esc(p.erro)}</p>` : ""}
            </div></div>
          </td>
          <td>${estado}</td>
          <td><div class="plugins-acoes-cel">${toggle}${upd}${del}</div></td>
        </tr>`;
      }).join("") +
      `</tbody></table>`;
  }

  function renderCatalogo() {
    const box = $("catalogo-lista");
    if (!box) return;
    const q = (buscaCat || "").trim().toLowerCase();
    const lista = catalogo.filter((p) => {
      if (!q) return true;
      return [p.nome, p.descricao, p.id, p.repo].join(" ").toLowerCase().indexOf(q) >= 0;
    });
    if (!catalogo.length) {
      box.innerHTML = '<p class="meta-img">Catálogo online indisponível no momento. Seus plugins locais continuam funcionando. Você ainda pode enviar um ZIP.</p>';
      return;
    }
    if (!lista.length) {
      box.innerHTML = '<p class="meta-img">Nenhum item no catálogo para essa busca.</p>';
      return;
    }
    box.innerHTML = lista.map((p) => {
      const icoSrc = p.icone || "";
      const ico = icoSrc
        ? `<img class="plugin-ico" src="${esc(icoSrc)}" alt="" onerror="this.classList.add('plugin-ico--vazio');this.removeAttribute('src')">`
        : `<span class="plugin-ico plugin-ico--vazio" aria-hidden="true"></span>`;
      let acao = "";
      if (p.status === "instalado" && p.atualizavel) {
        acao = `<button type="button" class="botao botao--claro" data-upd-online="${esc(p.id)}">Atualizar</button>`;
      } else if (p.status === "instalado") {
        acao = `<button type="button" class="botao" disabled>Já instalado</button>`;
      } else {
        acao = `<button type="button" class="botao botao--claro" data-inst-online="${esc(p.id)}">Instalar agora</button>`;
      }
      const req = p.min_versao_app ? `<p class="meta-img">Requer ArautoPY ${esc(p.min_versao_app)}+</p>` : "";
      const deps = (p.dependencias_pip || []).length
        ? `<p class="meta-img">pip (manual): <span class="mono">${esc((p.dependencias_pip || []).join(" "))}</span>
           <button type="button" class="botao botao--mini botao--fantasma" data-pip="${esc((p.dependencias_pip || []).join(" "))}">Copiar</button></p>`
        : "";
      return `<article class="plugin-card">
        <div class="plugin-card-cab">
          <div style="display:flex;gap:.7rem;align-items:flex-start;min-width:0">
            ${ico}
            <div>
              <h3>${esc(p.nome)} <span class="mono" style="font-weight:400;font-size:.85rem">${esc(p.tag || p.versao || "")}</span></h3>
              <p class="meta-img">${esc(p.descricao || "")}</p>
            </div>
          </div>
          ${acao}
        </div>
        <p class="meta-img">ID <span class="mono">${esc(p.id)}</span>${p.repo ? " · " + esc(p.repo) : ""}</p>
        ${req}${deps}
      </article>`;
    }).join("");
  }

  async function carregar() {
    const box = $("plugins-lista");
    try {
      const cat = await json("/api/plugins/catalogo");
      instalados = cat.instalados || [];
      catalogo = cat.online || [];
      const st = $("catalogo-status");
      if (st) {
        st.textContent = cat.catalogo_erro && !catalogo.length
          ? "Catálogo online indisponível no momento. Envie um ZIP se precisar instalar localmente."
          : (catalogo.length + " plugin(s) no índice público. Nada é instalado sozinho.");
      }
    } catch (e) {
      try {
        const r = await json("/api/plugins");
        instalados = r.plugins || [];
      } catch (e2) {
        if (box) box.innerHTML = `<p class="meta-img" style="color:var(--erro)">${esc(e2.message)}</p>`;
        return;
      }
    }
    renderInstalados();
    renderCatalogo();
  }

  async function carregarCatalogo(forcar) {
    const st = $("catalogo-status");
    if (st) st.textContent = "Atualizando índice…";
    try {
      const r = await json(forcar ? "/api/plugins/catalogo/refresh" : "/api/plugins/catalogo");
      instalados = r.instalados || instalados;
      catalogo = r.online || [];
      if (st) {
        st.textContent = r.catalogo_erro && !catalogo.length
          ? "Catálogo online indisponível no momento."
          : (catalogo.length + " plugin(s) no índice público.");
      }
      renderInstalados();
      renderCatalogo();
    } catch (e) {
      if (st) st.textContent = e.message || "indisponível";
      renderCatalogo();
    }
  }

  document.querySelectorAll("[data-filtro]").forEach((b) => {
    b.addEventListener("click", () => {
      filtroInst = b.dataset.filtro || "";
      document.querySelectorAll("[data-filtro]").forEach((x) => {
        x.classList.toggle("filtro-fonte-btn--ativo", x === b);
      });
      renderInstalados();
    });
  });
  if ($("catalogo-busca")) {
    $("catalogo-busca").addEventListener("input", () => {
      buscaCat = $("catalogo-busca").value || "";
      renderCatalogo();
    });
  }
  if ($("btn-catalogo-refresh")) {
    $("btn-catalogo-refresh").addEventListener("click", () => carregarCatalogo(true));
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
          <p>Deseja substituir os arquivos e recarregar o módulo?</p>
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
    if (status) {
      status.hidden = false;
      status.textContent = "Instalando " + file.name + "…";
      status.style.color = "var(--texto-2)";
    }
    try {
      let { r, corpo } = await postZip(file, false);
      if (!corpo.ok && corpo.ja_existe) {
        const ok = await abrirModalAtualizar(file, corpo.id);
        if (!ok) {
          if (status) { status.textContent = "Instalação cancelada."; }
          return;
        }
        ({ r, corpo } = await postZip(file, true));
      }
      if (!r.ok || corpo.ok === false) throw new Error(corpo.detail || "Falha na instalação");
      if (status) {
        status.textContent = corpo.detail || "Instalado.";
        status.style.color = "var(--ok)";
      }
      aviso(corpo.detail || "Plugin instalado.");
      await carregar();
      aba("instalados");
    } catch (e) {
      if (status) {
        status.textContent = e.message;
        status.style.color = "var(--erro)";
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

  async function acaoOnline(id, modo, extra) {
    extra = extra || {};
    const url = modo === "atualizar"
      ? "/api/plugins/" + encodeURIComponent(id) + "/atualizar"
      : "/api/plugins/" + encodeURIComponent(id) + "/instalar-online";
    return json(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ confirmar: true }, extra)),
    });
  }

  document.addEventListener("click", async (ev) => {
    const pip = ev.target.closest("[data-pip]");
    if (pip) {
      const cmd = "pip install " + pip.getAttribute("data-pip");
      try { await navigator.clipboard.writeText(cmd); aviso("Comando copiado: " + cmd); }
      catch (e) { aviso(cmd); }
      return;
    }
    const on = ev.target.closest("[data-on]");
    if (on) {
      try {
        const r = await json("/api/plugins/" + encodeURIComponent(on.dataset.on) + "/habilitar", { method: "POST" });
        aviso(r.detail || "Plugin ativado.");
        await carregar();
      } catch (e) { aviso(e.message, true); }
      return;
    }
    const off = ev.target.closest("[data-off]");
    if (off) {
      try {
        const r = await json("/api/plugins/" + encodeURIComponent(off.dataset.off) + "/desabilitar", { method: "POST" });
        aviso(r.detail || "Plugin desativado.");
        await carregar();
      } catch (e) { aviso(e.message, true); }
      return;
    }
    const del = ev.target.closest("[data-del]");
    if (del) {
      if (!confirm("Excluir o plugin \"" + del.dataset.del + "\"? A pasta será apagada.")) return;
      try {
        const r = await fetch("/api/plugins/" + encodeURIComponent(del.dataset.del) + "/desinstalar", { method: "POST" });
        const corpo = await r.json().catch(() => ({}));
        if (!r.ok || corpo.ok === false) throw new Error(corpo.detail || "Falha ao excluir");
        aviso(corpo.detail || "Plugin removido.");
        await carregar();
      } catch (e) { aviso(e.message, true); }
      return;
    }
    const inst = ev.target.closest("[data-inst-online]");
    const upd = ev.target.closest("[data-upd-online]");
    const id = inst ? inst.getAttribute("data-inst-online") : (upd ? upd.getAttribute("data-upd-online") : "");
    if (!id) return;
    const modo = upd ? "atualizar" : "instalar";
    if (!confirm((modo === "atualizar" ? "Atualizar" : "Instalar") + " o plugin " + id + "?")) return;
    const btn = inst || upd;
    btn.disabled = true;
    try {
      const extra = {};
      let r = await acaoOnline(id, modo, extra);
      if (r.precisa_confirmar_modificado) {
        if (!confirm(r.detail || "Plugin modificado localmente. Continuar?")) return;
        extra.confirmar_modificado = true;
        r = await acaoOnline(id, modo, extra);
      }
      if (r.precisa_confirmar_checksum) {
        if (!confirm(r.detail || "Checksum não confere. Continuar mesmo assim?")) return;
        extra.confirmar_checksum = true;
        r = await acaoOnline(id, modo, extra);
      }
      if (!r.ok) throw new Error(r.detail || "Falha");
      aviso(r.detail || "OK");
      if (r.pip_cmd) aviso("Dependências pip (instale você): " + r.pip_cmd);
      await carregar();
      aba("instalados");
    } catch (e) {
      aviso(e.message, true);
    } finally {
      btn.disabled = false;
    }
  });

  carregar();
})();
