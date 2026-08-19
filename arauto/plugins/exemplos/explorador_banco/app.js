/* Explorador de banco — plugin ArautoPY */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const aviso = (msg, erro) => {
    if (window.TC && TC.aviso) TC.aviso(msg, !!erro);
    else if (erro) console.error(msg);
    else console.log(msg);
  };

  async function api(path, body) {
    const r = await fetch("/plugins/explorador-banco/api/" + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
      cache: "no-store",
    });
    const corpo = await r.json().catch(() => ({}));
    if (!r.ok || corpo.ok === false) {
      throw new Error(corpo.detail || corpo.erro || "HTTP " + r.status);
    }
    return corpo;
  }

  async function apiGet(path) {
    const r = await fetch("/plugins/explorador-banco/api/" + path, { cache: "no-store" });
    return r.json();
  }

  let estado = {
    url: "",
    tabela: "",
    pk: [],
    colunas: [],
    offset: 0,
    limit: 50,
    total: 0,
    filtroCol: "",
    filtroVal: "",
    pendenteDel: null,
    pendenteEdit: null,
  };

  function urlAtual() {
    return ($("exb-url").value || "").trim();
  }

  function setStatus(txt) {
    const el = $("exb-status");
    if (el) el.textContent = txt;
  }

  async function carregarStatus() {
    try {
      const st = await apiGet("status");
      if (st.tem_url) {
        setStatus("Configuração: " + (st.modo || "?") + " · " + (st.url_mascara || "URL definida"));
      } else {
        setStatus("Nenhuma DB_URL na configuração — informe uma URL abaixo.");
      }
    } catch (e) {
      setStatus(e.message);
    }
  }

  async function listarTabelas() {
    const lista = $("exb-lista-tabelas");
    lista.innerHTML = '<p class="exb-vazio" style="padding:.7rem">Carregando…</p>';
    try {
      const r = await api("tabelas", { url: urlAtual() });
      const tabs = r.tabelas || [];
      if (!tabs.length) {
        lista.innerHTML = '<p class="exb-vazio" style="padding:.7rem">Nenhuma tabela encontrada.</p>';
        return;
      }
      lista.innerHTML = "";
      tabs.forEach((nome) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = nome;
        b.dataset.tabela = nome;
        if (nome === estado.tabela) b.classList.add("ativa");
        b.addEventListener("click", () => abrirTabela(nome));
        lista.appendChild(b);
      });
      setStatus(tabs.length + " tabela(s)");
      aviso(tabs.length + " tabela(s) listada(s)");
    } catch (e) {
      lista.innerHTML = '<p class="exb-vazio" style="padding:.7rem">' + esc(e.message) + "</p>";
      aviso(e.message, true);
    }
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function abrirTabela(nome) {
    estado.tabela = nome;
    estado.offset = 0;
    estado.filtroCol = "";
    estado.filtroVal = "";
    document.querySelectorAll("#exb-lista-tabelas button").forEach((b) => {
      b.classList.toggle("ativa", b.dataset.tabela === nome);
    });
    const painel = $("exb-painel");
    painel.innerHTML = '<p class="exb-vazio">Carregando ' + esc(nome) + "…</p>";
    try {
      const info = await api("info", { url: urlAtual(), tabela: nome });
      estado.pk = info.pk || [];
      estado.colunas = (info.colunas || []).map((c) => c.nome || c);
      estado.total = info.total || 0;
      await carregarLinhas();
    } catch (e) {
      painel.innerHTML = '<p class="exb-vazio">' + esc(e.message) + "</p>";
      aviso(e.message, true);
    }
  }

  async function carregarLinhas() {
    const painel = $("exb-painel");
    try {
      const r = await api("linhas", {
        url: urlAtual(),
        tabela: estado.tabela,
        limit: estado.limit,
        offset: estado.offset,
        filtro_col: estado.filtroCol,
        filtro_val: estado.filtroVal,
      });
      estado.total = r.total || 0;
      const cols = r.colunas || [];
      const linhas = r.linhas || [];

      let html = '<div class="exb-meta">';
      html += "<strong>" + esc(estado.tabela) + "</strong>";
      html += "<span>PK: " + (estado.pk.length ? estado.pk.map(esc).join(", ") : "—") + "</span>";
      html += "<span>" + estado.total + " registro(s)</span>";
      html += "</div>";

      html += '<div class="exb-filtro">';
      html += '<select id="exb-filtro-col"><option value="">Filtrar coluna…</option>';
      cols.forEach((c) => {
        html +=
          '<option value="' +
          esc(c) +
          '"' +
          (c === estado.filtroCol ? " selected" : "") +
          ">" +
          esc(c) +
          "</option>";
      });
      html += "</select>";
      html +=
        '<input type="text" id="exb-filtro-val" placeholder="Contém…" value="' +
        esc(estado.filtroVal) +
        '">';
      html += '<button type="button" class="botao" id="exb-filtro-ok">Filtrar</button>';
      html += '<button type="button" class="botao botao--fantasma" id="exb-filtro-limpar">Limpar</button>';
      html += "</div>";

      if (!linhas.length) {
        html += '<p class="exb-vazio">Nenhum registro neste intervalo.</p>';
      } else {
        html += '<div class="exb-wrap"><table class="exb-table"><thead><tr>';
        cols.forEach((c) => {
          html += "<th>" + esc(c) + "</th>";
        });
        html += "<th>Ações</th></tr></thead><tbody>";
        linhas.forEach((row, idx) => {
          html += "<tr data-idx='" + idx + "'>";
          cols.forEach((c) => {
            const v = row[c];
            html += '<td title="' + esc(v) + '">' + esc(v) + "</td>";
          });
          html += '<td class="exb-acoes">';
          html +=
            '<button type="button" class="botao botao--fantasma exb-btn-edit" data-idx="' +
            idx +
            '">Editar</button>';
          html +=
            '<button type="button" class="botao exb-btn-del" data-idx="' +
            idx +
            '" style="color:#ffb4b4">Excluir</button>';
          html += "</td></tr>";
        });
        html += "</tbody></table></div>";
      }

      const de = estado.offset + 1;
      const ate = estado.offset + linhas.length;
      html += '<div class="exb-pag">';
      html +=
        '<button type="button" class="botao botao--fantasma" id="exb-prev"' +
        (estado.offset <= 0 ? " disabled" : "") +
        ">Anterior</button>";
      html +=
        "<span>" +
        (linhas.length ? de + "–" + ate : "0") +
        " de " +
        estado.total +
        "</span>";
      html +=
        '<button type="button" class="botao botao--fantasma" id="exb-next"' +
        (estado.offset + estado.limit >= estado.total ? " disabled" : "") +
        ">Próxima</button>";
      html += "</div>";

      painel.innerHTML = html;
      painel._linhas = linhas;
      painel._cols = cols;

      $("exb-filtro-ok").addEventListener("click", () => {
        estado.filtroCol = $("exb-filtro-col").value;
        estado.filtroVal = $("exb-filtro-val").value;
        estado.offset = 0;
        carregarLinhas();
      });
      $("exb-filtro-limpar").addEventListener("click", () => {
        estado.filtroCol = "";
        estado.filtroVal = "";
        estado.offset = 0;
        carregarLinhas();
      });
      $("exb-prev").addEventListener("click", () => {
        estado.offset = Math.max(0, estado.offset - estado.limit);
        carregarLinhas();
      });
      $("exb-next").addEventListener("click", () => {
        estado.offset += estado.limit;
        carregarLinhas();
      });
      painel.querySelectorAll(".exb-btn-edit").forEach((b) => {
        b.addEventListener("click", () => abrirEditar(linhas[Number(b.dataset.idx)]));
      });
      painel.querySelectorAll(".exb-btn-del").forEach((b) => {
        b.addEventListener("click", () => abrirExcluir1(linhas[Number(b.dataset.idx)]));
      });
    } catch (e) {
      painel.innerHTML = '<p class="exb-vazio">' + esc(e.message) + "</p>";
      aviso(e.message, true);
    }
  }

  function pkDeLinha(row) {
    const pk = {};
    (estado.pk || []).forEach((c) => {
      pk[c] = row[c];
    });
    return pk;
  }

  function abrirEditar(row) {
    if (!estado.pk.length) {
      aviso("Tabela sem chave primária — edição bloqueada.", true);
      return;
    }
    estado.pendenteEdit = row;
    const box = $("exb-edit-campos");
    box.innerHTML = "";
    Object.keys(row).forEach((c) => {
      const isPk = estado.pk.indexOf(c) >= 0;
      const div = document.createElement("div");
      div.className = "campo";
      div.innerHTML =
        "<label>" +
        esc(c) +
        (isPk ? " (PK)" : "") +
        "</label>" +
        '<input type="text" data-col="' +
        esc(c) +
        '" value="' +
        esc(row[c]) +
        '"' +
        (isPk ? " readonly" : "") +
        ">";
      box.appendChild(div);
    });
    $("exb-modal-edit").hidden = false;
  }

  function fecharEdit() {
    $("exb-modal-edit").hidden = true;
    estado.pendenteEdit = null;
  }

  async function salvarEdit() {
    if (!estado.pendenteEdit) return;
    const dados = {};
    $("exb-edit-campos").querySelectorAll("input[data-col]").forEach((inp) => {
      const c = inp.dataset.col;
      if (estado.pk.indexOf(c) >= 0) return;
      dados[c] = inp.value;
    });
    try {
      const r = await api("atualizar", {
        url: urlAtual(),
        tabela: estado.tabela,
        pk: pkDeLinha(estado.pendenteEdit),
        dados,
        confirmar: true,
      });
      aviso(r.detail || "Atualizado.");
      fecharEdit();
      carregarLinhas();
    } catch (e) {
      aviso(e.message, true);
    }
  }

  function abrirExcluir1(row) {
    if (!estado.pk.length) {
      aviso("Tabela sem chave primária — exclusão bloqueada.", true);
      return;
    }
    estado.pendenteDel = row;
    const partes = (estado.pk || []).map((c) => c + "=" + row[c]);
    $("exb-del-resumo").textContent =
      estado.tabela + " · " + (partes.join(", ") || "(sem PK)");
    $("exb-modal-del1").hidden = false;
  }

  function fecharDel() {
    $("exb-modal-del1").hidden = true;
    $("exb-modal-del2").hidden = true;
    estado.pendenteDel = null;
    if ($("exb-del-token")) $("exb-del-token").value = "";
  }

  function abrirExcluir2() {
    $("exb-modal-del1").hidden = true;
    $("exb-modal-del2").hidden = false;
    $("exb-del-token").value = "";
    $("exb-del-token").focus();
  }

  async function confirmarExcluir() {
    if (!estado.pendenteDel) return;
    const token = ($("exb-del-token").value || "").trim();
    try {
      const r = await api("excluir", {
        url: urlAtual(),
        tabela: estado.tabela,
        pk: pkDeLinha(estado.pendenteDel),
        confirmar: true,
        confirmacao: token,
      });
      aviso(r.detail || "Excluído.");
      fecharDel();
      carregarLinhas();
    } catch (e) {
      aviso(e.message, true);
    }
  }

  $("exb-conectar").addEventListener("click", listarTabelas);
  $("exb-edit-cancelar").addEventListener("click", fecharEdit);
  $("exb-edit-salvar").addEventListener("click", salvarEdit);
  $("exb-del1-cancelar").addEventListener("click", fecharDel);
  $("exb-del1-seguir").addEventListener("click", abrirExcluir2);
  $("exb-del2-cancelar").addEventListener("click", fecharDel);
  $("exb-del2-confirmar").addEventListener("click", confirmarExcluir);

  // Ao abrir: status + lista automática se houver DB_URL configurada
  (async function init() {
    try {
      const st = await apiGet("status");
      if (st.tem_url) {
        setStatus("Configuração: " + (st.modo || "?") + " · " + (st.url_mascara || "URL definida") + " — carregando tabelas…");
        await listarTabelas();
      } else {
        setStatus("Nenhuma DB_URL na configuração — informe uma URL e clique em Listar tabelas.");
      }
    } catch (e) {
      setStatus(e.message || String(e));
    }
  })();
})();


