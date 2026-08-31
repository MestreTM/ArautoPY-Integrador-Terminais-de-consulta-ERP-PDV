(function () {
  "use strict";
  const BASE = "/plugins/folhas-promocionais/api";
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const SNAP = 12; // px de tela — mais fácil grudar no centro

  const estado = {
    meta: null,
    template: null,
    selecionada: null,
    produto: null,
    codigo: "",
    pxPorMm: 2.2,
    arraste: null,
    /** cache estável de URL de preview: key -> url */
    imgCache: {},
    /** camada pendente no modal de imagem personalizada */
    pendingCustomId: null,
    projetoAtivo: false,
  };

  async function api(path, opts) {
    const r = await fetch(BASE + path, {
      cache: "no-store",
      headers: opts && opts.body ? { "Content-Type": "application/json" } : undefined,
      ...opts,
    });
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const j = await r.json();
      if (!r.ok || j.ok === false) throw new Error(j.detail || r.statusText);
      return j;
    }
    if (!r.ok) throw new Error(r.statusText || "Falha na requisição");
    return r;
  }

  function uid(prefix) {
    return (prefix || "c") + "-" + Math.random().toString(36).slice(2, 9);
  }

  function papelAtual() {
    const tipo = $("folha-papel").value || "A4";
    const meta = (estado.meta && estado.meta.papeis) || {};
    if (tipo === "custom") {
      return {
        tipo: "custom",
        largura_mm: parseFloat($("folha-w").value) || 210,
        altura_mm: parseFloat($("folha-h").value) || 297,
      };
    }
    const p = meta[tipo] || { largura_mm: 210, altura_mm: 297 };
    return { tipo, largura_mm: p.largura_mm, altura_mm: p.altura_mm };
  }

  function syncPapelNoTemplate() {
    if (!estado.template) return;
    estado.template.papel = papelAtual();
    estado.template.cor_fundo = $("folha-fundo").value || "#ffffff";
    const p = estado.template.papel;
    $("folha-info-papel").textContent =
      (p.tipo || "custom").toUpperCase() +
      " · " +
      p.largura_mm +
      "×" +
      p.altura_mm +
      " mm";
  }

  function escalarCamadas(oldW, oldH, newW, newH) {
    if (!estado.template || !oldW || !oldH || !newW || !newH) return;
    if (oldW === newW && oldH === newH) return;
    const sx = newW / oldW;
    const sy = newH / oldH;
    (estado.template.camadas || []).forEach((c) => {
      c.x_mm = Math.round((c.x_mm || 0) * sx * 10) / 10;
      c.y_mm = Math.round((c.y_mm || 0) * sy * 10) / 10;
      c.largura_mm = Math.round((c.largura_mm || 10) * sx * 10) / 10;
      c.altura_mm = Math.round((c.altura_mm || 10) * sy * 10) / 10;
      if (c.fonte_mm) {
        c.fonte_mm = Math.round(c.fonte_mm * ((sx + sy) / 2) * 10) / 10;
      }
    });
  }

  function aoMudarPapel() {
    if (!estado.template) return;
    const antes = estado.template.papel || { largura_mm: 210, altura_mm: 297 };
    const tipo = $("folha-papel").value || "A4";
    $("folha-custom-size").hidden = tipo !== "custom";
    if (tipo !== "custom" && estado.meta.papeis[tipo]) {
      $("folha-w").value = estado.meta.papeis[tipo].largura_mm;
      $("folha-h").value = estado.meta.papeis[tipo].altura_mm;
    }
    const depois = papelAtual();
    escalarCamadas(
      Number(antes.largura_mm) || 210,
      Number(antes.altura_mm) || 297,
      Number(depois.largura_mm) || 210,
      Number(depois.altura_mm) || 297
    );
    estado.template.papel = depois;
    renderTudo();
  }

  function parsePreco(v) {
    if (v == null || v === "") return NaN;
    const n = parseFloat(String(v).replace(/R\$\s?/gi, "").replace(/\./g, "").replace(",", ".").trim());
    // se veio "12.50" sem milhar, segunda tentativa
    if (isNaN(n)) {
      return parseFloat(String(v).replace(",", ".").replace(/[^0-9.]/g, ""));
    }
    // heurística: se string tinha vírgula decimal BR
    const s = String(v);
    if (s.indexOf(",") >= 0) {
      return parseFloat(s.replace(/R\$\s?/gi, "").replace(/\./g, "").replace(",", ".").trim());
    }
    return parseFloat(String(v).replace(/[^0-9.]/g, ""));
  }

  function formatPrecoBR(n) {
    if (isNaN(n)) return "—";
    return (
      "R$ " +
      n.toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, ".")
    );
  }

  function precoExibido(campo) {
    const p = estado.produto || {};
    let bruto = campo === "price_2" ? (p.price_2 != null ? p.price_2 : p.preco2) : (p.price_1 != null ? p.price_1 : p.preco1);
    // usa preço/kg guardado se existir
    if (estado.precoKg != null && campo === "price_1") bruto = estado.precoKg;
    let n = parsePreco(bruto);
    if (isNaN(n)) return { texto: "—", sufixo: "" };
    let sufixo = "";
    if (p.venda_peso || p.by_weight) {
      if (estado.precoModo === "100g") {
        n = n / 10; // kg → 100 g
        sufixo = " (100g)";
      } else {
        sufixo = " O kilo";
      }
    }
    return { texto: formatPrecoBR(n), sufixo };
  }

  function valorCampo(campo) {
    const p = estado.produto || {};
    if (campo === "price_1" || campo === "price_2") {
      const pe = precoExibido(campo);
      return pe.texto + (pe.sufixo || "");
    }
    const mapa = {
      barcode: p.barcode || p.codigo || estado.codigo || "",
      description: p.description || p.descricao || p.nome || "",
    };
    let v = mapa[campo];
    if (v == null || v === "") return campo === "description" ? "Descrição do produto" : "—";
    return String(v);
  }

  function htmlCampo(campo) {
    const p = estado.produto || {};
    if (campo === "price_1" || campo === "price_2") {
      const pe = precoExibido(campo);
      const unid = (pe.sufixo || "").trim();
      if (!unid) return esc(pe.texto);
      return `<span class="fp-valor">${esc(pe.texto)}</span><span class="fp-unid">${esc(unid)}</span>`;
    }
    return esc(valorCampo(campo));
  }

  function srcImagemCamada(c) {
    if (c.tipo === "image_custom") {
      return (c.src || "").trim();
    }
    if (c.tipo === "image_product" && estado.codigo) {
      const key = "cosmos:" + estado.codigo;
      if (estado.imgCache[key]) return estado.imgCache[key];
      // URL estável (sem timestamp) — o browser cacheia
      return BASE + "/imagem-cosmos?codigo=" + encodeURIComponent(estado.codigo);
    }
    return "";
  }

  function prefetchCosmos(codigo) {
    if (!codigo) return;
    const key = "cosmos:" + codigo;
    if (estado.imgCache[key]) return;
    const url = BASE + "/imagem-cosmos?codigo=" + encodeURIComponent(codigo);
    // Prefetch como blob para URL object estável
    fetch(url)
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (!blob) return;
        if (estado.imgCache[key] && estado.imgCache[key].startsWith("blob:")) {
          try { URL.revokeObjectURL(estado.imgCache[key]); } catch (_) {}
        }
        estado.imgCache[key] = URL.createObjectURL(blob);
        // atualiza imgs existentes sem recriar o canvas inteiro
        document.querySelectorAll(".folha-camada-img img[data-key='" + key + "']").forEach((img) => {
          img.src = estado.imgCache[key];
        });
      })
      .catch(() => {});
  }

  function renderListaCamadas() {
    const ul = $("folha-lista-camadas");
    if (!ul || !estado.template) return;
    const cams = (estado.template.camadas || []).slice().sort((a, b) => (b.z || 0) - (a.z || 0));
    ul.innerHTML = cams
      .map((c) => {
        const ativa = c.id === estado.selecionada ? " ativa" : "";
        return `<li class="${ativa}" data-id="${esc(c.id)}">
          <span title="${esc(c.tipo)}">${esc(c.nome || c.tipo)}</span>
          <span class="z-btns">
            <button type="button" data-up="${esc(c.id)}" title="Trazer à frente">↑</button>
            <button type="button" data-down="${esc(c.id)}" title="Enviar para trás">↓</button>
            <button type="button" data-del="${esc(c.id)}" title="Remover">✕</button>
          </span>
        </li>`;
      })
      .join("");
    ul.querySelectorAll("li[data-id]").forEach((li) => {
      li.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        selecionar(li.dataset.id);
      });
    });
    ul.querySelectorAll("[data-up]").forEach((b) =>
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        moverZ(b.dataset.up, 1);
      })
    );
    ul.querySelectorAll("[data-down]").forEach((b) =>
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        moverZ(b.dataset.down, -1);
      })
    );
    ul.querySelectorAll("[data-del]").forEach((b) =>
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        removerCamada(b.dataset.del);
      })
    );
  }

  function moverZ(id, delta) {
    const c = (estado.template.camadas || []).find((x) => x.id === id);
    if (!c) return;
    c.z = (c.z || 0) + delta;
    renderTudo();
  }

  function removerCamada(id) {
    estado.template.camadas = (estado.template.camadas || []).filter((c) => c.id !== id);
    if (estado.selecionada === id) estado.selecionada = null;
    renderTudo();
  }

  function selecionar(id) {
    estado.selecionada = id;
    // atualiza só classes e handles, sem destruir imagens
    document.querySelectorAll(".folha-camada").forEach((el) => {
      const on = el.dataset.id === id;
      el.classList.toggle("selecionada", on);
      el.querySelectorAll(".handle").forEach((h) => h.remove());
      if (on) {
        ["nw", "ne", "sw", "se"].forEach((pos) => {
          const h = document.createElement("div");
          h.className = "handle handle-" + pos;
          h.dataset.handle = pos;
          el.appendChild(h);
        });
      }
    });
    renderListaCamadas();
    renderProps();
  }

  function renderProps() {
    const box = $("folha-props");
    const corpo = $("folha-props-corpo");
    const c = (estado.template.camadas || []).find((x) => x.id === estado.selecionada);
    if (!c) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    const tipo = c.tipo;
    let extra = "";
    if (tipo === "text") {
      extra = `<div class="prop-linha"><span>Texto</span><input data-k="texto" value="${esc(c.texto || "")}"></div>`;
    }
    if (tipo === "text_field") {
      const opts = ((estado.meta && estado.meta.campos_produto) || [])
        .map(
          (f) =>
            `<option value="${esc(f.id)}" ${c.campo === f.id ? "selected" : ""}>${esc(f.rotulo)}</option>`
        )
        .join("");
      extra = `<div class="prop-linha"><span>Campo</span><select data-k="campo">${opts}</select></div>`;
    }
    if (tipo === "text" || tipo === "text_field") {
      extra += `
        <div class="prop-linha"><span>Fonte mm</span><input type="number" step="0.5" min="1" data-k="fonte_mm" value="${esc(c.fonte_mm || 5)}"></div>
        <div class="prop-linha"><span>Cor</span><input type="color" data-k="cor" value="${esc((c.cor && c.cor !== "transparent") ? c.cor : "#000000")}" ${c.cor === "transparent" ? "disabled" : ""}></div>
        <div class="prop-linha"><span></span><label class="folha-check-inline"><input type="checkbox" data-k="cor_transp" ${c.cor === "transparent" ? "checked" : ""}> Transparente</label></div>
        <div class="prop-linha"><span>Alinhar</span>
          <select data-k="align">
            <option value="left" ${c.align === "left" ? "selected" : ""}>Esquerda</option>
            <option value="center" ${c.align === "center" ? "selected" : ""}>Centro</option>
            <option value="right" ${c.align === "right" ? "selected" : ""}>Direita</option>
          </select>
        </div>
        <div class="prop-linha"><span>Negrito</span><input type="checkbox" data-k="negrito" ${c.negrito ? "checked" : ""}></div>`;
    }
    if (tipo === "rect") {
      extra = `
        <div class="prop-linha"><span>Fundo</span><input type="color" data-k="cor_fundo" value="${esc((c.cor_fundo && c.cor_fundo !== "transparent") ? c.cor_fundo : "#eeeeee")}" ${c.cor_fundo === "transparent" ? "disabled" : ""}></div>
        <div class="prop-linha"><span></span><label class="folha-check-inline"><input type="checkbox" data-k="fundo_transp" ${c.cor_fundo === "transparent" ? "checked" : ""}> Fundo transparente</label></div>
        <div class="prop-linha"><span>Borda</span><input type="color" data-k="cor_borda" value="${esc((c.cor_borda && c.cor_borda !== "transparent") ? c.cor_borda : "#000000")}" ${c.cor_borda === "transparent" ? "disabled" : ""}></div>
        <div class="prop-linha"><span></span><label class="folha-check-inline"><input type="checkbox" data-k="borda_transp" ${c.cor_borda === "transparent" ? "checked" : ""}> Borda transparente</label></div>`;
    }
    if (tipo === "image_product" || tipo === "image_custom") {
      const locked = c.trava_proporcao !== false;
      const fit = c.object_fit || "contain";
      extra = `
        <div class="prop-linha"><span>Proporção</span>
          <label class="folha-check-inline">
            <input type="checkbox" data-k="trava_proporcao" ${locked ? "checked" : ""}>
            travada
          </label>
        </div>
        <div class="prop-linha"><span>Ajuste</span>
          <select data-k="object_fit">
            <option value="contain" ${fit === "contain" ? "selected" : ""}>Conter</option>
            <option value="cover" ${fit === "cover" ? "selected" : ""}>Cobrir</option>
            <option value="fill_height" ${fit === "fill_height" ? "selected" : ""}>Preencher vertical</option>
            <option value="fill_width" ${fit === "fill_width" ? "selected" : ""}>Preencher horizontal</option>
          </select>
        </div>
        <button type="button" class="botao botao--fantasma" id="folha-fill-vert" style="margin-top:.25rem">Preencher folha na vertical</button>`;
      if (tipo === "image_custom") {
        extra += `<p class="meta-img">Origem: ${c.src && c.src.startsWith("http") ? "URL" : "arquivo"}</p>`;
      } else {
        extra += `<p class="meta-img">Cosmos (EAN).</p>`;
      }
    }
    corpo.innerHTML = `
      <div class="prop-linha"><span>Nome</span><input data-k="nome" value="${esc(c.nome || "")}"></div>
      <div class="prop-linha"><span>X mm</span><input type="number" step="0.5" data-k="x_mm" value="${esc(c.x_mm || 0)}"></div>
      <div class="prop-linha"><span>Y mm</span><input type="number" step="0.5" data-k="y_mm" value="${esc(c.y_mm || 0)}"></div>
      <div class="prop-linha"><span>Larg. mm</span><input type="number" step="0.5" data-k="largura_mm" value="${esc(c.largura_mm || 10)}"></div>
      <div class="prop-linha"><span>Alt. mm</span><input type="number" step="0.5" data-k="altura_mm" value="${esc(c.altura_mm || 10)}"></div>
      ${extra}`;
    corpo.querySelectorAll("[data-k]").forEach((el) => {
      const ev = el.type === "checkbox" || el.tagName === "SELECT" ? "change" : "input";
      el.addEventListener(ev, () => {
        const k = el.dataset.k;
        let v = el.type === "checkbox" ? el.checked : el.value;
        if (["x_mm", "y_mm", "largura_mm", "altura_mm", "fonte_mm"].includes(k)) v = parseFloat(v) || 0;
        if (k === "cor_transp") {
          c.cor = v ? "transparent" : (corpo.querySelector('[data-k="cor"]') || {}).value || "#000000";
          renderCanvas();
          renderProps();
          return;
        }
        if (k === "fundo_transp") {
          c.cor_fundo = v ? "transparent" : (corpo.querySelector('[data-k="cor_fundo"]') || {}).value || "#eeeeee";
          renderCanvas();
          renderProps();
          return;
        }
        if (k === "borda_transp") {
          c.cor_borda = v ? "transparent" : (corpo.querySelector('[data-k="cor_borda"]') || {}).value || "#000000";
          renderCanvas();
          renderProps();
          return;
        }
        c[k] = v;
        aplicarGeomNoDom(c);
        if (["texto", "campo", "cor", "fonte_mm", "negrito", "align", "cor_fundo", "cor_borda", "nome", "object_fit"].includes(k)) {
          renderCanvas();
        }
        renderListaCamadas();
      });
    });
    const btnFill = $("folha-fill-vert");
    if (btnFill) {
      btnFill.onclick = () => {
        preencherVertical(c);
        renderTudo();
      };
    }
  }

  function preencherVertical(c) {
    if (!c || !estado.template) return;
    const p = estado.template.papel || papelAtual();
    const pageH = Number(p.altura_mm) || 297;
    const pageW = Number(p.largura_mm) || 210;
    // encaixa a caixa exatamente na folha (sem sair do papel)
    c.x_mm = 0;
    c.y_mm = 0;
    c.largura_mm = pageW;
    c.altura_mm = pageH;
    // cover: preenche a altura (e a largura) da folha, cortando o excesso se preciso
    c.object_fit = "cover";
    c.trava_proporcao = true;
  }

  function aplicarGeomNoDom(c) {
    const el = document.querySelector('.folha-camada[data-id="' + c.id + '"]');
    if (!el) return;
    const s = estado.pxPorMm;
    el.style.left = (c.x_mm || 0) * s + "px";
    el.style.top = (c.y_mm || 0) * s + "px";
    el.style.width = (c.largura_mm || 10) * s + "px";
    el.style.height = (c.altura_mm || 10) * s + "px";
  }

  function limparGuias() {
    const folha = $("folha-folha");
    if (!folha) return;
    folha.querySelectorAll(".folha-guia").forEach((g) => g.remove());
  }

  function mostrarGuias(xs, ys) {
    const folha = $("folha-folha");
    if (!folha) return;
    limparGuias();
    const s = estado.pxPorMm;
    const p = estado.template.papel;
    const cx = p.largura_mm / 2;
    const cy = p.altura_mm / 2;
    const near = (a, b) => Math.abs(a - b) < 0.05;
    (xs || []).forEach((xmm) => {
      const g = document.createElement("div");
      g.className = "folha-guia folha-guia-v" + (near(xmm, cx) ? " folha-guia-centro" : "");
      g.style.left = xmm * s + "px";
      g.style.height = p.altura_mm * s + "px";
      folha.appendChild(g);
    });
    (ys || []).forEach((ymm) => {
      const g = document.createElement("div");
      g.className = "folha-guia folha-guia-h" + (near(ymm, cy) ? " folha-guia-centro" : "");
      g.style.top = ymm * s + "px";
      g.style.width = p.largura_mm * s + "px";
      folha.appendChild(g);
    });
  }

  function guiasAlvo(excetoId) {
    const p = estado.template.papel;
    const xs = [0, p.largura_mm / 2, p.largura_mm];
    const ys = [0, p.altura_mm / 2, p.altura_mm];
    (estado.template.camadas || []).forEach((c) => {
      if (c.id === excetoId || c.visivel === false) return;
      const x = c.x_mm || 0;
      const y = c.y_mm || 0;
      const w = c.largura_mm || 0;
      const h = c.altura_mm || 0;
      xs.push(x, x + w / 2, x + w);
      ys.push(y, y + h / 2, y + h);
    });
    return { xs, ys };
  }

  function snapValor(val, alvos, s) {
    const thr = SNAP / s;
    let best = val;
    let dist = thr + 1;
    let hit = null;
    alvos.forEach((a) => {
      const d = Math.abs(val - a);
      if (d < dist && d <= thr) {
        dist = d;
        best = a;
        hit = a;
      }
    });
    return { val: best, hit };
  }


  function ajustarCaixaTexto(c, el) {
    if (!c || !el || (c.tipo !== "text" && c.tipo !== "text_field")) return;
    const s = estado.pxPorMm;
    const align = (c.align || "left").toLowerCase();
    const oldW = c.largura_mm || 10;
    const oldH = c.altura_mm || 10;
    const left = c.x_mm || 0;
    const top = c.y_mm || 0;
    const cx = left + oldW / 2;
    const right = left + oldW;

    // mede fora do fluxo para não bagunçar o layout
    const clone = el.cloneNode(true);
    clone.style.position = "absolute";
    clone.style.visibility = "hidden";
    clone.style.left = "-9999px";
    clone.style.top = "0";
    clone.style.width = "auto";
    clone.style.height = "auto";
    clone.style.maxWidth = "none";
    clone.style.whiteSpace = "pre-wrap";
    clone.querySelectorAll(".handle").forEach((h) => h.remove());
    document.body.appendChild(clone);
    const pad = 6;
    const tw = Math.ceil(clone.scrollWidth + pad);
    const th = Math.ceil(clone.scrollHeight + pad);
    clone.remove();

    if (tw > 4 && th > 4) {
      c.largura_mm = Math.round((tw / s) * 10) / 10;
      c.altura_mm = Math.round((th / s) * 10) / 10;
      if (align === "center") {
        c.x_mm = Math.round((cx - c.largura_mm / 2) * 10) / 10;
      } else if (align === "right") {
        c.x_mm = Math.round((right - c.largura_mm) * 10) / 10;
      }
      // top permanece (âncora superior)
      aplicarGeomNoDom(c);
    }
  }

  function renderCanvas() {
    const folha = $("folha-folha");
    if (!folha || !estado.template) return;
    syncPapelNoTemplate();
    const p = estado.template.papel;
    const s = estado.pxPorMm;
    folha.style.width = p.largura_mm * s + "px";
    folha.style.height = p.altura_mm * s + "px";
    folha.style.background = estado.template.cor_fundo || "#ffffff";

    // Preserve existing image elements by key to avoid blink
    const oldImgs = {};
    folha.querySelectorAll(".folha-camada-img img").forEach((img) => {
      if (img.dataset.key) oldImgs[img.dataset.key] = img;
    });

    const cams = (estado.template.camadas || []).slice().sort((a, b) => (a.z || 0) - (b.z || 0));
    folha.innerHTML = "";
    cams.forEach((c) => {
      if (c.visivel === false) return;
      const div = document.createElement("div");
      div.className = "folha-camada" + (c.id === estado.selecionada ? " selecionada" : "");
      div.dataset.id = c.id;
      div.style.left = (c.x_mm || 0) * s + "px";
      div.style.top = (c.y_mm || 0) * s + "px";
      div.style.width = (c.largura_mm || 10) * s + "px";
      div.style.height = (c.altura_mm || 10) * s + "px";
      div.style.zIndex = String(c.z || 0);

      if (c.tipo === "rect") {
        div.style.background = (!c.cor_fundo || c.cor_fundo === "transparent") ? "transparent" : c.cor_fundo;
        div.style.border = (!c.cor_borda || c.cor_borda === "transparent")
          ? "1px solid transparent"
          : ("1px solid " + c.cor_borda);
      } else if (c.tipo === "image_product" || c.tipo === "image_custom") {
        div.classList.add("folha-camada-img");
        const fit = (c.object_fit || "contain").toLowerCase();
        if (fit === "cover" || fit === "fill_height" || fit === "fill_width") {
          div.classList.add("fit-cover");
        }
        if (fit === "fill_height") div.classList.add("fit-fill-height");
        div.style.background = "transparent";
        const src = srcImagemCamada(c);
        const key =
          c.tipo === "image_product"
            ? "cosmos:" + (estado.codigo || "")
            : "custom:" + (c.src || c.id);
        if (src) {
          let img = oldImgs[key];
          if (img) {
            // reutiliza o mesmo <img> (já carregado)
            img = img.cloneNode(true);
          } else {
            img = document.createElement("img");
            img.alt = "img";
            img.dataset.key = key;
            img.src = estado.imgCache[key] || src;
            if (c.tipo === "image_product" && estado.codigo) {
              prefetchCosmos(estado.codigo);
            }
          }
          img.onerror = () => {
            img.remove();
            div.textContent = "Sem imagem";
            div.style.color = "#999";
            div.style.fontSize = "12px";
          };
          div.appendChild(img);
        } else {
          div.textContent = c.tipo === "image_product" ? "Foto (EAN)" : "Imagem";
          div.style.color = "#999";
          div.style.fontSize = "12px";
          div.style.background =
            "repeating-conic-gradient(#eee 0% 25%, #fafafa 0% 50%) 50% / 16px 16px";
        }
      } else {
        div.classList.add("folha-camada-text");
        if (c.tipo === "text_field") {
          div.innerHTML = htmlCampo(c.campo || "description");
        } else {
          div.textContent = c.texto || "";
        }
        div.style.color = (!c.cor || c.cor === "transparent") ? "transparent" : c.cor;
        div.style.fontWeight = c.negrito ? "700" : "400";
        div.style.fontSize = Math.max(8, (c.fonte_mm || 5) * s) + "px";
        div.style.alignItems =
          c.align === "center" ? "center" : c.align === "right" ? "flex-end" : "flex-start";
        div.style.justifyContent = "flex-start";
        div.style.textAlign = c.align || "left";
      }

      if (c.id === estado.selecionada) {
        ["nw", "ne", "sw", "se"].forEach((pos) => {
          const h = document.createElement("div");
          h.className = "handle handle-" + pos;
          h.dataset.handle = pos;
          div.appendChild(h);
        });
      }

      div.addEventListener("mousedown", (ev) => iniciarArraste(ev, c, div));
      folha.appendChild(div);
    });
  }

  function iniciarArraste(ev, camada, div) {
    if (ev.button !== 0) return;
    ev.preventDefault();
    selecionar(camada.id);
    const handle = ev.target.dataset.handle || null;
    const s = estado.pxPorMm;
    const isText = camada.tipo === "text" || camada.tipo === "text_field";
    const ratioLocked =
      (camada.tipo === "image_product" || camada.tipo === "image_custom") &&
      camada.trava_proporcao !== false
        ? (camada.largura_mm || 10) / Math.max(0.1, camada.altura_mm || 10)
        : null;
    estado.arraste = {
      id: camada.id,
      handle,
      startX: ev.clientX,
      startY: ev.clientY,
      origX: camada.x_mm || 0,
      origY: camada.y_mm || 0,
      origW: camada.largura_mm || 10,
      origH: camada.altura_mm || 10,
      origFonte: camada.fonte_mm || 5,
      isText,
      ratio: ratioLocked,
    };

    const move = (e) => {
      const a = estado.arraste;
      if (!a) return;
      const dx = (e.clientX - a.startX) / s;
      const dy = (e.clientY - a.startY) / s;
      const c = (estado.template.camadas || []).find((x) => x.id === a.id);
      if (!c) return;
      const alvos = guiasAlvo(a.id);
      const hitX = [];
      const hitY = [];

      if (a.handle) {
        let x = a.origX, y = a.origY, w = a.origW, h = a.origH;
        if (a.handle.includes("e")) w = a.origW + dx;
        if (a.handle.includes("s")) h = a.origH + dy;
        if (a.handle.includes("w")) { w = a.origW - dx; x = a.origX + dx; }
        if (a.handle.includes("n")) { h = a.origH - dy; y = a.origY + dy; }
        if (a.ratio) {
          if (Math.abs(dx) >= Math.abs(dy)) {
            h = w / a.ratio;
            if (a.handle.includes("n")) y = a.origY + a.origH - h;
          } else {
            w = h * a.ratio;
            if (a.handle.includes("w")) x = a.origX + a.origW - w;
          }
        }
        w = Math.max(2, w);
        h = Math.max(2, h);
        const sL = snapValor(x, alvos.xs, s);
        const sT = snapValor(y, alvos.ys, s);
        const sR = snapValor(x + w, alvos.xs, s);
        const sB = snapValor(y + h, alvos.ys, s);
        if (sL.hit != null) { w += x - sL.val; x = sL.val; hitX.push(sL.hit); }
        if (sT.hit != null) { h += y - sT.val; y = sT.val; hitY.push(sT.hit); }
        if (sR.hit != null) { w = sR.val - x; hitX.push(sR.hit); }
        if (sB.hit != null) { h = sB.val - y; hitY.push(sB.hit); }
        c.x_mm = Math.round(x * 10) / 10;
        c.y_mm = Math.round(y * 10) / 10;
        c.largura_mm = Math.round(Math.max(2, w) * 10) / 10;
        c.altura_mm = Math.round(Math.max(2, h) * 10) / 10;
        if (a.isText && a.origH > 0) {
          // escala a fonte com a altura do quadro
          const scale = c.altura_mm / a.origH;
          c.fonte_mm = Math.round(Math.max(1.5, a.origFonte * scale) * 10) / 10;
          const el = document.querySelector('.folha-camada[data-id="' + c.id + '"]');
          if (el) {
            el.style.fontSize = Math.max(8, c.fonte_mm * s) + "px";
            // ajusta largura ao texto se possível
            ajustarCaixaTexto(c, el);
          }
        }
      } else {
        let nx = a.origX + dx;
        let ny = a.origY + dy;
        const w = a.origW, h = a.origH;
        const p = estado.template.papel;
        const pageCx = p.largura_mm / 2;
        const pageCy = p.altura_mm / 2;
        // prioriza centro da página (horizontal e vertical)
        const thr = SNAP / s;
        const elCx = nx + w / 2;
        const elCy = ny + h / 2;
        if (Math.abs(elCx - pageCx) <= thr) {
          nx = pageCx - w / 2;
          hitX.push(pageCx);
        } else {
          const sL = snapValor(nx, alvos.xs, s);
          const sC = snapValor(nx + w / 2, alvos.xs, s);
          const sR = snapValor(nx + w, alvos.xs, s);
          const candX = [
            { d: Math.abs(sC.val - (nx + w / 2)), v: sC.val - w / 2, hit: sC.hit },
            { d: Math.abs(sL.val - nx), v: sL.val, hit: sL.hit },
            { d: Math.abs(sR.val - (nx + w)), v: sR.val - w, hit: sR.hit },
          ].sort((aa, bb) => aa.d - bb.d)[0];
          if (candX.hit != null && candX.d <= thr) { nx = candX.v; hitX.push(candX.hit); }
        }
        if (Math.abs(elCy - pageCy) <= thr) {
          ny = pageCy - h / 2;
          hitY.push(pageCy);
        } else {
          const sT = snapValor(ny, alvos.ys, s);
          const sM = snapValor(ny + h / 2, alvos.ys, s);
          const sB = snapValor(ny + h, alvos.ys, s);
          const candY = [
            { d: Math.abs(sM.val - (ny + h / 2)), v: sM.val - h / 2, hit: sM.hit },
            { d: Math.abs(sT.val - ny), v: sT.val, hit: sT.hit },
            { d: Math.abs(sB.val - (ny + h)), v: sB.val - h, hit: sB.hit },
          ].sort((aa, bb) => aa.d - bb.d)[0];
          if (candY.hit != null && candY.d <= thr) { ny = candY.v; hitY.push(candY.hit); }
        }
        c.x_mm = Math.round(nx * 10) / 10;
        c.y_mm = Math.round(ny * 10) / 10;
      }
      // NÃO rebuilda o canvas — só geometria + guias (evita piscar branco)
      aplicarGeomNoDom(c);
      mostrarGuias(hitX, hitY);
      // props números
      const corpo = $("folha-props-corpo");
      if (corpo && estado.selecionada === c.id) {
        corpo.querySelectorAll("[data-k]").forEach((el) => {
          const k = el.dataset.k;
          if (["x_mm", "y_mm", "largura_mm", "altura_mm"].includes(k) && el.type !== "checkbox") {
            el.value = c[k];
          }
        });
      }
    };

    const up = () => {
      const a = estado.arraste;
      estado.arraste = null;
      limparGuias();
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      // só aperta a caixa se houve redimensionamento pelos handles
      if (a && a.isText && a.handle) {
        const c = (estado.template.camadas || []).find((x) => x.id === a.id);
        const el = c && document.querySelector('.folha-camada[data-id="' + c.id + '"]');
        if (c && el) ajustarCaixaTexto(c, el);
        renderProps();
      }
      renderListaCamadas();
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  function renderTudo() {
    renderListaCamadas();
    renderCanvas();
    renderProps();
  }

  function addCamada(tipo, extra) {
    if (!estado.template) return;
    const zs = (estado.template.camadas || []).map((c) => c.z || 0);
    const z = zs.length ? Math.max(...zs) + 1 : 0;
    const base = {
      id: uid(tipo),
      nome: tipo,
      tipo,
      x_mm: 20,
      y_mm: 40,
      largura_mm: 80,
      altura_mm: 80,
      z,
      visivel: true,
      trava_proporcao: true,
    };
    if (tipo === "text") {
      Object.assign(base, { texto: "Novo texto", fonte_mm: 5, cor: "#000000", align: "left", nome: "Texto", largura_mm: 60, altura_mm: 15 });
    } else if (tipo === "text_field") {
      Object.assign(base, { campo: "description", fonte_mm: 5, cor: "#000000", align: "left", nome: "Campo produto", largura_mm: 60, altura_mm: 15 });
    } else if (tipo === "image_product") {
      Object.assign(base, { nome: "Foto Cosmos" });
    } else if (tipo === "image_custom") {
      Object.assign(base, { nome: "Imagem", src: (extra && extra.src) || "" });
    } else if (tipo === "rect") {
      Object.assign(base, { cor_fundo: "#e3f2fd", cor_borda: "#1d6fe0", nome: "Retângulo", altura_mm: 30, trava_proporcao: false });
    }
    estado.template.camadas.push(base);
    return base;
  }

  function abrirModalImg(idCamada) {
    estado.pendingCustomId = idCamada;
    $("folha-img-url").value = "";
    $("folha-file-img").value = "";
    $("folha-modal-img").hidden = false;
  }

  function fecharModalImg(aplicar) {
    $("folha-modal-img").hidden = true;
    const id = estado.pendingCustomId;
    estado.pendingCustomId = null;
    if (!aplicar && id) {
      // cancelou → remove elemento criado
      removerCamada(id);
    }
  }

  async function aplicarImgModal() {
    const id = estado.pendingCustomId;
    if (!id) return;
    const c = (estado.template.camadas || []).find((x) => x.id === id);
    if (!c) return;
    const file = $("folha-file-img").files && $("folha-file-img").files[0];
    const url = ($("folha-img-url").value || "").trim();
    if (!file && !url) {
      alert("Selecione um arquivo ou informe uma URL.");
      return;
    }
    try {
      if (file) {
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch(BASE + "/upload", { method: "POST", body: fd });
        const j = await r.json();
        if (!r.ok || !j.ok) throw new Error(j.detail || "Falha no upload");
        c.src = j.url;
      } else {
        c.src = url;
      }
      estado.pendingCustomId = null;
      $("folha-modal-img").hidden = true;
      selecionar(c.id);
      renderTudo();
    } catch (e) {
      alert(e.message || String(e));
    }
  }

  async function carregarTemplates() {
    const sel = $("folha-template-sel");
    if (!sel) return;
    const r = await api("/templates");
    const atual = sel.value;
    sel.innerHTML = '<option value="">— novo —</option>';
    (r.templates || []).forEach((t) => {
      const o = document.createElement("option");
      o.value = t.id;
      o.textContent = t.nome + (t.papel ? " (" + t.papel + ")" : "");
      sel.appendChild(o);
    });
    if (atual) sel.value = atual;
  }

  function modoBusca(q) {
    const t = (q != null ? q : ($("folha-codigo").value || "")).trim();
    if (!t) return "desc";
    const digitos = t.replace(/\D/g, "");
    const letras = t.replace(/[0-9\s.\-_/]/g, "");
    // predominantemente código (EAN, balança, interno) → busca por código
    if (digitos.length >= 2 && letras.length <= 3) return "codigo";
    return "desc";
  }

  function atualizarPrecoModoUI() {
    const wrap = $("folha-preco-modo-wrap");
    if (!wrap) return;
    const p = estado.produto || {};
    const peso = !!(p.venda_peso || p.by_weight);
    wrap.hidden = !peso;
    if (!peso) {
      estado.precoModo = "kg";
      return;
    }
    const sel = document.querySelector('input[name="folha-preco-modo"]:checked');
    if (sel) estado.precoModo = sel.value;
    else estado.precoModo = "kg";
  }

  function aplicarProdutoEscolhido(item) {
    const codigo = (item.barcode || "").trim();
    estado.codigo = codigo;
    const vendaPeso = item.venda_peso === true || item.by_weight === true;
    estado.produto = {
      barcode: item.barcode,
      description: item.description,
      price_1: item.price_1,
      price_2: item.price_2,
      venda_peso: vendaPeso,
      by_weight: !!item.by_weight,
    };
    estado.precoKg = item.price_1;
    estado.precoModo = "kg";
    const rKg = document.querySelector('input[name="folha-preco-modo"][value="kg"]');
    if (rKg) rKg.checked = true;
    $("folha-codigo").value = codigo;
    $("folha-prod-status").textContent =
      (item.description || codigo) +
      (item.price_1 != null ? " · " + formatPrecoBR(parsePreco(item.price_1)) : "") +
      (vendaPeso ? " · peso" : "");
    atualizarPrecoModoUI();
    prefetchCosmos(codigo);
    renderCanvas();
    fecharModalProd();
  }

  function fecharModalProd() {
    const m = $("folha-modal-prod");
    if (m) m.hidden = true;
  }

  function abrirModalProd(titulo, sub, itens) {
    $("folha-modal-prod-titulo").textContent = titulo;
    $("folha-modal-prod-sub").textContent = sub || "";
    const ul = $("folha-prod-lista");
    ul.innerHTML = (itens || [])
      .map((it, i) => {
        const preco =
          it.price_1 != null && it.price_1 !== ""
            ? " · R$ " + it.price_1
            : "";
        const pesoTag = it.venda_peso ? " · peso/kg" : "";
        return `<li data-i="${i}">
          <span>${esc(it.description || "(sem descrição)")}${esc(preco)}${pesoTag}</span>
          <span class="ean">${esc(it.barcode || "")}</span>
        </li>`;
      })
      .join("");
    if (!itens || !itens.length) {
      ul.innerHTML = '<li style="cursor:default;opacity:.7">Nenhum produto encontrado.</li>';
    } else {
      ul.querySelectorAll("li[data-i]").forEach((li) => {
        li.addEventListener("click", () => aplicarProdutoEscolhido(itens[Number(li.dataset.i)]));
      });
    }
    $("folha-modal-prod").hidden = false;
  }

  async function buscarProduto() {
    const q = ($("folha-codigo").value || "").trim();
    const modo = modoBusca(q);
    if (!q) {
      $("folha-prod-status").textContent = "Informe o código (EAN, balança ou interno) ou a descrição.";
      return;
    }
    $("folha-prod-status").textContent = "Consultando…";
    try {
      // 1) sempre tenta match direto pelo código digitado (balança, PLU, EAN, etc.)
      try {
        const r0 = await api("/produto?codigo=" + encodeURIComponent(q));
        if (r0.ok && r0.produto) {
          aplicarProdutoEscolhido({
            barcode: r0.produto.barcode || q,
            description: r0.produto.description,
            price_1: r0.produto.price_1,
            price_2: r0.produto.price_2,
            venda_peso: r0.produto.venda_peso,
            by_weight: r0.produto.by_weight,
          });
          return;
        }
      } catch (_) {
        /* segue para lista */
      }

      if (modo === "codigo") {
        const r = await api(
          "/buscar?modo=codigo&q=" + encodeURIComponent(q) + "&limit=40"
        );
        if (r.exato && r.itens && r.itens[0]) {
          aplicarProdutoEscolhido(r.itens[0]);
          return;
        }
        abrirModalProd(
          "Produtos com código parecido",
          'Busca por "' + q + '" (EAN, balança ou cadastro)',
          r.itens || []
        );
        $("folha-prod-status").textContent =
          (r.itens || []).length + " resultado(s) — escolha na lista.";
      } else {
        const r = await api(
          "/buscar?modo=desc&q=" + encodeURIComponent(q) + "&limit=40"
        );
        abrirModalProd(
          "Busca por descrição",
          'Resultados para "' + q + '" (ignora acentos)',
          r.itens || []
        );
        $("folha-prod-status").textContent =
          (r.itens || []).length + " resultado(s).";
      }
    } catch (e) {
      $("folha-prod-status").textContent = e.message || String(e);
    }
  }

  async function salvar() {
    syncPapelNoTemplate();
    estado.template.nome = ($("folha-tpl-nome").value || "").trim() || "Template";
    const r = await api("/templates", {
      method: "POST",
      body: JSON.stringify({ template: estado.template }),
    });
    estado.template.id = r.id;
    await carregarTemplates();
    if (window.TC && TC.aviso) TC.aviso(r.detail || "Projeto salvo.");
    else alert(r.detail || "Projeto salvo.");
  }

  async function exportarArquivoTemplate() {
    syncPapelNoTemplate();
    const temCustom = (estado.template.camadas || []).some(
      (c) => c.tipo === "image_custom" && c.src
    );
    try {
      if (temCustom) {
        const r = await fetch(BASE + "/template/export-zip", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ template: estado.template }),
        });
        if (!r.ok) {
          let msg = r.statusText;
          try { const j = await r.json(); msg = j.detail || msg; } catch (_) {}
          throw new Error(msg);
        }
        const blob = await r.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = ((estado.template.nome || "template") + ".zip").replace(/\s+/g, "_");
        a.click();
        URL.revokeObjectURL(a.href);
      } else {
        const blob = new Blob([JSON.stringify(estado.template, null, 2)], {
          type: "application/json",
        });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = ((estado.template.nome || "template") + ".json").replace(/\s+/g, "_");
        a.click();
        URL.revokeObjectURL(a.href);
      }
    } catch (e) {
      alert("Falha ao exportar: " + (e.message || e));
    }
  }

  function setProjetoAtivo(on) {
    estado.projetoAtivo = !!on;
    const shell = document.querySelector(".folha-shell");
    if (shell) shell.classList.toggle("folha-shell--bloqueado", !estado.projetoAtivo);
    const vazio = $("folha-canvas-vazio");
    if (vazio) vazio.hidden = estado.projetoAtivo;
    if (!estado.projetoAtivo) {
      estado.selecionada = null;
    }
  }

  function abrirModalInicio() {
    const wrap = $("folha-inicio-lista-wrap");
    if (wrap) wrap.hidden = true;
    $("folha-modal-inicio").hidden = false;
  }

  function fecharModalInicio() {
    $("folha-modal-inicio").hidden = true;
    if (!estado.projetoAtivo) setProjetoAtivo(false);
  }

  async function importarArquivoTemplate(file) {
    try {
      const nome = (file.name || "").toLowerCase();
      let tpl = null;
      if (nome.endsWith(".zip")) {
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch(BASE + "/template/import-zip", { method: "POST", body: fd });
        const j = await r.json();
        if (!r.ok || !j.ok) throw new Error(j.detail || "Falha no import");
        tpl = j.template;
        if (!tpl || !Array.isArray(tpl.camadas)) throw new Error("Template inválido no ZIP.");
        if (!tpl.papel) tpl.papel = { tipo: "A4", largura_mm: 210, altura_mm: 297 };
        aplicarTemplate(tpl);
        setProjetoAtivo(true);
        if (j.id) estado.template.id = j.id;
        await carregarTemplates();
        if (window.TC && TC.aviso) TC.aviso("Template importado e salvo.");
        else alert("Template importado e salvo.");
      } else {
        const text = await file.text();
        const data = JSON.parse(text);
        tpl = data.template || data;
        if (!tpl || !Array.isArray(tpl.camadas)) throw new Error("JSON inválido: falta camadas.");
        if (!tpl.papel) tpl.papel = { tipo: "A4", largura_mm: 210, altura_mm: 297 };
        aplicarTemplate(tpl);
        setProjetoAtivo(true);
        await salvar();
      }
    } catch (e) {
      alert("Falha ao importar: " + (e.message || e));
    }
  }

  async function exportar(formato) {
    syncPapelNoTemplate();
    const codigo = ($("folha-codigo").value || "").trim();
    const r = await fetch(BASE + "/exportar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: estado.template,
        codigo,
        formato,
        dpi: 150,
        preco_modo: estado.precoModo || "kg",
        venda_peso: !!(estado.produto && (estado.produto.venda_peso || estado.produto.by_weight)),
      }),
    });
    if (!r.ok) {
      let msg = r.statusText;
      try { const j = await r.json(); msg = j.detail || msg; } catch (_) {}
      alert(msg);
      return null;
    }
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const ext = formato === "pdf" ? ".pdf" : formato === "jpg" || formato === "jpeg" ? ".jpg" : ".png";
    a.download = (estado.template.nome || "cartaz") + ext;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    return blob;
  }

  async function imprimirCartaz() {
    syncPapelNoTemplate();
    const codigo = ($("folha-codigo").value || "").trim();
    const r = await fetch(BASE + "/exportar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: estado.template,
        codigo,
        formato: "png",
        dpi: 200,
        preco_modo: estado.precoModo || "kg",
        venda_peso: !!(estado.produto && (estado.produto.venda_peso || estado.produto.by_weight)),
      }),
    });
    if (!r.ok) {
      let msg = r.statusText;
      try { const j = await r.json(); msg = j.detail || msg; } catch (_) {}
      throw new Error(msg);
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);

    let iframe = document.getElementById("folha-print-frame");
    if (!iframe) {
      iframe = document.createElement("iframe");
      iframe.id = "folha-print-frame";
      iframe.setAttribute("aria-hidden", "true");
      iframe.style.cssText =
        "position:fixed;right:0;bottom:0;width:0;height:0;border:0;opacity:0;pointer-events:none;";
      document.body.appendChild(iframe);
    }

    const doc = iframe.contentWindow.document;
    doc.open();
    doc.write(
      "<!DOCTYPE html><html><head><title>Imprimir</title>" +
        "<style>" +
        "html,body{margin:0;padding:0;background:#fff;}" +
        "img{display:block;width:100%;height:auto;}" +
        "@page{margin:0;}" +
        "@media print{html,body{margin:0;width:100%;}img{width:100%;}}" +
        "</style></head><body>" +
        '<img id="cartaz" src="' + url + '" alt="cartaz"/>' +
        "<script>(function(){" +
        "var i=document.getElementById('cartaz');" +
        "function go(){try{window.focus();window.print();}catch(e){}}" +
        "if(i.complete){setTimeout(go,100);}else{i.onload=function(){setTimeout(go,100);};}" +
        "})();<\/script></body></html>"
    );
    doc.close();

    setTimeout(function () {
      try { URL.revokeObjectURL(url); } catch (_) {}
    }, 120000);
  }


  function aplicarTemplate(tpl) {
    estado.template = JSON.parse(JSON.stringify(tpl));
    (estado.template.camadas || []).forEach((c) => {
      if ((c.tipo === "image_product" || c.tipo === "image_custom") && c.trava_proporcao === undefined) {
        c.trava_proporcao = true;
      }
    });
    $("folha-tpl-nome").value = estado.template.nome || "";
    const papel = estado.template.papel || { tipo: "A4" };
    $("folha-papel").value = papel.tipo || "A4";
    $("folha-w").value = papel.largura_mm || 210;
    $("folha-h").value = papel.altura_mm || 297;
    $("folha-custom-size").hidden = (papel.tipo || "A4") !== "custom";
    $("folha-fundo").value = estado.template.cor_fundo || "#ffffff";
    estado.selecionada = null;
    renderTudo();
  }

  async function init() {
    const meta = await api("/meta");
    estado.meta = meta;
    const selPapel = $("folha-papel");
    selPapel.innerHTML = "";
    Object.keys(meta.papeis || {}).forEach((k) => {
      const o = document.createElement("option");
      o.value = k;
      o.textContent = meta.papeis[k].rotulo || k;
      selPapel.appendChild(o);
    });
    await carregarTemplates();
    setProjetoAtivo(false);

    $("folha-papel").addEventListener("change", aoMudarPapel);
    $("folha-w").addEventListener("change", () => {
      if ($("folha-papel").value === "custom") aoMudarPapel();
    });
    $("folha-h").addEventListener("change", () => {
      if ($("folha-papel").value === "custom") aoMudarPapel();
    });
    $("folha-fundo").addEventListener("input", () => renderCanvas());

    $("folha-add-text").onclick = () => {
      const c = addCamada("text");
      selecionar(c.id);
      renderTudo();
    };
    $("folha-add-field").onclick = () => {
      const c = addCamada("text_field");
      selecionar(c.id);
      renderTudo();
    };
    $("folha-add-img-cosmos").onclick = () => {
      const c = addCamada("image_product");
      selecionar(c.id);
      renderTudo();
    };
    $("folha-add-img-custom").onclick = () => {
      const c = addCamada("image_custom");
      selecionar(c.id);
      renderTudo();
      abrirModalImg(c.id);
    };
    $("folha-add-rect").onclick = () => {
      const c = addCamada("rect");
      selecionar(c.id);
      renderTudo();
    };

    $("folha-img-ok").onclick = () => aplicarImgModal();
    $("folha-img-cancel").onclick = () => fecharModalImg(false);
    $("folha-drop").onclick = () => $("folha-file-img").click();
    $("folha-file-img").addEventListener("change", () => {
      if ($("folha-file-img").files && $("folha-file-img").files[0]) {
        aplicarImgModal();
      }
    });
    $("folha-drop").addEventListener("dragover", (e) => {
      e.preventDefault();
      $("folha-drop").classList.add("over");
    });
    $("folha-drop").addEventListener("dragleave", () => $("folha-drop").classList.remove("over"));
    $("folha-drop").addEventListener("drop", (e) => {
      e.preventDefault();
      $("folha-drop").classList.remove("over");
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) {
        const dt = new DataTransfer();
        dt.items.add(f);
        $("folha-file-img").files = dt.files;
        aplicarImgModal();
      }
    });

    $("folha-buscar").onclick = () => buscarProduto();
    $("folha-codigo").addEventListener("keydown", (e) => {
      if (e.key === "Enter") buscarProduto();
    });
    $("folha-salvar-como").onclick = () => {
      $("folha-modal-salvar").hidden = false;
    };
    $("folha-modal-salvar-cancel").onclick = () => {
      $("folha-modal-salvar").hidden = true;
    };
    $("folha-salvar-projeto").onclick = () => {
      $("folha-modal-salvar").hidden = true;
      salvar().catch((e) => alert(e.message));
    };
    $("folha-modal-salvar").querySelectorAll("[data-fmt]").forEach((btn) => {
      btn.onclick = () => {
        $("folha-modal-salvar").hidden = true;
        exportar(btn.dataset.fmt).catch((e) => alert(e.message));
      };
    });
    if ($("folha-imprimir")) {
      $("folha-imprimir").onclick = () => {
        imprimirCartaz().catch((e) => alert(e.message || e));
      };
    }
    if ($("folha-export-template")) {
      $("folha-export-template").onclick = () => {
        $("folha-modal-salvar").hidden = true;
        exportarArquivoTemplate().catch((e) => alert(e.message || e));
      };
    }
    if ($("folha-modal-prod-cancel")) {
      $("folha-modal-prod-cancel").onclick = () => fecharModalProd();
    };
    if ($("folha-import-file")) {
      $("folha-import-file").addEventListener("change", () => {
        const f = $("folha-import-file").files && $("folha-import-file").files[0];
        if (f) {
          importarArquivoTemplate(f).then(() => {
            $("folha-modal-inicio").hidden = true;
          });
        }
        $("folha-import-file").value = "";
      });
    }

    async function mostrarListaTemplatesInicio() {
      const wrap = $("folha-inicio-lista-wrap");
      const ul = $("folha-inicio-lista");
      wrap.hidden = false;
      ul.innerHTML = "<li style='cursor:default'>Carregando…</li>";
      try {
        const r = await api("/templates");
        const itens = r.templates || [];
        if (!itens.length) {
          ul.innerHTML = "<li style='cursor:default;opacity:.7'>Nenhum template salvo ainda.</li>";
          return;
        }
        ul.innerHTML = itens
          .map(
            (t, i) =>
              `<li data-i="${i}"><span>${esc(t.nome || t.id)}</span><span class="ean">${esc(t.papel || "")} · ${esc(t.id)}</span></li>`
          )
          .join("");
        ul.querySelectorAll("li[data-i]").forEach((li) => {
          li.addEventListener("click", async () => {
            const t = itens[Number(li.dataset.i)];
            try {
              const r2 = await api("/templates/" + encodeURIComponent(t.id));
              aplicarTemplate(r2.template);
              setProjetoAtivo(true);
              $("folha-modal-inicio").hidden = true;
            } catch (e) {
              alert(e.message);
            }
          });
        });
      } catch (e) {
        ul.innerHTML = "<li style='cursor:default'>" + esc(e.message) + "</li>";
      }
    }

    $("folha-inicio-novo").onclick = () => {
      aplicarTemplate(estado.meta.template_padrao);
      setProjetoAtivo(true);
      $("folha-modal-inicio").hidden = true;
    };
    $("folha-inicio-abrir").onclick = () => mostrarListaTemplatesInicio();
    $("folha-inicio-importar").onclick = () => $("folha-import-file").click();
    if ($("folha-inicio-fechar")) {
      $("folha-inicio-fechar").onclick = () => fecharModalInicio();
    }
    const modalInicio = $("folha-modal-inicio");
    if (modalInicio) {
      modalInicio.addEventListener("click", (e) => {
        if (e.target === modalInicio) fecharModalInicio();
      });
    }
    if ($("folha-abrir-projeto")) {
      $("folha-abrir-projeto").onclick = () => abrirModalInicio();
    }
    if ($("folha-trocar-tpl")) {
      $("folha-trocar-tpl").onclick = () => abrirModalInicio();
    }

    abrirModalInicio();

    // clique fora desmarca
    const scroll = $("folha-canvas-scroll");
    if (scroll) {
      scroll.addEventListener("mousedown", (e) => {
        if (e.target === scroll || e.target.id === "folha-folha") {
          estado.selecionada = null;
          document.querySelectorAll(".folha-camada.selecionada").forEach((el) => {
            el.classList.remove("selecionada");
            el.querySelectorAll(".handle").forEach((h) => h.remove());
          });
          renderListaCamadas();
          renderProps();
        }
      });
    }

    // setas movem o elemento selecionado (1 mm; Shift = 5 mm)
    window.addEventListener("keydown", (e) => {
      if (!estado.selecionada || !estado.template) return;
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const keys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"];
      if (!keys.includes(e.key)) return;
      e.preventDefault();
      const c = (estado.template.camadas || []).find((x) => x.id === estado.selecionada);
      if (!c) return;
      const step = e.shiftKey ? 5 : 1;
      if (e.key === "ArrowLeft") c.x_mm = Math.round((c.x_mm - step) * 10) / 10;
      if (e.key === "ArrowRight") c.x_mm = Math.round((c.x_mm + step) * 10) / 10;
      if (e.key === "ArrowUp") c.y_mm = Math.round((c.y_mm - step) * 10) / 10;
      if (e.key === "ArrowDown") c.y_mm = Math.round((c.y_mm + step) * 10) / 10;
      aplicarGeomNoDom(c);
      renderProps();
    });

    document.querySelectorAll('input[name="folha-preco-modo"]').forEach((r) => {
      r.addEventListener("change", () => {
        estado.precoModo = r.value;
        renderCanvas();
        const pe = precoExibido("price_1");
        const p = estado.produto || {};
        if (p.description || estado.codigo) {
          $("folha-prod-status").textContent =
            (p.description || estado.codigo || "") +
            " · " +
            pe.texto +
            (pe.sufixo || "");
        }
      });
    });

    // código digitado (EAN, balança, interno) → auto busca após pausa
    let eanTimer = null;
    $("folha-codigo").addEventListener("input", () => {
      clearTimeout(eanTimer);
      const v = ($("folha-codigo").value || "").trim();
      if (modoBusca(v) !== "codigo") return;
      const dig = v.replace(/\D/g, "");
      // a partir de 3 dígitos tenta (balança/PLU/EAN/cadastro)
      if (dig.length >= 3) {
        eanTimer = setTimeout(() => buscarProduto(), 320);
      }
    });

    // Delete remove camada selecionada
    window.addEventListener("keydown", (e) => {
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (!estado.selecionada) return;
      e.preventDefault();
      removerCamada(estado.selecionada);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => init().catch((e) => alert(e.message)));
  } else {
    init().catch((e) => alert(e.message));
  }
})();
