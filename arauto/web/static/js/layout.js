/* Editor de layout dos terminais — interação no estilo do editor de camadas
   (propagandas): canvas, props bar, lista, drag/resize, snap e guias.
   Dados: elementos[chave] = { x, y, tamanho, negrito, visivel, largura, linhas, altura }
   x = -1 centraliza na horizontal.
*/
(function () {
  "use strict";
  const { $, esc, json, aviso } = window.TC;

  const SNAP = 8;

  const estado = {
    modelos: [],
    catalogo: [],
    cores: [],
    fontes: [],
    corSemFundo: -1,
    fator: 0.55,
    entrelinha: 1.15,
    modelo: null,
    layout: null,
    textos: {},
    selecionado: null,
    escala: 1,
    zoom: 1,
    codigoPrevia: "7896080900001",
  };

  const tela = $("tela");
  const elBox = $("elementos");
  const modelosBox = $("modelos");
  const propsBar = $("layout-props-bar");

  const COR_MAPA = {
    256: "#000000", 257: "#7a4a1a", 258: "#1a7a2a", 259: "#6b7a1a",
    260: "#101f45", 261: "#5a1a7a", 262: "#6a6a7a", 263: "#cfd3e5",
    264: "#c0c0c8", 265: "#c02020", 266: "#40c020", 267: "#d0c020",
    268: "#2040c0", 269: "#c020a0", 270: "#20b0c0", 271: "#FFFFFF",
    65535: "transparent",
  };
  function corCss(codigo) {
    const n = Number(codigo);
    if (codigo == null || Number.isNaN(n) || n < 0 || n === 65535) return "transparent";
    if (n === 271) return "#FFFFFF";
    const api = (estado.cores || []).find((c) => Number(c.codigo) === n);
    if (api && api.hex) return api.hex;
    return COR_MAPA[n] || "#cfd3e5";
  }

  function modeloAtual() {
    return estado.modelos.find((m) => m.modelo === estado.modelo) || null;
  }

  function els() {
    if (!estado.layout) estado.layout = { elementos: {} };
    if (!estado.layout.elementos) estado.layout.elementos = {};
    return estado.layout.elementos;
  }

  function elOf(chave) {
    const todos = els();
    if (!todos[chave]) {
      todos[chave] = {
        x: 10, y: 10, tamanho: 16, negrito: false, visivel: true,
        largura: 0, linhas: 1, altura: 0, trava_proporcao: false,
      };
    }
    return todos[chave];
  }

  function quebrarTexto(texto, tamanho, largura, maxLinhas) {
    texto = String(texto || "").trim();
    if (!texto) return [];
    if (!largura || largura <= 0 || maxLinhas <= 1) return [texto];
    const porLinha = Math.max(1, Math.floor(largura / Math.max(1, tamanho * estado.fator)));
    const palavras = texto.split(/\s+/);
    const linhas = [];
    let atual = "";
    for (const p of palavras) {
      const cand = atual ? atual + " " + p : p;
      if (cand.length <= porLinha) {
        atual = cand;
      } else {
        if (atual) linhas.push(atual);
        if (linhas.length >= maxLinhas) break;
        atual = p.length > porLinha ? p.slice(0, porLinha) : p;
      }
    }
    if (atual && linhas.length < maxLinhas) linhas.push(atual);
    return linhas.slice(0, maxLinhas);
  }

  function textoDe(chave) {
    const t = estado.textos || {};
    if (chave === "codigo") return t.codigo || t.codigo_barras || estado.codigoPrevia || "";
    if (chave === "descricao") return t.descricao || t.nome || "PRODUTO EXEMPLO";
    if (chave === "rotulo1") return t.rotulo1 || t.label1 || "À vista";
    if (chave === "preco1") return t.preco1 || t.price1 || "R$ 9,99";
    if (chave === "rotulo2") return t.rotulo2 || t.label2 || "A prazo";
    if (chave === "preco2") return t.preco2 || t.price2 || "R$ 10,99";
    if (chave === "nao_achado") return t.nao_achado || t.mensagem || "PRODUTO NÃO ENCONTRADO";
    if (chave === "imagem") return "";
    return t[chave] || "";
  }

  function caixaLargura(chave, p) {
    if (chave === "imagem") return Math.max(8, p.largura || p.altura || 80);
    if ((p.largura || 0) > 0) return p.largura;
    const txt = textoDe(chave);
    const tam = p.tamanho || 16;
    return Math.max(12, Math.ceil(String(txt).length * tam * estado.fator));
  }

  function caixaAltura(chave, p) {
    if (chave === "imagem") return Math.max(8, p.altura || p.largura || 80);
    const tam = p.tamanho || 16;
    const linhas = Math.max(1, p.linhas || 1);
    if ((p.largura || 0) > 0 && linhas > 1) {
      return Math.ceil(linhas * tam * estado.entrelinha);
    }
    return Math.ceil(tam * estado.entrelinha);
  }

  /* —— guias (estilo plugin) ——————————————————————————— */
  function limparGuias() {
    if (!tela) return;
    tela.querySelectorAll(".layout-guia").forEach((g) => g.remove());
  }

  function mostrarGuia(eixo, pos) {
    if (!tela) return;
    const m = modeloAtual();
    if (!m) return;
    const g = document.createElement("div");
    const centroX = Math.round(m.largura / 2);
    const centroY = Math.round(m.altura / 2);
    const isCentro = (eixo === "v" && pos === centroX) || (eixo === "h" && pos === centroY);
    g.className = "layout-guia layout-guia--" + eixo + (isCentro ? " layout-guia--centro" : "");
    if (eixo === "v") {
      g.style.left = pos * estado.escala + "px";
      g.style.height = m.altura * estado.escala + "px";
    } else {
      g.style.top = pos * estado.escala + "px";
      g.style.width = m.largura * estado.escala + "px";
    }
    tela.appendChild(g);
  }

  function snapValor(val, alvos) {
    let best = val, bestD = SNAP + 1, hit = null;
    alvos.forEach((a) => {
      const d = Math.abs(val - a);
      if (d < bestD) { bestD = d; best = a; hit = a; }
    });
    if (bestD <= SNAP) return { val: best, hit };
    return { val, hit: null };
  }

  function alvosSnap(exceto) {
    const m = modeloAtual();
    const xs = [0, Math.round(m.largura / 2), m.largura];
    const ys = [0, Math.round(m.altura / 2), m.altura];
    Object.keys(els()).forEach((chave) => {
      if (chave === exceto) return;
      const p = elOf(chave);
      if (!p.visivel) return;
      const w = caixaLargura(chave, p);
      const h = caixaAltura(chave, p);
      const x = p.x === -1 ? Math.round((m.largura - w) / 2) : (p.x || 0);
      const y = p.y || 0;
      xs.push(x, x + Math.round(w / 2), x + w);
      ys.push(y, y + Math.round(h / 2), y + h);
    });
    return { xs, ys };
  }

  /* —— props bar (como plugin) ————————————————————————— */
  function renderProps() {
    if (!propsBar) return;
    const chave = estado.selecionado;
    if (!chave) {
      propsBar.classList.remove("visivel");
      propsBar.innerHTML = '<span class="layout-props-vazio">Selecione um elemento no canvas para editar</span>';
      return;
    }
    propsBar.classList.add("visivel");
    const p = elOf(chave);
    const rotulo = (estado.catalogo.find((c) => c.chave === chave) || {}).rotulo || chave;
    const isImg = chave === "imagem";
    const align = p.x === -1 ? "center" : "left";
    const w = p.largura || 0;
    const h = p.altura || 0;

    let html = `
      <div class="campo" style="min-width:7rem"><label>Nome</label><input class="prop-input" value="${esc(rotulo)}" disabled></div>
      <div class="campo" style="min-width:3.4rem"><label>X</label><input type="number" class="prop-input" data-k="x" value="${p.x|0}"></div>
      <div class="campo" style="min-width:3.4rem"><label>Y</label><input type="number" class="prop-input" data-k="y" value="${p.y|0}"></div>
      <div class="campo" style="min-width:3.4rem"><label>Larg.</label><input type="number" class="prop-input" data-k="largura" value="${w|0}"></div>
      <div class="campo" style="min-width:3.4rem"><label>Alt.</label><input type="number" class="prop-input" data-k="altura" value="${h|0}"></div>
      <label class="prop-check"><input type="checkbox" data-k="visivel" ${p.visivel !== false ? "checked" : ""}> Visível</label>
      <label class="prop-check"><input type="checkbox" data-k="trava_proporcao" ${p.trava_proporcao ? "checked" : ""}> Proporção</label>`;

    if (!isImg) {
      html += `
        <div class="campo" style="min-width:3.6rem"><label>Fonte</label><input type="number" class="prop-input" data-k="tamanho" value="${p.tamanho || 16}"></div>
        <label class="prop-check"><input type="checkbox" data-k="negrito" ${p.negrito ? "checked" : ""}> Negrito</label>
        <div class="campo" style="min-width:6rem"><label>Alinhamento</label>
          <select class="prop-select" data-k="align">
            <option value="left" ${align === "left" ? "selected" : ""}>Esquerda</option>
            <option value="center" ${align === "center" ? "selected" : ""}>Centro</option>
          </select>
        </div>
        <div class="campo" style="min-width:3.4rem"><label>Linhas</label><input type="number" class="prop-input" data-k="linhas" value="${p.linhas || 1}" min="1" max="10"></div>`;
    } else {
      html += `
        <div class="campo" style="min-width:6.5rem"><label>Encaixe</label>
          <select class="prop-select" data-k="object_fit">
            <option value="contain" ${(p.object_fit || "contain") === "contain" ? "selected" : ""}>Contain</option>
            <option value="cover" ${p.object_fit === "cover" ? "selected" : ""}>Cover</option>
          </select>
        </div>`;
    }

    propsBar.innerHTML = html;
    propsBar.querySelectorAll("[data-k]").forEach((el) => {
      const apply = () => {
        const k = el.dataset.k;
        if (k === "align") {
          if (el.value === "center") p.x = -1;
          else if (p.x === -1) {
            const m = modeloAtual();
            const boxW = caixaLargura(chave, p);
            p.x = m ? Math.max(0, Math.round((m.largura - boxW) / 2)) : 0;
          }
        } else if (el.type === "checkbox") {
          p[k] = el.checked;
        } else if (el.type === "number") {
          p[k] = Number(el.value);
        } else {
          p[k] = el.value;
        }
        renderTela();
        renderElementos();
        // não rebuilda a barra inteira no input para não perder o foco
        const xEl = propsBar.querySelector('[data-k="x"]');
        if (xEl && document.activeElement !== xEl) xEl.value = p.x;
      };
      el.addEventListener("change", apply);
      if (el.type === "number" || el.type === "text") el.addEventListener("input", apply);
    });
  }

  function campoNum(k, label, val, min, max) {
    return (
      `<label class="layout-prop">` +
      `<span>${esc(label)}</span>` +
      `<input type="number" data-k="${k}" value="${val}" min="${min}" max="${max}">` +
      `</label>`
    );
  }

  function syncPropsGeom(chave) {
    if (!propsBar || estado.selecionado !== chave) return;
    const p = elOf(chave);
    propsBar.querySelectorAll("input[type=number]").forEach((el) => {
      const k = el.dataset.k;
      if (["x", "y", "largura", "altura", "tamanho", "linhas"].includes(k) && p[k] != null) {
        el.value = p[k];
      }
    });
  }

  /* —— lista de camadas ——————————————————————————————— */
  function renderElementos() {
    if (!elBox) return;
    const modoVazio = $("modo-vazio") && $("modo-vazio").checked;
    elBox.innerHTML = "";
    estado.catalogo.forEach(({ chave, rotulo }) => {
      const p = elOf(chave);
      const li = document.createElement("li");
      li.className = "layout-camada-item" + (estado.selecionado === chave ? " ativa" : "");
      li.dataset.chave = chave;
      if (modoVazio && chave !== "nao_achado") li.classList.add("apagada");
      if (!modoVazio && chave === "nao_achado") li.classList.add("apagada");

      li.innerHTML =
        `<button type="button" class="layout-camada-vis" data-vis title="Visível">` +
        (p.visivel !== false ? "👁" : "—") + `</button>` +
        `<span class="meta">${esc(rotulo)}</span>` +
        `<span class="layout-camada-xy mono">${p.x}, ${p.y}</span>`;

      li.addEventListener("click", (ev) => {
        if (ev.target.closest("[data-vis]")) return;
        estado.selecionado = chave;
        renderTela();
        renderElementos();
        renderProps();
      });
      li.querySelector("[data-vis]").addEventListener("click", (ev) => {
        ev.stopPropagation();
        p.visivel = !p.visivel;
        renderTela();
        renderElementos();
        renderProps();
      });
      elBox.appendChild(li);
    });
  }

  /* —— canvas —————————————————————————————————————————— */
  function calcularZoom(m) {
    /* Largura = coluna inteira. Altura segue o aspecto do aparelho.
       Não usa clientHeight (isso encolhia o canvas a cada troca de modelo). */
    const scroll = $("layout-canvas-scroll") || document.querySelector(".layout-canvas-scroll");
    if (!scroll || !m || !m.largura) return 1;
    const availW = Math.max(200, scroll.clientWidth - 24);
    return Math.max(0.25, availW / m.largura);
  }

  function renderTela() {
    if (!tela || !estado.layout) return;
    const m = modeloAtual();
    if (!m) return;

    estado.escala = 1;
    estado.zoom = calcularZoom(m);
    const W = m.largura, H = m.altura;
    const z = estado.zoom;
    tela.style.width = W + "px";
    tela.style.height = H + "px";
    tela.style.transform = z === 1 ? "none" : ("scale(" + z + ")");
    tela.style.transformOrigin = "0 0";
    const bgTela = Number(estado.layout.cor_tela) === 271
      ? "#FFFFFF"
      : corCss(estado.layout.cor_tela != null ? estado.layout.cor_tela : 260);
    tela.style.background = bgTela;
    tela.style.backgroundColor = bgTela;

    const zoomEl = $("tela-zoom");
    if (zoomEl) {
      zoomEl.style.width = Math.round(W * z) + "px";
      zoomEl.style.height = Math.round(H * z) + "px";
      zoomEl.style.transform = "none";
    }

    const res = $("resolucao");
    if (res) {
      res.textContent = m.nome + " · " + W + " × " + H + " px";
    }

    limparGuias();
    tela.innerHTML = "";

    const modoVazio = $("modo-vazio") && $("modo-vazio").checked;
    const corTexto = corCss(estado.layout.cor_texto != null ? estado.layout.cor_texto : 263);
    const fundoTexto = estado.layout.cor_fundo_texto;
    const temFundo = fundoTexto != null && Number(fundoTexto) >= 0;

    // aviso de corte
    const avisoCorte = $("aviso-corte");
    if (avisoCorte) avisoCorte.hidden = true;

    estado.catalogo.forEach(({ chave }) => {
      const p = elOf(chave);
      if (p.visivel === false) return;
      if (modoVazio && chave !== "nao_achado") return;
      if (!modoVazio && chave === "nao_achado") return;
      if (chave !== "imagem") {
        const txt = textoDe(chave);
        if (!txt && chave !== "imagem") return;
      }

      const div = document.createElement("div");
      div.className = "tela-el" + (estado.selecionado === chave ? " tela-el--sel" : "");
      div.dataset.chave = chave;

      const w = caixaLargura(chave, p);
      const h = caixaAltura(chave, p);
      const x = p.x === -1 ? Math.round((W - w) / 2) : (p.x || 0);
      const y = p.y || 0;

      div.style.left = x * estado.escala + "px";
      div.style.top = y * estado.escala + "px";
      div.style.width = w * estado.escala + "px";
      div.style.minHeight = h * estado.escala + "px";
      div.style.color = corTexto;
      if (temFundo) div.style.background = corCss(fundoTexto);

      if (chave === "imagem") {
        div.classList.add("tela-el--img");
        div.style.height = h * estado.escala + "px";
        const cod = estado.codigoPrevia || "";
        div.innerHTML =
          `<img src="/api/imagens/${encodeURIComponent(cod)}" alt="" ` +
          `onerror="this.style.display='none';this.parentElement.classList.add('tela-el--img-vazia')">` +
          `<span class="tela-el-img-lbl">IMG</span>`;
      } else {
        const tam = p.tamanho || 16;
        div.style.fontSize = (tam || 16) + "px";
        div.style.fontWeight = p.negrito ? "700" : "400";
        const linhas = quebrarTexto(textoDe(chave), tam, p.largura || 0, p.linhas || 1);
        if ((p.largura || 0) > 0 && (p.linhas || 1) > 1) {
          div.classList.add("tela-el--quebra");
          div.style.height = h * estado.escala + "px";
        }
        div.textContent = linhas.join("\n") || "·";
      }

      // fora da tela?
      if (x + w > W || y + h > H || x < 0 || y < 0) {
        div.classList.add("tela-el--corte");
        if (avisoCorte) {
          avisoCorte.hidden = false;
          avisoCorte.textContent = "Há elementos cortados pela borda da tela.";
        }
      }

      div.addEventListener("pointerdown", (ev) => {
        if (ev.target.classList.contains("tela-handle")) return;
        iniciarArraste(ev, chave);
      });
      div.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (estado.selecionado !== chave) {
          estado.selecionado = chave;
          renderTela();
          renderElementos();
          renderProps();
        }
      });

      if (estado.selecionado === chave) {
        ["nw", "ne", "sw", "se"].forEach((canto) => {
          const hnd = document.createElement("div");
          hnd.className = "tela-handle tela-handle--" + canto;
          hnd.dataset.canto = canto;
          hnd.addEventListener("pointerdown", (ev) => iniciarResize(ev, chave, canto));
          div.appendChild(hnd);
        });
      }

      tela.appendChild(div);
    });
  }

  function aplicarGeomNoDom(chave) {
    const m = modeloAtual();
    const p = elOf(chave);
    const node = tela && tela.querySelector(`.tela-el[data-chave="${chave}"]`);
    if (!node || !m) return;
    const w = caixaLargura(chave, p);
    const h = caixaAltura(chave, p);
    const x = p.x === -1 ? Math.round((m.largura - w) / 2) : (p.x || 0);
    node.style.left = x * estado.escala + "px";
    node.style.top = (p.y || 0) * estado.escala + "px";
    node.style.width = w * estado.escala + "px";
    if (chave === "imagem" || ((p.largura || 0) > 0 && (p.linhas || 1) > 1)) {
      node.style.height = h * estado.escala + "px";
      node.style.minHeight = h * estado.escala + "px";
    }
    if (chave !== "imagem" && p.tamanho) {
      if (p.tamanho) node.style.fontSize = p.tamanho + "px";
    }
  }

  function iniciarArraste(ev, chave) {
    ev.preventDefault();
    ev.stopPropagation();
    estado.selecionado = chave;
    renderElementos();
    renderProps();
    // marca seleção no DOM sem rebuild completo
    tela.querySelectorAll(".tela-el").forEach((n) => {
      n.classList.toggle("tela-el--sel", n.dataset.chave === chave);
    });

    const p = elOf(chave);
    const m = modeloAtual();
    if (!m) return;

    const startX = ev.clientX, startY = ev.clientY;
    const w = caixaLargura(chave, p);
    const ox = p.x === -1 ? Math.round((m.largura - w) / 2) : (p.x || 0);
    const oy = p.y || 0;

    function move(e) {
      const z = estado.zoom || 1;
      const dx = Math.round((e.clientX - startX) / z);
      const dy = Math.round((e.clientY - startY) / z);
      let nx = ox + dx;
      let ny = oy + dy;
      const { xs, ys } = alvosSnap(chave);
      const w2 = caixaLargura(chave, p);
      const h2 = caixaAltura(chave, p);
      limparGuias();

      const hitX = [], hitY = [];
      const pageCx = Math.round(m.largura / 2);
      const pageCy = Math.round(m.altura / 2);
      const elCx = nx + w2 / 2, elCy = ny + h2 / 2;

      if (Math.abs(elCx - pageCx) <= SNAP) {
        nx = pageCx - Math.round(w2 / 2);
        hitX.push(pageCx);
      } else {
        const sL = snapValor(nx, xs);
        const sC = snapValor(nx + Math.round(w2 / 2), xs);
        const sR = snapValor(nx + w2, xs);
        const cand = [
          { d: Math.abs(sC.val - (nx + w2 / 2)), v: sC.val - Math.round(w2 / 2), hit: sC.hit },
          { d: Math.abs(sL.val - nx), v: sL.val, hit: sL.hit },
          { d: Math.abs(sR.val - (nx + w2)), v: sR.val - w2, hit: sR.hit },
        ].sort((a, b) => a.d - b.d)[0];
        if (cand.hit != null && cand.d <= SNAP) { nx = cand.v; hitX.push(cand.hit); }
      }

      if (Math.abs(elCy - pageCy) <= SNAP) {
        ny = pageCy - Math.round(h2 / 2);
        hitY.push(pageCy);
      } else {
        const sT = snapValor(ny, ys);
        const sM = snapValor(ny + Math.round(h2 / 2), ys);
        const sB = snapValor(ny + h2, ys);
        const cand = [
          { d: Math.abs(sM.val - (ny + h2 / 2)), v: sM.val - Math.round(h2 / 2), hit: sM.hit },
          { d: Math.abs(sT.val - ny), v: sT.val, hit: sT.hit },
          { d: Math.abs(sB.val - (ny + h2)), v: sB.val - h2, hit: sB.hit },
        ].sort((a, b) => a.d - b.d)[0];
        if (cand.hit != null && cand.d <= SNAP) { ny = cand.v; hitY.push(cand.hit); }
      }

      p.x = Math.max(-1, Math.min(m.largura - 1, Math.round(nx)));
      p.y = Math.max(0, Math.min(m.altura - 1, Math.round(ny)));
      aplicarGeomNoDom(chave);
      hitX.forEach((v) => mostrarGuia("v", v));
      hitY.forEach((v) => mostrarGuia("h", v));
      syncPropsGeom(chave);
    }

    function up() {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", up);
      limparGuias();
      renderTela();
      renderElementos();
      renderProps();
    }
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", up);
  }

  function iniciarResize(ev, chave, canto) {
    ev.preventDefault();
    ev.stopPropagation();
    const p = elOf(chave);
    const m = modeloAtual();
    if (!m) return;
    const startX = ev.clientX, startY = ev.clientY;
    const o = {
      x: p.x === -1 ? 0 : (p.x || 0),
      y: p.y || 0,
      largura: caixaLargura(chave, p),
      altura: caixaAltura(chave, p),
      tamanho: p.tamanho || 16,
      linhas: p.linhas || 1,
    };
    // se x era -1, materializa posição
    if (p.x === -1) p.x = o.x;
    const isImg = chave === "imagem";
    const isText = !isImg;

    function move(e) {
      const z = estado.zoom || 1;
      const dx = Math.round((e.clientX - startX) / z);
      const dy = Math.round((e.clientY - startY) / z);
      limparGuias();
      let x = o.x, y = o.y, w = o.largura, h = o.altura;

      if (canto.includes("e")) w = Math.max(8, o.largura + dx);
      if (canto.includes("s")) h = Math.max(8, o.altura + dy);
      if (canto.includes("w")) {
        w = Math.max(8, o.largura - dx);
        x = o.x + (o.largura - w);
      }
      if (canto.includes("n")) {
        h = Math.max(8, o.altura - dy);
        y = o.y + (o.altura - h);
      }

      if (p.trava_proporcao) {
        const ratio = o.largura / Math.max(1, o.altura);
        if (Math.abs(dx) >= Math.abs(dy)) {
          h = Math.max(8, w / ratio);
          if (canto.includes("n")) y = o.y + o.altura - h;
        } else {
          w = Math.max(8, h * ratio);
          if (canto.includes("w")) x = o.x + o.largura - w;
        }
      }

      // snap bordas
      const { xs, ys } = alvosSnap(chave);
      const sR = snapValor(x + w, xs);
      const sB = snapValor(y + h, ys);
      const sL = snapValor(x, xs);
      const sT = snapValor(y, ys);
      if (canto.includes("e") && sR.hit != null) w = sR.val - x;
      if (canto.includes("s") && sB.hit != null) h = sB.val - y;
      if (canto.includes("w") && sL.hit != null) { w = (x + w) - sL.val; x = sL.val; }
      if (canto.includes("n") && sT.hit != null) { h = (y + h) - sT.val; y = sT.val; }
      if (sR.hit != null && canto.includes("e")) mostrarGuia("v", sR.hit);
      if (sL.hit != null && canto.includes("w")) mostrarGuia("v", sL.hit);
      if (sB.hit != null && canto.includes("s")) mostrarGuia("h", sB.hit);
      if (sT.hit != null && canto.includes("n")) mostrarGuia("h", sT.hit);

      p.x = Math.round(x);
      p.y = Math.round(y);
      if (isImg) {
        p.largura = Math.round(w);
        p.altura = Math.round(h);
      } else {
        // texto: largura explícita; altura → linhas ou fonte
        p.largura = Math.round(w);
        if (isText && o.altura > 0) {
          const scale = h / o.altura;
          p.tamanho = Math.round(Math.max(8, o.tamanho * scale));
        }
        if ((p.linhas || 1) > 1) {
          p.linhas = Math.max(1, Math.round(h / Math.max(1, p.tamanho * estado.entrelinha)));
        }
      }
      aplicarGeomNoDom(chave);
      syncPropsGeom(chave);
    }

    function up() {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", up);
      limparGuias();
      renderTela();
      renderElementos();
      renderProps();
    }
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", up);
  }

  /* —— teclado ————————————————————————————————————————— */
  if (tela) {
    tela.addEventListener("keydown", (ev) => {
      if (!estado.selecionado) return;
      const step = ev.shiftKey ? 10 : 1;
      const p = elOf(estado.selecionado);
      let moved = false;
      if (ev.key === "ArrowLeft") { p.x = (p.x === -1 ? 0 : p.x) - step; moved = true; }
      if (ev.key === "ArrowRight") { p.x = (p.x === -1 ? 0 : p.x) + step; moved = true; }
      if (ev.key === "ArrowUp") { p.y = (p.y || 0) - step; moved = true; }
      if (ev.key === "ArrowDown") { p.y = (p.y || 0) + step; moved = true; }
      if (moved) {
        ev.preventDefault();
        p.y = Math.max(0, p.y);
        renderTela();
        renderElementos();
        renderProps();
      }
    });
    tela.addEventListener("click", () => tela.focus());
  }

  /* —— centro —————————————————————————————————————————— */
  function centralizar(eixo) {
    if (!estado.selecionado) {
      aviso("Selecione um elemento.", true);
      return;
    }
    const p = elOf(estado.selecionado);
    const m = modeloAtual();
    if (!m) return;
    const w = caixaLargura(estado.selecionado, p);
    const h = caixaAltura(estado.selecionado, p);
    if (eixo === "h" || eixo === "ambos") p.x = -1;
    if (eixo === "v" || eixo === "ambos") p.y = Math.max(0, Math.round((m.altura - h) / 2));
    renderTela();
    renderElementos();
    renderProps();
  }

  /* —— modelos ———————————————————————————————————————— */
  function renderModelos() {
    if (!modelosBox) return;
    modelosBox.innerHTML = "";
    estado.modelos.forEach((m) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "modelo-btn" + (m.modelo === estado.modelo ? " modelo-btn--ativo" : "");
      btn.textContent = m.nome + " (" + m.largura + "×" + m.altura + ")";
      btn.addEventListener("click", () => selecionarModelo(m.modelo));
      modelosBox.appendChild(btn);
    });
  }

  async function selecionarModelo(id) {
    estado.modelo = id;
    estado.selecionado = null;
    try {
      const data = await json("/api/layout");
      estado.modelos = (data.modelos || []).map((m) => ({
        modelo: m.modelo != null ? m.modelo : m.id,
        nome: m.nome || ("Modelo " + m.modelo),
        largura: m.largura,
        altura: m.altura,
        elementos: m.elementos || {},
        cor_texto: m.cor_texto,
        cor_fundo_texto: m.cor_fundo_texto,
        cor_tela: m.cor_tela,
        fonte_normal: m.fonte_normal,
        fonte_negrito: m.fonte_negrito,
      }));
      const m = estado.modelos.find((x) => x.modelo === id);
      if (m) {
        estado.layout = {
          elementos: JSON.parse(JSON.stringify(m.elementos || {})),
          cor_texto: m.cor_texto != null ? m.cor_texto : 263,
          cor_fundo_texto: m.cor_fundo_texto != null ? m.cor_fundo_texto : -1,
          cor_tela: m.cor_tela != null ? m.cor_tela : 260,
          fonte_normal: m.fonte_normal || "DejaVuSans.ttf",
          fonte_negrito: m.fonte_negrito || "DejaVuSans-Bold.ttf",
        };
      } else {
        estado.layout = {
          elementos: {}, cor_texto: 263, cor_fundo_texto: -1, cor_tela: 260,
          fonte_normal: "DejaVuSans.ttf", fonte_negrito: "DejaVuSans-Bold.ttf",
        };
      }
      preencherFontes();
      syncCoresUI();
      renderModelos();
      renderTela();
      renderElementos();
      renderProps();
    } catch (e) {
      aviso("Falha ao carregar layout: " + e.message, true);
    }
  }

  function preencherFontes() {
    const lista = estado.fontes.slice();
    const L = estado.layout || {};
    [L.fonte_normal, L.fonte_negrito].forEach((f) => {
      if (f && lista.indexOf(f) < 0) lista.unshift(f);
    });
    function fill(id, valor) {
      const sel = $(id);
      if (!sel) return;
      const atual = valor || "";
      sel.innerHTML = lista.map((f) =>
        `<option value="${esc(f)}" ${f === atual ? "selected" : ""}>${esc(f)}</option>`
      ).join("");
      if (atual && sel.value !== atual) {
        const extra = document.createElement("option");
        extra.value = atual;
        extra.textContent = atual;
        extra.selected = true;
        sel.insertBefore(extra, sel.firstChild);
      }
    }
    fill("fonte-normal", L.fonte_normal);
    fill("fonte-negrito", L.fonte_negrito);
  }

  function hexDaCor(codigo) {
    const n = Number(codigo);
    if (n === 271) return "#FFFFFF";
    return corCss(n);
  }

  function renderPaleta(boxId, valor, campo, incluirNenhum) {
    const box = $(boxId);
    if (!box) return;
    const atual = valor != null ? Number(valor) : 0;
    let html = "";
    if (incluirNenhum) {
      const on = atual < 0 || atual === 65535;
      html += `<button type="button" class="cor-swatch cor-swatch--nenhum${on ? " cor-swatch--on" : ""}" data-cor="${estado.corSemFundo}" title="Sem fundo"></button>`;
    }
    (estado.cores || []).forEach((c) => {
      if (Number(c.codigo) === 65535) return;
      const hex = Number(c.codigo) === 271 ? "#FFFFFF" : hexDaCor(c.codigo);
      const on = Number(c.codigo) === atual;
      html += `<button type="button" class="cor-swatch${on ? " cor-swatch--on" : ""}" data-cor="${c.codigo}" title="${esc(c.nome)} (${hex})" style="background:${hex}"></button>`;
    });
    box.innerHTML = html;
    box.querySelectorAll("[data-cor]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (!estado.layout) return;
        estado.layout[campo] = Number(btn.dataset.cor);
        renderPaleta(boxId, estado.layout[campo], campo, incluirNenhum);
        renderTela();
      });
    });
  }

  function syncCoresUI() {
    const L = estado.layout || {};
    renderPaleta("paleta-cor-texto", L.cor_texto != null ? L.cor_texto : 263, "cor_texto", false);
    renderPaleta("paleta-cor-fundo-texto", L.cor_fundo_texto != null ? L.cor_fundo_texto : estado.corSemFundo, "cor_fundo_texto", true);
    renderPaleta("paleta-cor-tela", L.cor_tela != null ? L.cor_tela : 260, "cor_tela", false);
  }

  /* —— previa / salvar ——————————————————————————————— */
  async function simular() {
    const cod = ($("codigo-previa") && $("codigo-previa").value || "").trim();
    if (!cod) return;
    estado.codigoPrevia = cod;
    try {
      const r = await json("/api/layout/previa?codigo=" + encodeURIComponent(cod) +
        (estado.modelo != null ? "&modelo=" + estado.modelo : ""));
      estado.textos = r.textos || r || {};
      if (r.encontrado === false || r.found === false) {
        if ($("modo-vazio")) $("modo-vazio").checked = true;
      }
      renderTela();
    } catch (e) {
      // fallback: consulta normal
      try {
        const r = await json("/consulta/" + encodeURIComponent(cod));
        estado.textos = {
          codigo: r.codigo_barras || cod,
          descricao: r.descricao || "",
          preco1: r.preco1 || "",
          preco2: r.preco2 || "",
          rotulo1: r.rotulo1 || "À vista",
          rotulo2: r.rotulo2 || "A prazo",
          nao_achado: r.mensagem || "PRODUTO NÃO ENCONTRADO",
        };
        if (!r.encontrado && $("modo-vazio")) $("modo-vazio").checked = true;
        renderTela();
      } catch (e2) {
        aviso("Prévia: " + e2.message, true);
      }
    }
  }

  function coletarLayout() {
    const L = estado.layout || {};
    L.fonte_normal = ($("fonte-normal") && $("fonte-normal").value) || L.fonte_normal;
    L.fonte_negrito = ($("fonte-negrito") && $("fonte-negrito").value) || L.fonte_negrito;
    return L;
  }

  async function salvar() {
    if (estado.modelo == null) return;
    try {
      await json("/api/layout/" + estado.modelo, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(coletarLayout()),
      });
      aviso("Layout do modelo salvo.");
    } catch (e) {
      aviso("Falha ao salvar: " + e.message, true);
    }
  }

  async function restaurar() {
    if (estado.modelo == null) return;
    if (!confirm("Restaurar o layout padrão deste modelo?")) return;
    try {
      await json("/api/layout/" + estado.modelo + "/restaurar", { method: "POST" });
      await selecionarModelo(estado.modelo);
      aviso("Layout restaurado.");
    } catch (e) {
      aviso("Falha: " + e.message, true);
    }
  }

  async function copiar() {
    if (estado.modelo == null) return;
    const outros = estado.modelos.filter((m) => m.modelo !== estado.modelo);
    if (!outros.length) {
      aviso("Não há outros modelos.", true);
      return;
    }
    const nomes = outros.map((m) => m.nome).join(", ");
    if (!confirm("Copiar o layout atual para: " + nomes + "?")) return;
    const body = coletarLayout();
    try {
      for (const m of outros) {
        await json("/api/layout/" + m.modelo, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      }
      aviso("Layout copiado para " + outros.length + " modelo(s).");
    } catch (e) {
      aviso("Falha ao copiar: " + e.message, true);
    }
  }

  /* —— boot ———————————————————————————————————————————— */
  async function iniciar() {
    try {
      const data = await json("/api/layout");
      estado.modelos = (data.modelos || []).map((m) => ({
        modelo: m.modelo != null ? m.modelo : m.id,
        nome: m.nome || ("Modelo " + m.modelo),
        largura: m.largura,
        altura: m.altura,
        elementos: m.elementos || {},
        cor_texto: m.cor_texto,
        cor_fundo_texto: m.cor_fundo_texto,
        cor_tela: m.cor_tela,
        fonte_normal: m.fonte_normal,
        fonte_negrito: m.fonte_negrito,
      }));
      estado.catalogo = data.elementos || [];
      estado.fontes = data.fontes || [];
      estado.cores = data.cores || [];
      estado.corSemFundo = data.cor_sem_fundo != null ? data.cor_sem_fundo : -1;
      if (data.fator_caractere) estado.fator = data.fator_caractere;
      if (data.entrelinha) estado.entrelinha = data.entrelinha;

      // se cores vierem como dict
      if (!Array.isArray(estado.cores) && data.cores && typeof data.cores === "object") {
        estado.cores = Object.keys(data.cores).map((nome) => ({
          nome, codigo: data.cores[nome],
        }));
      }

      const preferido = data.modelo_padrao != null ? data.modelo_padrao : 506;
      const inicial = estado.modelos.find((m) => m.modelo === preferido) || estado.modelos[0];
      if (inicial) await selecionarModelo(inicial.modelo);
      else {
        renderModelos();
        aviso("Nenhum modelo disponível.", true);
      }
      simular();
      requestAnimationFrame(() => { if (estado.layout) renderTela(); });
    } catch (e) {
      aviso("Não foi possível carregar o editor: " + e.message, true);
    }
  }

  // binds
  if ($("btn-previa")) $("btn-previa").addEventListener("click", simular);
  if ($("codigo-previa")) {
    $("codigo-previa").addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); simular(); }
    });
  }
  if ($("modo-vazio")) {
    $("modo-vazio").addEventListener("change", () => {
      renderTela();
      renderElementos();
    });
  }
  if ($("btn-c-h")) $("btn-c-h").addEventListener("click", () => centralizar("h"));
  if ($("btn-c-v")) $("btn-c-v").addEventListener("click", () => centralizar("v"));
  if ($("btn-c-ambos")) $("btn-c-ambos").addEventListener("click", () => centralizar("ambos"));
  if ($("btn-salvar")) $("btn-salvar").addEventListener("click", salvar);
  if ($("btn-restaurar")) $("btn-restaurar").addEventListener("click", restaurar);
  if ($("btn-copiar")) $("btn-copiar").addEventListener("click", copiar);

  ["fonte-normal", "fonte-negrito"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("change", () => {
      if (!estado.layout) return;
      if (id === "fonte-normal") estado.layout.fonte_normal = el.value;
      else estado.layout.fonte_negrito = el.value;
    });
  });

  window.addEventListener("resize", () => {
    if (estado.layout) renderTela();
  });

  iniciar();
})();
