/* Painel do operador — layout alinhado ao redesign (KPIs, consulta, terminais, faltantes). */
(function () {
  "use strict";
  const { $, esc, json, aviso } = window.TC;

  let faltantesCache = [];

  function fmtNum(n) {
    if (n == null || n === "") return "—";
    return Number(n).toLocaleString("pt-BR");
  }

  function fmtPct(n) {
    if (n == null) return "—";
    return Number(n).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
  }

  function fmtMs(ms) {
    if (ms == null || ms === "") return "—";
    return Math.round(Number(ms)) + " ms";
  }

  function fmtHora(ts) {
    if (!ts) return "—";
    const s = String(ts);
    // ISO: 2026-08-25T14:30:00 → 14:30:00
    if (s.indexOf("T") > 0) return s.split("T")[1].slice(0, 8);
    if (s.length >= 19) return s.slice(11, 19);
    return s;
  }

  function fmtUptime(seg) {
    seg = Math.max(0, Math.floor(Number(seg) || 0));
    const h = Math.floor(seg / 3600);
    const m = Math.floor((seg % 3600) / 60);
    if (h >= 24) {
      const d = Math.floor(h / 24);
      return d + " d " + (h % 24) + " h";
    }
    if (h > 0) return h + " h " + m + " min";
    return m + " min";
  }

  function fmtRelativo(ts) {
    if (!ts) return "";
    let t;
    if (typeof ts === "number") t = ts * (ts < 1e12 ? 1000 : 1);
    else t = Date.parse(ts);
    if (!Number.isFinite(t)) return String(ts);
    const diff = Math.max(0, Date.now() - t);
    const s = Math.floor(diff / 1000);
    if (s < 60) return "agora";
    if (s < 3600) return Math.floor(s / 60) + " min";
    if (s < 86400) return Math.floor(s / 3600) + " h";
    return Math.floor(s / 86400) + " d";
  }

  /* —— KPIs ——————————————————————————————————————————— */
  async function carregarKpis() {
    try {
      const [st, stats] = await Promise.all([
        json("/api/status"),
        json("/api/estatisticas?dias=1"),
      ]);

      const base = st.base || {};
      const produtos = base.produtos != null ? base.produtos : "—";
      const modo = base.modo || "";
      const intervalo = base.intervalo_recarga_s;
      const ultima = base.ultima_carga;

      $("kpi-consultas").textContent = fmtNum(stats.total);
      const notaC = $("kpi-consultas-nota");
      notaC.textContent = (stats.encontrados != null)
        ? fmtNum(stats.encontrados) + " encontradas"
        : "nas últimas 24 h";
      notaC.className = "kpi-nota";

      $("kpi-acerto").textContent = fmtPct(stats.taxa_acerto);
      const miss = stats.nao_encontrados || 0;
      const notaA = $("kpi-acerto-nota");
      notaA.textContent = miss
        ? fmtNum(miss) + " código" + (miss === 1 ? "" : "s") + " sem cadastro"
        : "sem falhas no período";
      notaA.className = "kpi-nota";

      $("kpi-tempo").textContent = fmtMs(stats.tempo_medio_ms);
      const notaT = $("kpi-tempo-nota");
      notaT.textContent = modo ? ("base " + modo) : "tempo de resposta";
      notaT.className = "kpi-nota";

      $("kpi-produtos").textContent = fmtNum(produtos);
      const notaP = $("kpi-produtos-nota");
      if (ultima) {
        const ago = fmtRelativo(ultima);
        notaP.textContent = ago === "agora" ? "recarregada agora" : ("recarregada há " + ago);
      } else if (intervalo) {
        notaP.textContent = "recarga a cada " + Math.round(intervalo / 60) + " min";
      } else {
        notaP.textContent = "produtos indexados";
      }
      notaP.className = "kpi-nota";

      // faltantes
      faltantesCache = stats.nao_encontrados_top || [];
      renderFaltantes(faltantesCache);

      // terminais
      renderTerminais(st.terminais || []);
    } catch (e) {
      /* silencioso no ciclo; primeiro load mostra aviso */
    }
  }

  function renderTerminais(lista) {
    const box = $("lista-terminais");
    if (!box) return;
    if (!lista.length) {
      box.innerHTML = '<p class="vazio">Nenhum terminal conectado.</p>';
      return;
    }
    box.innerHTML = lista.map((t) => {
      const modelo = t.modelo || t.nome_aparelho || "Terminal";
      const ip = t.endereco || t.ip || "—";
      const proto = t.tipo != null
        ? (t.tipo === 501 ? "SC501" : t.tipo >= 600 ? "G-BOT" : "SC504")
        : (t.protocolo || "");
      const visto = t.visto_em || t.last_seen;
      const idade = visto ? (Date.now() / 1000 - (typeof visto === "number" ? visto : Date.parse(visto) / 1000)) : 9999;
      let dot = "terminal-dot";
      let estado = "online";
      if (idade > 300) { dot += " terminal-dot--off"; estado = "sem keep-alive"; }
      else if (idade > 120) { dot += " terminal-dot--warn"; estado = "há " + Math.round(idade / 60) + " min"; }
      else estado = "online " + fmtUptime(idade > 0 && t.conectado_em
        ? (Date.now() / 1000 - (typeof t.conectado_em === "number" ? t.conectado_em : Date.now() / 1000))
        : idade);

      // estado legível: tempo desde conexão
      if (t.conectado_em) {
        const up = Date.now() / 1000 - (typeof t.conectado_em === "number" ? t.conectado_em : Date.parse(t.conectado_em) / 1000);
        if (idade <= 120) estado = "online " + fmtUptime(up);
      }

      return (
        `<div class="terminal-item">` +
        `<i class="${dot}" aria-hidden="true"></i>` +
        `<span class="terminal-info">` +
        `<b>${esc(modelo)}</b>` +
        `<span>${esc(ip)}${proto ? " · " + esc(proto) : ""}</span>` +
        `</span>` +
        `<span class="terminal-estado">${esc(estado)}</span>` +
        `</div>`
      );
    }).join("");
  }

  function renderFaltantes(lista) {
    const box = $("lista-faltantes");
    if (!box) return;
    if (!lista.length) {
      box.innerHTML = '<p class="vazio">Nada por enquanto.</p>';
      return;
    }
    box.innerHTML = lista.map((f) => {
      const codigo = f.barcode || f.codigo || f.code || "?";
      const vezes = f.n != null ? f.n + "×" : (f.vezes != null ? f.vezes + "×" : "");
      const quando = fmtRelativo(f.ultima || f.quando || f.ts);
      return (
        `<div class="faltante-item">` +
        `<span class="mono">${esc(codigo)}</span>` +
        `<span class="faltante-vezes">${esc(vezes)}</span>` +
        `<span class="faltante-quando">${esc(quando)}</span>` +
        `</div>`
      );
    }).join("");
  }

  /* —— consultas recentes ———————————————————————————— */
  async function carregarConsultas() {
    const corpo = $("corpo-consultas");
    if (!corpo) return;
    try {
      const itens = await json("/api/consultas?limite=8");
      const lista = Array.isArray(itens) ? itens : (itens.itens || []);
      if (!lista.length) {
        corpo.innerHTML = '<tr><td colspan="6" class="vazio">Nenhuma consulta ainda.</td></tr>';
        return;
      }
      corpo.innerHTML = lista.slice(0, 8).map((c) => {
        const hora = fmtHora(c.ts || c.hora || c.quando);
        const canal = c.channel || c.canal || "—";
        const codigo = c.barcode || c.codigo || "—";
        const prod = c.description || c.descricao || c.produto || (c.found || c.encontrado ? "—" : "não encontrado");
        const preco = c.price1 || c.preco1 || c.preco || "—";
        const ms = c.elapsed_ms != null ? c.elapsed_ms : (c.ms != null ? c.ms : c.tempo_ms);
        return (
          `<tr>` +
          `<td class="mono">${esc(hora)}</td>` +
          `<td><span class="pastilha pastilha-canal pastilha-canal--${esc(String(canal).toLowerCase().replace(/[^a-z0-9]+/g,""))}">${esc(canal)}</span></td>` +
          `<td class="mono">${esc(codigo)}</td>` +
          `<td>${esc(prod)}</td>` +
          `<td>${esc(preco)}</td>` +
          `<td class="dir mono">${esc(ms != null ? Math.round(Number(ms)) : "—")}</td>` +
          `</tr>`
        );
      }).join("");
    } catch (e) {
      corpo.innerHTML = `<tr><td colspan="6" class="vazio">${esc(e.message)}</td></tr>`;
    }
  }

  /* —— consulta rápida ——————————————————————————————— */
  async function consultar() {
    const entrada = $("entrada-codigo");
    const box = $("resultado");
    if (!entrada || !box) return;
    const codigo = (entrada.value || "").trim();
    if (!codigo) {
      aviso("Informe um código.", true);
      return;
    }
    box.hidden = false;
    box.className = "consulta-resultado";
    box.innerHTML = '<p class="meta-img">Consultando…</p>';

    try {
      const r = await json("/consulta/" + encodeURIComponent(codigo));
      const ok = r.encontrado || r.found;
      const cod = r.codigo_barras || r.codigo || codigo;
      const nome = r.descricao || r.nome || r.label || "—";
      const r1 = r.rotulo1 || "Preço";
      const r2 = r.rotulo2 || "";
      const p1 = r.preco1 || r.preco || "";
      const p2 = r.preco2 || "";
      const ms = r.tempo_ms != null ? r.tempo_ms : r.ms;

      if (!ok) {
        box.className = "consulta-resultado consulta-resultado--erro";
        box.innerHTML =
          `<div class="consulta-corpo">` +
          `<span class="pastilha">não encontrado</span>` +
          `<span class="consulta-codigo mono">${esc(cod)}</span>` +
          `<p class="consulta-nome">${esc(r.mensagem || nome || "Código ausente na base")}</p>` +
          `</div>`;
      } else {
        const precos = [];
        if (p1) {
          precos.push(
            `<span class="consulta-preco"><span>${esc(r1)}</span><b>${esc(p1)}</b></span>`
          );
        }
        if (p2) {
          precos.push(
            `<span class="consulta-preco"><span>${esc(r2 || "Preço 2")}</span><b>${esc(p2)}</b></span>`
          );
        }
        const imgUrl = "/api/imagens/" + encodeURIComponent(cod);
        box.innerHTML =
          `<div class="consulta-img" id="consulta-img">` +
          `<img src="${esc(imgUrl)}" alt="" loading="lazy" ` +
          `onerror="this.remove();this.parentElement.classList.add('consulta-img--vazia');` +
          `this.parentElement.innerHTML='Imagem<br>local';">` +
          `</div>` +
          `<div class="consulta-corpo">` +
          `<span class="consulta-codigo mono">${esc(cod)}</span>` +
          `<p class="consulta-nome">${esc(nome)}</p>` +
          (precos.length ? `<div class="consulta-precos">${precos.join("")}</div>` : "") +
          `<span class="consulta-meta">respondido em ${esc(fmtMs(ms))}</span>` +
          `</div>`;
      }
      carregarConsultas();
      carregarKpis();
    } catch (e) {
      if (e.status === 404 && e.data) {
        const r = e.data;
        const cod = r.codigo_barras || r.codigo || codigo;
        box.className = "consulta-resultado consulta-resultado--erro";
        box.innerHTML =
          `<div class="consulta-corpo">` +
          `<span class="pastilha">não encontrado</span>` +
          `<span class="consulta-codigo mono">${esc(cod)}</span>` +
          `<p class="consulta-nome">${esc(r.mensagem || r.descricao || "Código ausente na base")}</p>` +
          `</div>`;
      } else {
        box.className = "consulta-resultado consulta-resultado--erro";
        box.innerHTML = `<p class="meta-img" style="color:var(--erro)">${esc(e.message)}</p>`;
      }
    }
  }

  async function recarregarBase() {
    const btn = $("btn-recarregar-base");
    if (btn) btn.disabled = true;
    try {
      const r = await json("/api/recarregar", { method: "POST" });
      const n = r.produtos != null ? r.produtos : (r.base && r.base.produtos);
      aviso(n != null ? ("Base recarregada: " + fmtNum(n) + " produto(s).") : (r.detail || "Base recarregada."));
      carregarKpis();
    } catch (e) {
      aviso("Falha ao recarregar: " + e.message, true);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function exportarFaltantes() {
    if (!faltantesCache.length) {
      aviso("Não há códigos faltantes para exportar.", true);
      return;
    }
    const linhas = ["codigo;vezes;ultima"];
    faltantesCache.forEach((f) => {
      linhas.push([
        f.barcode || f.codigo || "",
        f.n != null ? f.n : (f.vezes || ""),
        f.ultima || f.quando || "",
      ].join(";"));
    });
    const blob = new Blob([linhas.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "codigos-nao-encontrados.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  /* —— bind —————————————————————————————————————————— */
  const btn = $("btn-consultar");
  const entrada = $("entrada-codigo");
  if (btn) btn.addEventListener("click", consultar);
  if (entrada) {
    entrada.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); consultar(); }
    });
  }
  if ($("btn-recarregar-base")) $("btn-recarregar-base").addEventListener("click", recarregarBase);
  if ($("btn-exportar-faltantes")) $("btn-exportar-faltantes").addEventListener("click", exportarFaltantes);

  carregarKpis();
  carregarConsultas();
  setInterval(carregarKpis, 15000);
  setInterval(carregarConsultas, 5000);
})();
