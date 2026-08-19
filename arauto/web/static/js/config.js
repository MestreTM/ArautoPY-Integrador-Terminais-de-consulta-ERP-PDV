/* Tela de configuração: salva o formulário e simula códigos de balança. */
(function () {
  "use strict";

  const { $, esc, json, aviso } = window.TC;
  const form = $("form-config");

  /* Navegação por seções na barra lateral. */
  function ativarSecao(id) {
    document.querySelectorAll("[data-secao]").forEach((sec) => {
      sec.classList.toggle("config-secao--ativa", sec.id === id);
    });
    document.querySelectorAll(".config-nav-item").forEach((btn) => {
      btn.classList.toggle("config-nav-item--ativo", btn.dataset.secao === id);
    });
    const alvo = document.getElementById(id);
    if (alvo) {
      alvo.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  document.querySelectorAll(".config-nav-item").forEach((btn) => {
    btn.addEventListener("click", () => ativarSecao(btn.dataset.secao));
  });

  /* Campos que só fazem sentido em certos modos de base ficam escondidos.
     Mostrar DB_URL com a base interna ligada só confunde quem configura. */
  function aplicarDependencias() {
    const modo = form.elements["DB_MODE"] ? form.elements["DB_MODE"].value : "";
    document.querySelectorAll("[data-depende]").forEach((campo) => {
      const aceitos = campo.dataset.depende.split(",").map((s) => s.trim());
      campo.hidden = !aceitos.includes(modo);
    });
  }

  if (form.elements["DB_MODE"]) {
    form.elements["DB_MODE"].addEventListener("change", aplicarDependencias);
  }
  aplicarDependencias();

  function coletar() {
    const config = {};
    Array.from(form.elements).forEach((el) => {
      if (!el.name) return;
      config[el.name] = el.type === "checkbox" ? String(el.checked) : el.value;
    });
    return { config };
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const botao = $("btn-salvar");
    botao.disabled = true;
    try {
      const r = await json("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(coletar()),
      });
      let msg = "Configuração salva.";
      if (r.aplicado_em_quente && r.aplicado_em_quente.length) {
        msg += " " + r.aplicado_em_quente.join(" · ") + ".";
      }
      if (r.erros_aplicacao && r.erros_aplicacao.length) {
        aviso(msg + " Atenção: " + r.erros_aplicacao.join(" · "), true);
      } else if (r.reinicio_necessario) {
        aviso(msg + " Portas do WebViewer/API ainda exigem reiniciar o processo.");
      } else {
        aviso(msg);
      }
    } catch (e) {
      aviso("Não foi possível salvar: " + e.message, true);
    } finally {
      botao.disabled = false;
    }
  });

  $("btn-descartar").addEventListener("click", () => location.reload());

  $("btn-recarregar").addEventListener("click", async (ev) => {
    const botao = ev.currentTarget;
    const rotulo = botao.textContent;
    botao.disabled = true;
    botao.textContent = "Recarregando…";
    try {
      const r = await json("/api/recarregar", { method: "POST" });
      aviso(`Base recarregada: ${r.produtos} produto(s).`);
    } catch (e) {
      aviso("Falha ao recarregar: " + e.message, true);
    } finally {
      botao.disabled = false;
      botao.textContent = rotulo;
    }
  });

  /* -------------------------------------------- máscara da etiqueta */
  const entradaMascara = $("campo-mascara");

  /* A régua numera cada posição sob a máscara. Sem isso, contar "em que
     posição começa o total" vira exercício de olho, e errar aqui muda o preço
     que o cliente vê. */
  function desenharRegua() {
    const mascara = entradaMascara.value.trim().toUpperCase();
    $("regua").innerHTML = mascara.split("").map((c, i) =>
      `<span class="casa m-${esc(c)}"><b>${esc(c)}</b><i>${i + 1}</i></span>`).join("");
    $("campo-comprimento").value = mascara.length;
    $("campo-tamanho").value = (mascara.match(/C/g) || []).length;
    $("mascara-atual").textContent = mascara;
  }

  async function validarMascara() {
    desenharRegua();
    const erro = $("mascara-erro");
    try {
      const r = await json("/api/balanca/simular?codigo=0&mascara=" +
                           encodeURIComponent(entradaMascara.value.trim()));
      // só o texto da máscara importa aqui; o código 0 nunca casa
      const invalida = r.ok === false && /máscara|C \(código|P \(peso|posições/i.test(r.motivo || "");
      erro.hidden = !invalida;
      if (invalida) erro.textContent = r.motivo;
    } catch (e) { erro.hidden = true; }
  }

  entradaMascara.addEventListener("input", validarMascara);
  desenharRegua();

  document.querySelectorAll(".pronta").forEach((botao) =>
    botao.addEventListener("click", () => {
      entradaMascara.value = botao.dataset.mascara;
      validarMascara();
      $("btn-simular").click();
    }));

  /* --------------------------------------------------------- simulador */
  $("btn-simular").addEventListener("click", async () => {
    const codigo = $("sim-codigo").value.trim();
    const saida = $("sim-saida");
    saida.hidden = false;

    try {
      const busca = new URLSearchParams({ codigo, mascara: entradaMascara.value.trim() });
      const r = await json("/api/balanca/simular?" + busca.toString());

      if (!r.ok) {
        saida.className = "sim-saida erro";
        saida.textContent = r.motivo;
        return;
      }

      const linhas = [
        `código lido &nbsp;&nbsp; <b>${esc(r.codigo)}</b>`,
        `tipo &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${esc(r.descricao_tipo)}`,
        `produto &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>${esc(r.codigo_produto)}</b>`,
      ];
      if (r.total !== undefined) linhas.push(`total lido &nbsp;&nbsp; <b>${esc(r.total)}</b>`);
      if (r.peso !== undefined) linhas.push(`peso lido &nbsp;&nbsp;&nbsp; <b>${r.peso}</b> kg`);
      if (r.dv_confere === false) {
        linhas.push(`<span style="color:var(--alerta)">dígito verificador do EAN não confere</span>`);
      }

      if (r.encontrado) {
        linhas.push(`cadastro &nbsp;&nbsp;&nbsp;&nbsp; ${esc(r.codigo_cadastro)} — ${esc(r.descricao)}`);
        linhas.push(`preço/kg &nbsp;&nbsp;&nbsp;&nbsp; ${esc(r.preco_unitario || "—")}`);
        linhas.push(`<span style="color:var(--ok)">preço final &nbsp; <b>${esc(r.preco_final)}</b></span>`);
        if (r.peso_final !== undefined && r.peso_estimado) {
          linhas.push(`<span class="obs">peso ${r.peso_final} kg deduzido do preço do cadastro; ` +
                      `só bate se o cadastro estiver com o preço do dia</span>`);
        }
      } else {
        linhas.push(`<span style="color:var(--alerta)">nenhum cadastro para ` +
                    `${esc(r.candidatos.join(" / "))}</span>`);
      }
      saida.className = "sim-saida";
      saida.innerHTML = linhas.join("<br>");
    } catch (e) {
      saida.className = "sim-saida erro";
      saida.textContent = "Falha ao simular: " + e.message;
    }
  });

  $("sim-codigo").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); $("btn-simular").click(); }
  });


  /* ---------------------------------------------------- base de imagens */
  async function atualizarStatusImagens() {
    const badge = $("img-badge");
    const det = $("img-detalhe");
    const pasta = $("img-pasta");
    if (!badge) return;
    try {
      const st = await json("/api/imagens/status");
      if (pasta) pasta.textContent = st.pasta || "—";
      if (st.em_andamento) {
        badge.className = "badge-img badge-img--warn";
        badge.textContent = "Baixando…";
        det.textContent = (st.mensagem || "Download em andamento") +
          " · " + (st.arquivos_locais || 0) + " na pasta";
        return st;
      }
      if (st.baixado && !st.ultimo_erro) {
        badge.className = "badge-img badge-img--ok";
        badge.textContent = "Base disponível";
        det.textContent =
          (st.arquivos_locais || st.arquivos || 0) + " imagens locais" +
          (st.ultimo_ok ? " · última vez: " + st.ultimo_ok : "");
      } else if (st.ultimo_erro) {
        badge.className = "badge-img badge-img--no";
        badge.textContent = "Erro no download";
        det.textContent = st.ultimo_erro;
      } else {
        badge.className = "badge-img badge-img--warn";
        badge.textContent = "Ainda não baixada";
        det.textContent = "Nenhum pacote concluído nesta instalação.";
      }
      return st;
    } catch (e) {
      badge.className = "badge-img badge-img--no";
      badge.textContent = "Indisponível";
      det.textContent = e.message;
    }
  }

  if ($("btn-status-imagens")) {
    $("btn-status-imagens").addEventListener("click", () => atualizarStatusImagens());
  }

  if ($("btn-baixar-imagens")) {
    $("btn-baixar-imagens").addEventListener("click", async () => {
      const btn = $("btn-baixar-imagens");
      btn.disabled = true;
      const rotulo = btn.textContent;
      btn.textContent = "Iniciando…";
      try {
        await json("/api/imagens/baixar-pacote", { method: "POST" });
        aviso("Download do GitHub iniciado — EAN iguais serão atualizados; demais permanecem.");
        const timer = setInterval(async () => {
          const st = await atualizarStatusImagens();
          if (st && st.em_andamento) {
            btn.textContent = "Baixando…";
            return;
          }
          clearInterval(timer);
          btn.disabled = false;
          btn.textContent = rotulo;
          if (st && st.baixado) aviso("Pacote GitHub aplicado.");
          else if (st && st.ultimo_erro) aviso("Falha: " + st.ultimo_erro, true);
        }, 2000);
      } catch (e) {
        aviso("Não foi possível iniciar: " + e.message, true);
        btn.disabled = false;
        btn.textContent = rotulo;
      }
    });
  }

  if ($("btn-limpar-imagens")) {
    $("btn-limpar-imagens").addEventListener("click", async () => {
      if (!confirm("Apagar TODAS as imagens locais? Esta ação não desfaz.")) return;
      try {
        const r = await json("/api/imagens/limpar", { method: "POST" });
        aviso("Banco de imagens limpo: " + (r.apagados || 0) + " arquivo(s).");
        atualizarStatusImagens();
      } catch (e) {
        aviso("Falha ao limpar: " + e.message, true);
      }
    });
  }

  if ($("btn-apagar-ean")) {
    $("btn-apagar-ean").addEventListener("click", async () => {
      const ean = ($("img-ean-apagar").value || "").trim();
      if (!ean) {
        aviso("Informe o código EAN.", true);
        return;
      }
      if (!confirm("Apagar a imagem local do código " + ean + "?")) return;
      try {
        const r = await json("/api/imagens/apagar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ean }),
        });
        aviso("Removido: " + (r.arquivo || r.ean || ean));
        $("img-ean-apagar").value = "";
        atualizarStatusImagens();
      } catch (e) {
        aviso(e.message || "Imagem não encontrada", true);
      }
    });
    $("img-ean-apagar").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        $("btn-apagar-ean").click();
      }
    });
  }

  atualizarStatusImagens();



  /* ---------------------------------------------------- presets base SQL */
  const PRESETS_BASE = window.ARAUTO_PRESETS_BASE || [];

  function setCampo(chave, valor) {
    const el = $("c_" + chave);
    if (!el) return;
    if (el.type === "checkbox") {
      el.checked = String(valor).toLowerCase() === "true";
    } else {
      el.value = valor == null ? "" : String(valor);
    }
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  document.querySelectorAll(".preset-base").forEach((botao) => {
    botao.addEventListener("click", () => {
      const id = botao.dataset.presetId;
      const preset = PRESETS_BASE.find((p) => p.id === id);
      if (!preset) {
        aviso("Preset não encontrado.", true);
        return;
      }
      const vals = preset.valores || {};
      Object.keys(vals).forEach((k) => setCampo(k, vals[k]));
      if (typeof aplicarDependencias === "function") aplicarDependencias();
      const nota = $("preset-base-nota");
      if (nota) {
        if (preset.nota) {
          nota.hidden = false;
          nota.textContent = preset.nota;
        } else {
          nota.hidden = true;
          nota.textContent = "";
        }
      }
      aviso("Preset \"" + preset.nome + "\" aplicado. Confira a URL e salve.");
    });
  });



  /* ---------------------------------------------------- testar SQL */
  if ($("btn-testar-sql")) {
    $("btn-testar-sql").addEventListener("click", async () => {
      const btn = $("btn-testar-sql");
      const out = $("testar-sql-resultado");
      btn.disabled = true;
      const rotulo = btn.textContent;
      btn.textContent = "Testando…";
      if (out) {
        out.hidden = false;
        out.textContent = "Conectando…";
        out.style.color = "var(--texto-2)";
      }
      try {
        const corpo = {
          DB_URL: ($("c_DB_URL") && $("c_DB_URL").value) || "",
          DB_PRODUCT_TABLE_NAME: ($("c_DB_PRODUCT_TABLE_NAME") && $("c_DB_PRODUCT_TABLE_NAME").value) || "",
          DB_COL_BARCODE: ($("c_DB_COL_BARCODE") && $("c_DB_COL_BARCODE").value) || "",
          DB_COL_DESCRIPITION: ($("c_DB_COL_DESCRIPITION") && $("c_DB_COL_DESCRIPITION").value) || "",
          DB_COL_PRICE1: ($("c_DB_COL_PRICE1") && $("c_DB_COL_PRICE1").value) || "",
          DB_COL_PRICE2: ($("c_DB_COL_PRICE2") && $("c_DB_COL_PRICE2").value) || "",
        };
        const r = await json("/api/config/testar-sql", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(corpo),
        });
        const ok = !!r.ok;
        if (out) {
          out.hidden = false;
          out.textContent = r.detail || (ok ? "OK" : "Falha");
          out.style.color = ok ? "var(--ok, #6ddea0)" : "var(--alerta, #ff8a80)";
        }
        aviso(r.detail || (ok ? "Conexão ok" : "Falha na conexão"), !ok);
      } catch (e) {
        if (out) {
          out.hidden = false;
          out.textContent = e.message;
          out.style.color = "var(--alerta, #ff8a80)";
        }
        aviso("Teste falhou: " + e.message, true);
      } finally {
        btn.disabled = false;
        btn.textContent = rotulo;
      }
    });
  }



  /* ---------------------------------------------------- helper tabelas SQL */
  const modalSql = $("modal-sql");
  let _sqlTabelas = [];
  let _sqlColunas = [];
  let _sqlTabelaSel = "";

  function abrirModalSql() {
    const el = $("modal-sql");
    if (!el) {
      console.warn("modal-sql não encontrado no DOM");
      aviso("Popup de tabelas não carregou. Recarregue a página.", true);
      return;
    }
    el.hidden = false;
    el.classList.add("is-open");
    el.removeAttribute("hidden");
    el.style.display = "flex";
  }
  function fecharModalSql() {
    const el = $("modal-sql");
    if (!el) return;
    el.hidden = true;
    el.classList.remove("is-open");
    el.setAttribute("hidden", "");
    el.style.display = "none";
  }

  function renderListaTabelas(filtro) {
    const box = $("sql-lista-tabelas");
    if (!box) return;
    const f = (filtro || "").trim().toLowerCase();
    const itens = _sqlTabelas.filter((t) => !f || t.toLowerCase().includes(f));
    if (!itens.length) {
      box.innerHTML = '<p class="meta-img" style="padding:.6rem">Nenhuma tabela com esse filtro.</p>';
      return;
    }
    box.innerHTML = itens.map((t) =>
      `<button type="button" class="sql-item mono${t === _sqlTabelaSel ? " sql-item--ativo" : ""}" data-tabela="${esc(t)}">${esc(t)}</button>`
    ).join("");
    box.querySelectorAll(".sql-item").forEach((btn) => {
      btn.addEventListener("click", () => selecionarTabela(btn.dataset.tabela));
    });
  }

  function preencherSelectsColunas(cols) {
    const ids = [
      ["sql-col-barcode", "c_DB_COL_BARCODE"],
      ["sql-col-description", "c_DB_COL_DESCRIPITION"],
      ["sql-col-price1", "c_DB_COL_PRICE1"],
      ["sql-col-price2", "c_DB_COL_PRICE2"],
    ];
    ids.forEach(([selId, formId]) => {
      const sel = $(selId);
      if (!sel) return;
      const atual = ($(formId) && $(formId).value) || sel.value || "";
      sel.innerHTML = '<option value="">—</option>' +
        cols.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
      if (atual && cols.includes(atual)) sel.value = atual;
      // heurística leve se vazio
      if (!sel.value) {
        const nome = selId;
        const lower = cols.map((c) => c.toLowerCase());
        const pick = (cands) => {
          for (const c of cands) {
            const i = lower.findIndex((x) => x.includes(c));
            if (i >= 0) return cols[i];
          }
          return "";
        };
        if (nome.includes("barcode")) sel.value = pick(["codigo_barra", "cod_barra", "ean", "gtin", "barcode", "barra"]);
        if (nome.includes("description")) sel.value = pick(["descricao", "description", "nome", "produto"]);
        if (nome.includes("price1")) sel.value = pick(["prc_venda", "preco_venda", "preco", "price", "valor"]);
        if (nome.includes("price2")) sel.value = pick(["prc_venda_prazo", "preco2", "price2"]);
      }
    });
  }

  async function selecionarTabela(nome) {
    _sqlTabelaSel = nome;
    if ($("sql-tabela-sel")) $("sql-tabela-sel").textContent = nome;
    renderListaTabelas(($("sql-busca-tabela") && $("sql-busca-tabela").value) || "");
    const passo = $("sql-passo-colunas");
    const status = $("sql-cols-status");
    if (passo) passo.hidden = false;
    if (status) status.textContent = "Carregando colunas…";
    if ($("modal-sql-aplicar")) $("modal-sql-aplicar").disabled = true;
    try {
      const r = await json("/api/config/listar-colunas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          DB_URL: ($("c_DB_URL") && $("c_DB_URL").value) || "",
          tabela: nome,
        }),
      });
      if (!r.ok) {
        if (status) status.textContent = r.detail || "Falha ao listar colunas";
        return;
      }
      _sqlColunas = r.colunas || [];
      preencherSelectsColunas(_sqlColunas);
      if (status) status.textContent = _sqlColunas.length + " coluna(s)";
      if ($("modal-sql-aplicar")) $("modal-sql-aplicar").disabled = false;
    } catch (e) {
      if (status) status.textContent = e.message;
    }
  }

  if ($("btn-mostrar-tabelas")) {
    $("btn-mostrar-tabelas").addEventListener("click", async () => {
      const btn = $("btn-mostrar-tabelas");
      const url = ($("c_DB_URL") && $("c_DB_URL").value) || "";
      if (!url.trim()) {
        aviso("Preencha a URL de conexão antes.", true);
        return;
      }
      btn.disabled = true;
      const rotulo = btn.textContent;
      btn.textContent = "Carregando…";
      abrirModalSql();
      const box = $("sql-lista-tabelas");
      if (box) box.innerHTML = '<p class="meta-img" style="padding:.6rem">Consultando banco…</p>';
      try {
        const r = await json("/api/config/listar-tabelas", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ DB_URL: url }),
        });
        if (!r.ok) {
          if (box) box.innerHTML = `<p class="meta-img" style="padding:.6rem;color:var(--alerta)">${esc(r.detail || "Erro")}</p>`;
          aviso(r.detail || "Falha ao listar tabelas", true);
          return;
        }
        _sqlTabelas = r.tabelas || [];
        _sqlTabelaSel = ($("c_DB_PRODUCT_TABLE_NAME") && $("c_DB_PRODUCT_TABLE_NAME").value) || "";
        if ($("sql-tabela-sel")) $("sql-tabela-sel").textContent = _sqlTabelaSel || "—";
        renderListaTabelas("");
        if (_sqlTabelaSel && _sqlTabelas.includes(_sqlTabelaSel)) {
          selecionarTabela(_sqlTabelaSel);
        } else if ($("sql-passo-colunas")) {
          $("sql-passo-colunas").hidden = true;
        }
        aviso((_sqlTabelas.length || 0) + " tabela(s) encontrada(s).");
      } catch (e) {
        if (box) box.innerHTML = `<p class="meta-img" style="padding:.6rem;color:var(--alerta)">${esc(e.message)}</p>`;
        aviso("Falha: " + e.message, true);
      } finally {
        btn.disabled = false;
        btn.textContent = rotulo;
      }
    });
  }

  if ($("sql-busca-tabela")) {
    $("sql-busca-tabela").addEventListener("input", () => {
      renderListaTabelas($("sql-busca-tabela").value);
    });
  }

  // filtro de colunas nos selects (simples: esconde options)
  if ($("sql-busca-coluna")) {
    $("sql-busca-coluna").addEventListener("input", () => {
      const f = ($("sql-busca-coluna").value || "").trim().toLowerCase();
      ["sql-col-barcode", "sql-col-description", "sql-col-price1", "sql-col-price2"].forEach((id) => {
        const sel = $(id);
        if (!sel) return;
        Array.from(sel.options).forEach((opt, i) => {
          if (i === 0) { opt.hidden = false; return; }
          opt.hidden = !!(f && !opt.value.toLowerCase().includes(f));
        });
      });
    });
  }

  function aplicarMapeamentoSql() {
    if (!_sqlTabelaSel) {
      aviso("Selecione uma tabela.", true);
      return;
    }
    const barcode = ($("sql-col-barcode") && $("sql-col-barcode").value) || "";
    const desc = ($("sql-col-description") && $("sql-col-description").value) || "";
    const p1 = ($("sql-col-price1") && $("sql-col-price1").value) || "";
    const p2 = ($("sql-col-price2") && $("sql-col-price2").value) || "";
    if (!barcode || !desc || !p1) {
      aviso("Informe ao menos código, descrição e preço 1.", true);
      return;
    }
    if ($("c_DB_MODE")) {
      $("c_DB_MODE").value = "EXTERNAL_SQL";
      $("c_DB_MODE").dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (typeof aplicarDependencias === "function") aplicarDependencias();
    if ($("c_DB_PRODUCT_TABLE_NAME")) $("c_DB_PRODUCT_TABLE_NAME").value = _sqlTabelaSel;
    if ($("c_DB_COL_BARCODE")) $("c_DB_COL_BARCODE").value = barcode;
    if ($("c_DB_COL_DESCRIPITION")) $("c_DB_COL_DESCRIPITION").value = desc;
    if ($("c_DB_COL_PRICE1")) $("c_DB_COL_PRICE1").value = p1;
    if ($("c_DB_COL_PRICE2")) $("c_DB_COL_PRICE2").value = p2;
    fecharModalSql();
    aviso("Mapeamento aplicado. Teste a conexão e salve.");
  }

  if ($("modal-sql-aplicar")) {
    $("modal-sql-aplicar").addEventListener("click", aplicarMapeamentoSql);
  }
  if ($("modal-sql-fechar")) $("modal-sql-fechar").addEventListener("click", fecharModalSql);
  if ($("modal-sql-cancelar")) $("modal-sql-cancelar").addEventListener("click", fecharModalSql);
  if ($("modal-sql-fundo")) $("modal-sql-fundo").addEventListener("click", fecharModalSql);

})();

/* Inicialização com o SO */
(function () {
  const el = document.getElementById("autostart-ativo");
  if (!el) return;
  const st = document.getElementById("autostart-status");

  function mostrar(msg, erro) {
    if (st) {
      st.textContent = msg;
      st.style.color = erro ? "var(--alerta, #ff8a80)" : "var(--ok, #6ddea0)";
    }
    if (window.TC && TC.aviso) TC.aviso(msg, !!erro);
  }

  async function aplicar(ativo) {
    if (st) {
      st.textContent = "Aplicando…";
      st.style.color = "var(--texto-2)";
    }
    const r = await fetch("/api/autostart", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ativo: !!ativo }),
      cache: "no-store",
    });
    const corpo = await r.json().catch(() => ({}));
    let detalhe = (typeof corpo.detail === "string")
      ? corpo.detail
      : (corpo.detail ? JSON.stringify(corpo.detail) : "");
    if (!r.ok || corpo.ok === false) {
      throw new Error(detalhe || "Falha ao alterar inicialização");
    }
    const status = corpo.status || {};
    el.checked = !!(status.ativo || corpo.ativo);
    mostrar(el.checked ? "Ativado." : "Desativado.", false);
    return corpo;
  }

  el.addEventListener("change", async () => {
    const desejado = !!el.checked;
    try {
      await aplicar(desejado);
    } catch (e) {
      el.checked = !desejado;
      mostrar(e.message, true);
    }
  });

  const form = document.getElementById("form-config");
  if (form) {
    form.addEventListener("submit", () => {
      // O "Salvar" da config não inclui este interruptor (não tem name).
      // Reaplica o estado visível para o registro não ficar órfão.
      setTimeout(() => {
        aplicar(!!el.checked).catch((e) => mostrar(e.message, true));
      }, 400);
    });
  }
})();




/* Atualização via GitHub (repositório oficial fixo) */
(function () {
  const st = document.getElementById("update-status");
  const ver = document.getElementById("update-versao");
  const btnCheck = document.getElementById("btn-update-check");
  const btnApply = document.getElementById("btn-update-aplicar");
  const logBox = document.getElementById("update-changelog");
  if (!btnCheck) return;

  function setStatus(msg, erro) {
    if (st) {
      st.textContent = msg || "";
      st.style.color = erro ? "var(--alerta, #ff8a80)" : "";
    }
  }

  async function carregarChangelog() {
    if (!logBox) return;
    try {
      const r = await fetch("/api/update/changelog", { cache: "no-store" });
      const corpo = await r.json().catch(() => ({}));
      if (!r.ok || corpo.ok === false) {
        logBox.innerHTML = "<p class=\"meta-img\">" + (corpo.detail || "Changelog indisponível.") + "</p>";
        return;
      }
      logBox.innerHTML = corpo.html || "<p class=\"meta-img\">Changelog vazio.</p>";
    } catch (e) {
      logBox.innerHTML = "<p class=\"meta-img\">Falha ao carregar changelog.</p>";
    }
  }

  btnCheck.addEventListener("click", async () => {
    btnCheck.disabled = true;
    setStatus("Consultando GitHub…");
    try {
      const r = await fetch("/api/update/verificar", { method: "POST", cache: "no-store" });
      const corpo = await r.json().catch(() => ({}));
      if (!r.ok || corpo.ok === false) {
        throw new Error(corpo.detail || "Falha ao verificar");
      }
      let msg = "Remota: " + (corpo.versao_remota || "—");
      if (corpo.atualizacao_disponivel) {
        msg += " · atualização disponível";
        if (btnApply) btnApply.disabled = false;
      } else {
        msg += " · em dia";
        if (btnApply) btnApply.disabled = true;
      }
      setStatus(msg);
      if (window.TC && TC.aviso) TC.aviso(corpo.detail || msg);
    } catch (e) {
      setStatus(e.message, true);
      if (btnApply) btnApply.disabled = true;
      if (window.TC && TC.aviso) TC.aviso(e.message, true);
    } finally {
      btnCheck.disabled = false;
    }
  });

  if (btnApply) {
    btnApply.addEventListener("click", async () => {
      if (!confirm("Baixar e substituir os arquivos do ArautoPY? Será necessário reiniciar depois.")) return;
      btnApply.disabled = true;
      setStatus("Baixando e aplicando…");
      try {
        const r = await fetch("/api/update/aplicar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
          cache: "no-store",
        });
        const corpo = await r.json().catch(() => ({}));
        if (!r.ok || corpo.ok === false) {
          throw new Error(corpo.detail || "Falha ao aplicar");
        }
        setStatus(corpo.detail || "Atualizado. Reinicie o servidor.");
        if (window.TC && TC.aviso) TC.aviso(corpo.detail || "Reinicie o ArautoPY.");
      } catch (e) {
        setStatus(e.message, true);
        if (window.TC && TC.aviso) TC.aviso(e.message, true);
        btnApply.disabled = false;
      }
    });
  }

  fetch("/api/update", { cache: "no-store" })
    .then((r) => r.json())
    .then((s) => {
      if (ver) {
        ver.textContent = s.versao_local || "?";
        if (s.frozen) setStatus("Versão .exe — atualização manual pelo GitHub");
      }
    })
    .catch(() => {});

  carregarChangelog();
})();


