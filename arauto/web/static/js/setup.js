(function () {
  "use strict";
  const { $, esc, json, aviso } = window.TC;

  const estado = {
    passo: 1,
    max: 4,
    usuario: "",
    senha: "",
    loja: "",
    modo: "INTERNAL",
    url: "",
    txt: "",
    tabela: "",
    colunas: {
      barcode: "",
      barcode_alt: "",
      description: "",
      price1: "",
      price2: "",
    },
    autostart: false,
    presetId: "",
    amostraOffset: 0,
    amostraCodigo: "",
  };

  let dialectos = [];
  let tabelas = [];
  let colsTabela = [];
  let mapaIdx = 0;

  const MAPA_PASSOS = [
    { id: "tabela", titulo: "Tabela de produtos", dica: "Onde o ERP/PDV guarda o cadastro.", obrigatorio: true },
    { id: "barcode", titulo: "Coluna do código de barras", dica: "EAN, GTIN ou código que o scanner lê.", obrigatorio: true },
    { id: "barcode_alt", titulo: "Código extra (opcional)", dica: "PLU / referência quando o código de barras vem vazio. Pode pular.", obrigatorio: false },
    { id: "description", titulo: "Coluna da descrição", dica: "Nome do produto na tela do terminal.", obrigatorio: true },
    { id: "price1", titulo: "Coluna do preço", dica: "Preço principal mostrado ao cliente.", obrigatorio: true },
    { id: "price2", titulo: "Segundo preço (opcional)", dica: "Atacado, associado, etc. Pode pular.", obrigatorio: false },
  ];

  function enc(s) { return encodeURIComponent(s || ""); }

  function dialectoAtual() {
    const id = ($("url-dialecto") && $("url-dialecto").value) || "";
    return dialectos.find((d) => d.id === id) || dialectos[0] || null;
  }

  function visibilidadeUrl() {
    const d = dialectoAtual();
    const sqlite = d && d.id === "sqlite";
    const arquivo = !!(d && d.arquivo);
    if ($("url-campo-host")) $("url-campo-host").hidden = sqlite;
    if ($("url-campo-porta")) $("url-campo-porta").hidden = sqlite || !d || d.porta == null;
    if ($("url-campo-user")) $("url-campo-user").hidden = sqlite;
    if ($("url-campo-pass")) $("url-campo-pass").hidden = sqlite;
    if ($("url-db-label")) $("url-db-label").textContent = arquivo ? "Arquivo do banco" : "Nome do banco";
  }

  function avancadoLigado() {
    return !!($("url-avancado") && $("url-avancado").checked);
  }

  function atualizarResumoUrl() {
    const est = $("db-url-estado");
    if (est) est.textContent = estado.url ? "Conexão configurada" : "Nenhuma conexão configurada";
  }

  function montarUrl() {
    const d = dialectoAtual();
    const url = (window.TC && TC.montarSqlUrl)
      ? TC.montarSqlUrl(d, {
          avancado: avancadoLigado(),
          url: $("url-bruta") ? $("url-bruta").value : "",
          host: $("url-host") && $("url-host").value,
          porta: $("url-porta") && $("url-porta").value,
          user: $("url-user") && $("url-user").value,
          pass: $("url-pass") && $("url-pass").value,
          db: $("url-db") && $("url-db").value,
        })
      : "";
    const prev = $("url-builder-preview");
    if (prev) prev.textContent = url || "—";
    if ($("url-bruta") && !avancadoLigado()) $("url-bruta").value = url;
    return url;
  }

  function aplicarUrl(url) {
    estado.url = url || "";
    if ($("c_DB_URL")) $("c_DB_URL").value = estado.url;
    atualizarResumoUrl();
    return estado.url;
  }

  function aplicarModo() {
    const sel = document.querySelector('input[name="db-mode"]:checked');
    estado.modo = (sel && sel.value) || "INTERNAL";
    if ($("bloco-txt")) $("bloco-txt").hidden = estado.modo !== "EXTERNAL_TXT";
    if ($("bloco-sql")) $("bloco-sql").hidden = estado.modo !== "EXTERNAL_SQL";
    document.querySelectorAll(".inst-opcao").forEach((el) => {
      const inp = el.querySelector('input[name="db-mode"]');
      el.classList.toggle("inst-opcao--ativa", !!(inp && inp.checked));
    });
  }

  function pintarPassos() {
    document.querySelectorAll(".inst-passo").forEach((li) => {
      const n = Number(li.dataset.passo);
      li.classList.toggle("inst-passo--ativo", n === estado.passo);
      li.classList.toggle("inst-passo--ok", n < estado.passo);
    });
    for (let i = 1; i <= 4; i++) {
      const el = $("passo-" + i);
      if (el) el.hidden = i !== estado.passo;
    }
    if ($("btn-voltar")) $("btn-voltar").hidden = estado.passo === 1;
    if ($("btn-avancar")) {
      $("btn-avancar").textContent = estado.passo === estado.max ? "Concluir e entrar" : "Continuar";
    }
  }

  function precisaCampos() {
    return estado.modo === "EXTERNAL_SQL";
  }

  function atualizarResumo() {
    const box = $("setup-resumo");
    if (!box) return;
    const linhas = [
      ["Usuário", estado.usuario],
      ["Loja", estado.loja || "—"],
      ["Base", estado.modo === "INTERNAL" ? "Interna" : estado.modo === "EXTERNAL_TXT" ? "Arquivo texto" : "Banco externo"],
    ];
    if (estado.modo === "EXTERNAL_SQL") {
      linhas.push(["Tabela", estado.tabela || "—"]);
      linhas.push(["Código", estado.colunas.barcode || "—"]);
    }
    box.innerHTML = linhas.map((p) =>
      `<div><span class="meta-img">${esc(p[0])}</span><strong>${esc(p[1])}</strong></div>`
    ).join("");
  }

  function pintarAmostra(alvoDesc, alvoMeta, alvoBox, r) {
    const box = $(alvoBox);
    const desc = $(alvoDesc);
    const meta = $(alvoMeta);
    if (!box) return;
    if (!r || !r.ok || !r.produto) {
      box.hidden = false;
      if (desc) desc.textContent = (r && r.detail) || "Sem produto de teste ainda.";
      if (meta) meta.textContent = "";
      return;
    }
    const p = r.produto;
    box.hidden = false;
    if (desc) desc.textContent = p.descricao || "—";
    const bits = [];
    if (p.codigo) bits.push("Código " + p.codigo);
    if (p.codigo_adicional) bits.push("Extra " + p.codigo_adicional);
    if (p.preco1) bits.push("Preço " + p.preco1);
    if (p.preco2 && p.preco2 !== p.preco1) bits.push("Preço 2 " + p.preco2);
    if (meta) meta.textContent = bits.join(" · ");
  }

  async function carregarAmostra(avancar) {
    if (estado.modo !== "EXTERNAL_SQL") return;
    if (!estado.url || !estado.tabela || !estado.colunas.barcode || !estado.colunas.description || !estado.colunas.price1) {
      ["setup-amostra", "mapa-amostra"].forEach((id) => { const el = $(id); if (el) el.hidden = true; });
      return;
    }
    if (avancar) estado.amostraOffset = (estado.amostraOffset || 0) + 1;
    else estado.amostraOffset = 0;
    try {
      const r = await json("/api/config/amostra-produto", {
        method: "POST",
        body: {
          DB_URL: estado.url,
          DB_PRODUCT_TABLE_NAME: estado.tabela,
          DB_COL_BARCODE: estado.colunas.barcode,
          DB_COL_BARCODE_ALT: estado.colunas.barcode_alt,
          DB_COL_DESCRIPITION: estado.colunas.description,
          DB_COL_PRICE1: estado.colunas.price1,
          DB_COL_PRICE2: estado.colunas.price2,
          preset_id: estado.presetId || "",
          offset: estado.amostraOffset,
          excluir: avancar ? (estado.amostraCodigo || "") : "",
        },
      });
      if (r && r.ok && r.produto) {
        estado.amostraOffset = r.offset || 0;
        estado.amostraCodigo = r.produto.codigo || "";
      }
      pintarAmostra("setup-amostra-desc", "setup-amostra-meta", "setup-amostra", r);
      pintarAmostra("mapa-amostra-desc", "mapa-amostra-meta", "mapa-amostra", r);
    } catch (e) {
      pintarAmostra("setup-amostra-desc", "setup-amostra-meta", "setup-amostra", { ok: false, detail: e.message });
    }
  }

  function atualizarMapaResumo() {
    const box = $("mapa-resumo");
    const mini = $("setup-sql-mapa");
    const linha = estado.tabela
      ? ("Tabela " + estado.tabela +
         " · código " + (estado.colunas.barcode || "—") +
         " · extra " + (estado.colunas.barcode_alt || "—") +
         " · descrição " + (estado.colunas.description || "—") +
         " · preço " + (estado.colunas.price1 || "—"))
      : "";
    if (mini) {
      mini.hidden = !linha;
      mini.textContent = linha;
    }
    if (!box) return;
    if (estado.modo !== "EXTERNAL_SQL") {
      box.innerHTML = '<p class="meta-img">Este modo não precisa mapear colunas.</p>';
      return;
    }
    box.innerHTML =
      `<ul class="inst-lista-resumo">
        <li>Tabela <strong class="mono">${esc(estado.tabela || "—")}</strong></li>
        <li>Código <strong class="mono">${esc(estado.colunas.barcode || "—")}</strong></li>
        <li>Código extra <strong class="mono">${esc(estado.colunas.barcode_alt || "—")}</strong></li>
        <li>Descrição <strong class="mono">${esc(estado.colunas.description || "—")}</strong></li>
        <li>Preço <strong class="mono">${esc(estado.colunas.price1 || "—")}</strong></li>
        <li>Preço 2 <strong class="mono">${esc(estado.colunas.price2 || "—")}</strong></li>
      </ul>`;
    carregarAmostra();
  }

  function pickCol(cands) {
    const lower = colsTabela.map((c) => c.toLowerCase());
    for (const c of cands) {
      const i = lower.findIndex((x) => x.includes(c));
      if (i >= 0) return colsTabela[i];
    }
    return "";
  }

  function renderMapaPasso() {
    const passo = MAPA_PASSOS[mapaIdx];
    $("mapa-titulo").textContent = passo.titulo;
    $("mapa-dica").textContent = passo.dica;
    $("mapa-progresso").textContent = (mapaIdx + 1) + " de " + MAPA_PASSOS.length;
    $("mapa-voltar").disabled = mapaIdx === 0;
    $("mapa-pular").hidden = passo.obrigatorio;
    const corpo = $("mapa-corpo");
    if (passo.id === "tabela") {
      const f = "";
      corpo.innerHTML =
        `<input type="search" id="mapa-busca" placeholder="Filtrar tabelas…" autocomplete="off">
         <div class="sql-lista" id="mapa-lista"></div>`;
      const lista = $("mapa-lista");
      function paint(filtro) {
        const q = (filtro || "").toLowerCase();
        const itens = tabelas.filter((t) => !q || t.toLowerCase().indexOf(q) >= 0);
        if (!itens.length) {
          lista.innerHTML = '<p class="meta-img" style="padding:.6rem">Nenhuma tabela.</p>';
          return;
        }
        lista.innerHTML = itens.map((t) =>
          `<button type="button" class="sql-item mono${t === estado.tabela ? " sql-item--ativo" : ""}" data-t="${esc(t)}">${esc(t)}</button>`
        ).join("");
        lista.querySelectorAll("[data-t]").forEach((b) => {
          b.addEventListener("click", () => {
            estado.tabela = b.dataset.t;
            lista.querySelectorAll(".sql-item").forEach((x) => x.classList.toggle("sql-item--ativo", x === b));
          });
        });
      }
      paint("");
      $("mapa-busca").addEventListener("input", () => paint($("mapa-busca").value));
    } else {
      const atual = estado.colunas[passo.id] || "";
      corpo.innerHTML =
        `<input type="search" id="mapa-busca" placeholder="Filtrar colunas…" autocomplete="off">
         <div class="sql-lista" id="mapa-lista"></div>`;
      const lista = $("mapa-lista");
      function paint(filtro) {
        const q = (filtro || "").toLowerCase();
        const itens = colsTabela.filter((t) => !q || t.toLowerCase().indexOf(q) >= 0);
        lista.innerHTML = itens.map((t) =>
          `<button type="button" class="sql-item mono${t === estado.colunas[passo.id] ? " sql-item--ativo" : ""}" data-t="${esc(t)}">${esc(t)}</button>`
        ).join("");
        lista.querySelectorAll("[data-t]").forEach((b) => {
          b.addEventListener("click", () => {
            estado.colunas[passo.id] = b.dataset.t;
            lista.querySelectorAll(".sql-item").forEach((x) => x.classList.toggle("sql-item--ativo", x === b));
            carregarAmostra();
          });
        });
      }
      if (!atual) {
        if (passo.id === "barcode") estado.colunas.barcode = pickCol(["codigo_barra", "cod_barra", "ean", "gtin", "barcode", "barra"]);
        if (passo.id === "barcode_alt") estado.colunas.barcode_alt = pickCol(["referencia", "ref", "plu", "codigo_interno"]);
        if (passo.id === "description") estado.colunas.description = pickCol(["descricao", "description", "nome", "produto"]);
        if (passo.id === "price1") estado.colunas.price1 = pickCol(["prc_venda", "preco_venda", "preco", "price", "valor"]);
        if (passo.id === "price2") estado.colunas.price2 = pickCol(["prc_venda_prazo", "preco2", "price2"]);
      }
      paint("");
      $("mapa-busca").addEventListener("input", () => paint($("mapa-busca").value));
    }
  }

  async function carregarColunas() {
    const r = await json("/api/config/listar-colunas", {
      method: "POST",
      body: { DB_URL: estado.url, tabela: estado.tabela },
    });
    if (!r.ok) throw new Error(r.detail || "Não foi possível listar colunas.");
    colsTabela = r.colunas || [];
  }

  async function abrirMapa() {
    if (!estado.url) aplicarUrl(montarUrl());
    if (!estado.url) {
      aviso("Monte a conexão no passo anterior.", true);
      return;
    }
    const modal = $("modal-mapa");
    modal.hidden = false;
    $("mapa-corpo").innerHTML = '<p class="meta-img">Consultando tabelas…</p>';
    try {
      const r = await json("/api/config/listar-tabelas", {
        method: "POST",
        body: { DB_URL: estado.url },
      });
      if (!r.ok) throw new Error(r.detail || "Falha ao listar tabelas");
      tabelas = r.tabelas || [];
      mapaIdx = 0;
      renderMapaPasso();
    } catch (e) {
      $("mapa-corpo").innerHTML = `<p class="meta-img" style="color:var(--erro)">${esc(e.message)}</p>`;
      aviso(e.message, true);
    }
  }

  function fecharMapa() {
    $("modal-mapa").hidden = true;
    atualizarMapaResumo();
  }

  async function validarPasso1() {
    const usuario = ($("setup-usuario").value || "").trim();
    const senha = $("setup-senha").value || "";
    const senha2 = $("setup-senha2").value || "";
    const loja = ($("setup-loja").value || "").trim();
    if (usuario.length < 2) throw new Error("Informe um usuário.");
    if (senha.length < 6) throw new Error("A senha precisa ter pelo menos 6 caracteres.");
    if (senha !== senha2) throw new Error("As senhas não coincidem.");
    await json("/api/setup/conta", { method: "POST", body: { usuario, senha, loja } });
    estado.usuario = usuario;
    estado.senha = senha;
    estado.loja = loja;
  }

  function validarPasso2() {
    aplicarModo();
    if (estado.modo === "EXTERNAL_TXT") {
      estado.txt = ($("setup-txt").value || "").trim();
      if (!estado.txt) throw new Error("Informe o caminho do arquivo de produtos.");
    }
    if (estado.modo === "EXTERNAL_SQL") {
      if (!estado.url) aplicarUrl(montarUrl());
      if (!estado.url) throw new Error("Abra Configurar e monte a conexão com o banco.");
    }
  }

  function validarPasso3() {
    if (!precisaCampos()) return;
    if (!estado.tabela || !estado.colunas.barcode || !estado.colunas.description || !estado.colunas.price1) {
      throw new Error("Escolha tabela, código, descrição e preço.");
    }
  }

  async function concluir() {
    estado.autostart = !!($("setup-autostart") && $("setup-autostart").checked);
    await json("/api/setup/base", {
      method: "POST",
      body: {
        DB_MODE: estado.modo,
        PATH_FILE_PRODUCT: estado.txt,
        DB_URL: estado.url,
        DB_PRODUCT_TABLE_NAME: estado.tabela,
        DB_COL_BARCODE: estado.colunas.barcode,
        DB_COL_BARCODE_ALT: estado.colunas.barcode_alt,
        DB_COL_DESCRIPITION: estado.colunas.description,
        DB_COL_PRICE1: estado.colunas.price1,
        DB_COL_PRICE2: estado.colunas.price2,
      },
    });
    const r = await json("/api/setup/concluir", {
      method: "POST",
      body: { autostart: estado.autostart, loja: estado.loja },
    });
    location.href = r.redirect || "/painel";
  }

  async function avancar() {
    const btn = $("btn-avancar");
    btn.disabled = true;
    try {
      if (estado.passo === 1) await validarPasso1();
      else if (estado.passo === 2) {
        validarPasso2();
        if (!precisaCampos()) {
          estado.passo = 4;
          atualizarResumo();
          pintarPassos();
          return;
        }
      } else if (estado.passo === 3) validarPasso3();
      else if (estado.passo === 4) {
        await concluir();
        return;
      }
      estado.passo = Math.min(estado.max, estado.passo + 1);
      if (estado.passo === 4) atualizarResumo();
      if (estado.passo === 3) { atualizarMapaResumo(); carregarAmostra(); }
      pintarPassos();
    } catch (e) {
      aviso(e.message || "Não foi possível continuar", true);
    } finally {
      btn.disabled = false;
    }
  }

  function voltar() {
    if (estado.passo === 4 && !precisaCampos()) estado.passo = 2;
    else estado.passo = Math.max(1, estado.passo - 1);
    pintarPassos();
  }

  document.querySelectorAll('input[name="db-mode"]').forEach((el) => {
    el.addEventListener("change", aplicarModo);
  });
  if ($("btn-avancar")) $("btn-avancar").addEventListener("click", avancar);
  if ($("btn-voltar")) $("btn-voltar").addEventListener("click", voltar);
  if ($("btn-abrir-mapa")) $("btn-abrir-mapa").addEventListener("click", abrirMapa);
  if ($("mapa-fechar")) $("mapa-fechar").addEventListener("click", fecharMapa);
  if ($("modal-mapa-fundo")) $("modal-mapa-fundo").addEventListener("click", fecharMapa);
  if ($("mapa-voltar")) {
    $("mapa-voltar").addEventListener("click", () => {
      if (mapaIdx > 0) {
        mapaIdx -= 1;
        renderMapaPasso();
      }
    });
  }
  if ($("mapa-pular")) {
    $("mapa-pular").addEventListener("click", () => {
      const passo = MAPA_PASSOS[mapaIdx];
      if (passo && !passo.obrigatorio) estado.colunas[passo.id] = "";
      if (mapaIdx >= MAPA_PASSOS.length - 1) fecharMapa();
      else {
        mapaIdx += 1;
        renderMapaPasso();
      }
    });
  }
  if ($("mapa-ok")) {
    $("mapa-ok").addEventListener("click", async () => {
      const passo = MAPA_PASSOS[mapaIdx];
      try {
        if (passo.id === "tabela") {
          if (!estado.tabela) throw new Error("Selecione uma tabela.");
          await carregarColunas();
        } else if (passo.obrigatorio && !estado.colunas[passo.id]) {
          throw new Error("Selecione uma coluna.");
        }
        if (mapaIdx >= MAPA_PASSOS.length - 1) {
          fecharMapa();
          return;
        }
        mapaIdx += 1;
        renderMapaPasso();
      } catch (e) {
        aviso(e.message, true);
      }
    });
  }

  (window.ARAUTO_PRESETS_BASE || []).forEach((preset) => {
    document.querySelectorAll('[data-preset-id="' + preset.id + '"]').forEach((btn) => {
      btn.addEventListener("click", () => {
        const v = preset.valores || {};
        document.querySelectorAll('input[name="db-mode"]').forEach((r) => {
          r.checked = r.value === (v.DB_MODE || "EXTERNAL_SQL");
        });
        aplicarModo();
        if (v.DB_URL) {
          estado.url = v.DB_URL;
          if ($("c_DB_URL")) $("c_DB_URL").value = v.DB_URL;
          try {
            const raw = v.DB_URL;
            const d = dialectos.find((x) => raw.startsWith(x.scheme + "://"));
            if (d && $("url-dialecto")) $("url-dialecto").value = d.id;
            visibilidadeUrl();
            const sem = raw.slice(((d && d.scheme) || "").length + 3);
            let rest = sem, user = "", pass = "", host = "", porta = "", db = "";
            if (rest.indexOf("@") >= 0) {
              const cred = rest.slice(0, rest.indexOf("@"));
              rest = rest.slice(rest.indexOf("@") + 1);
              if (cred.indexOf(":") >= 0) {
                user = decodeURIComponent(cred.split(":")[0] || "");
                pass = decodeURIComponent(cred.split(":").slice(1).join(":") || "");
              } else user = decodeURIComponent(cred);
            }
            const slash = rest.indexOf("/");
            const hostport = slash >= 0 ? rest.slice(0, slash) : rest;
            db = slash >= 0 ? rest.slice(slash + 1).split("?")[0] : "";
            if (hostport.indexOf(":") >= 0) {
              host = hostport.split(":")[0];
              porta = hostport.split(":")[1].split("?")[0];
            } else host = hostport;
            if ($("url-host")) $("url-host").value = host || "localhost";
            if ($("url-porta")) $("url-porta").value = porta || (d && d.porta) || "";
            if ($("url-user")) $("url-user").value = user;
            if ($("url-pass")) $("url-pass").value = pass;
            if ($("url-db")) $("url-db").value = db;
          } catch (e) {}
          aplicarUrl(v.DB_URL);
        }
        estado.presetId = preset.id || "";
        estado.tabela = v.DB_PRODUCT_TABLE_NAME || "";
        document.querySelectorAll(".preset-base").forEach((b) => {
          b.classList.toggle("preset-base--ativo", b.getAttribute("data-preset-id") === preset.id);
        });
        estado.colunas.barcode = v.DB_COL_BARCODE || "";
        estado.colunas.barcode_alt = v.DB_COL_BARCODE_ALT || "";
        estado.colunas.description = v.DB_COL_DESCRIPITION || "";
        estado.colunas.price1 = v.DB_COL_PRICE1 || "";
        estado.colunas.price2 = v.DB_COL_PRICE2 || "";
        const nota = $("setup-preset-nota");
        if (nota) {
          nota.hidden = !preset.nota;
          nota.textContent = preset.nota || "";
        }
        aviso(
          "Preset \"" + preset.nome + "\" aplicado. Tabela " +
          (estado.tabela || "—") +
          (estado.colunas.barcode ? " · " + estado.colunas.barcode : "") +
          (estado.colunas.description ? " · " + estado.colunas.description : "") +
          (estado.colunas.price1 ? " · " + estado.colunas.price1 : "") +
          ". Teste a conexão."
        );
        atualizarMapaResumo();
        const prev = $("setup-mapa-preview");
        if (prev && estado.tabela) {
          prev.hidden = false;
          prev.innerHTML =
            `<p class="dica">Mapeamento do preset (já vai no teste):</p>
             <p class="mono">${esc(estado.tabela)} · ${esc(estado.colunas.barcode)} · ${esc(estado.colunas.description)} · ${esc(estado.colunas.price1)}</p>`;
        }
      });
    });
  });

  ["url-dialecto", "url-host", "url-porta", "url-user", "url-pass", "url-db"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("change", () => {
      if (id === "url-dialecto") {
        const d = dialectoAtual();
        if (d) {
          if ($("url-porta") && d.porta != null) $("url-porta").value = d.porta;
          if ($("url-user") && d.usuario_padrao && !$("url-user").value) $("url-user").value = d.usuario_padrao;
          if ($("url-pass") && d.senha_padrao && !$("url-pass").value) $("url-pass").value = d.senha_padrao;
        }
        visibilidadeUrl();
      }
      montarUrl();
    });
    el.addEventListener("input", montarUrl);
  });

  function abrirModalUrl() {
    const box = $("modal-url");
    if (!box) { aviso("Modal de URL não encontrado.", true); return; }
    if ($("url-avancado")) $("url-avancado").checked = false;
    if ($("url-campo-avancado")) $("url-campo-avancado").hidden = true;
    if ($("url-campos-simples")) $("url-campos-simples").hidden = false;
    visibilidadeUrl();
    montarUrl();
    if ($("url-bruta")) $("url-bruta").value = estado.url || "";
    box.hidden = false;
    const first = $("url-dialecto") || $("url-host");
    if (first) first.focus();
  }
  function fecharModalUrl() {
    const box = $("modal-url");
    if (box) box.hidden = true;
  }
  if ($("btn-montar-url")) $("btn-montar-url").addEventListener("click", (ev) => { ev.preventDefault(); abrirModalUrl(); });
  if ($("modal-url-fechar")) $("modal-url-fechar").addEventListener("click", fecharModalUrl);
  if ($("modal-url-cancelar")) $("modal-url-cancelar").addEventListener("click", fecharModalUrl);
  if ($("modal-url-fundo")) $("modal-url-fundo").addEventListener("click", fecharModalUrl);
  if ($("modal-url-aplicar")) {
    $("modal-url-aplicar").addEventListener("click", () => {
      aplicarUrl(montarUrl());
      fecharModalUrl();
      aviso("URL montada. Teste a conexão antes de continuar.", "info");
    });
  }
  if ($("url-avancado")) {
    $("url-avancado").addEventListener("change", () => {
      const on = avancadoLigado();
      if ($("url-campo-avancado")) $("url-campo-avancado").hidden = !on;
      if ($("url-campos-simples")) $("url-campos-simples").hidden = on;
      if (on && $("url-bruta") && !$("url-bruta").value) $("url-bruta").value = montarUrl();
      montarUrl();
    });
  }
  if ($("url-bruta")) $("url-bruta").addEventListener("input", montarUrl);
  document.addEventListener("keydown", (ev) => {
    const box = $("modal-url");
    if (ev.key === "Escape" && box && !box.hidden) fecharModalUrl();
  });

  if ($("btn-testar-sql")) {
    $("btn-testar-sql").addEventListener("click", async () => {
      if (!estado.url) aplicarUrl(montarUrl());
      const out = $("testar-sql-resultado");
      try {
        const r = await json("/api/config/testar-sql", {
          method: "POST",
          body: {
            DB_URL: estado.url,
            DB_PRODUCT_TABLE_NAME: estado.tabela,
            DB_COL_BARCODE: estado.colunas.barcode,
            DB_COL_BARCODE_ALT: estado.colunas.barcode_alt,
            DB_COL_DESCRIPITION: estado.colunas.description,
            DB_COL_PRICE1: estado.colunas.price1,
            DB_COL_PRICE2: estado.colunas.price2,
            preset_id: estado.presetId || "",
          },
        });
        if (out) {
          out.textContent = r.detail || (r.ok ? "Conexão ok" : "Falha");
          out.style.color = r.ok ? "var(--ok)" : "var(--erro)";
        }
        aviso(r.detail || (r.ok ? "Conexão ok" : "Falha"), !r.ok);
      } catch (e) {
        if (out) { out.textContent = e.message; out.style.color = "var(--erro)"; }
        aviso(e.message, true);
      }
    });
  }

  json("/api/config/dialectos").then((r) => {
    dialectos = (r && r.itens) || [];
    const sel = $("url-dialecto");
    if (!sel) return;
    if (!dialectos.length) {
      sel.innerHTML = '<option value="">Nenhum driver SQL instalado</option>';
      return;
    }
    sel.innerHTML = dialectos.map((d) =>
      `<option value="${esc(d.id)}">${esc(d.rotulo)}${d.instalado === false ? " (instale o driver)" : ""}</option>`
    ).join("");
    visibilidadeUrl();
    montarUrl();
    atualizarResumoUrl();
  }).catch(() => {});

  const st = window.ARAUTO_AUTOSTART || {};
  if ($("autostart-motivo")) $("autostart-motivo").textContent = st.motivo || "";
  if ($("bloco-autostart")) {
    $("bloco-autostart").hidden = st.disponivel === false;
    if (st.disponivel === false && $("autostart-dica")) {
      $("autostart-dica").textContent = st.motivo || "Esta instalação não gerencia a inicialização do sistema.";
    }
    if (st.ativo && $("setup-autostart")) $("setup-autostart").checked = true;
  }
  ["btn-setup-amostra-reload", "btn-mapa-amostra-reload"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("click", (ev) => { ev.preventDefault(); carregarAmostra(true); });
  });

  function aplicarTema(tema) {
    const t = tema === "escuro" ? "escuro" : "claro";
    document.documentElement.dataset.tema = t;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", t === "claro" ? "#e7edf5" : "#161826");
    try { localStorage.setItem("arauto.tema", t); } catch (e) {}
    document.querySelectorAll(".inst-tema").forEach((b) => {
      b.classList.toggle("inst-tema--ativo", b.dataset.tema === t);
    });
  }

  document.querySelectorAll(".inst-tema").forEach((btn) => {
    btn.addEventListener("click", () => aplicarTema(btn.dataset.tema));
  });
  aplicarTema(document.documentElement.dataset.tema || "claro");

  if ($("inst-intro-iniciar")) {
    $("inst-intro-iniciar").addEventListener("click", () => {
      const intro = $("inst-intro");
      const principal = $("inst-principal");
      document.body.classList.remove("inst-body--intro");
      if (intro) intro.hidden = true;
      if (principal) principal.hidden = false;
      const primeiro = $("setup-loja") || $("setup-usuario");
      if (primeiro) primeiro.focus();
    });
  }

  if ($("btn-tema-setup")) {
    $("btn-tema-setup").addEventListener("click", () => {
      aplicarTema(document.documentElement.dataset.tema === "claro" ? "escuro" : "claro");
    });
  }

  aplicarModo();
  pintarPassos();
})();
