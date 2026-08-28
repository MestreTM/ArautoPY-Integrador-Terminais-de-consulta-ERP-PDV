/* Tela de logs (e bloco de logs dentro de Diagnóstico). */
(function () {
  "use strict";
  const { $, esc, json, aviso } = window.TC;

  const consoleEl = $("log-console");
  if (!consoleEl) return;

  let ultimoId = 0;
  let primeira = true;

  function filtros() {
    const p = new URLSearchParams({ desde: String(ultimoId) });
    const nivel = $("log-nivel");
    const origem = $("log-origem");
    const busca = $("log-busca");
    if (nivel && nivel.value) p.set("nivel", nivel.value);
    if (origem && origem.value) p.set("origem", origem.value);
    if (busca && busca.value.trim()) p.set("busca", busca.value.trim());
    return p.toString();
  }

  const noFim = () =>
    consoleEl.scrollHeight - consoleEl.scrollTop - consoleEl.clientHeight < 80;

  function classeNivel(n) {
    const u = String(n || "").toUpperCase();
    if (u === "ERROR" || u === "CRITICAL") return "ev-erro";
    if (u === "WARNING" || u === "WARN") return "ev-alerta";
    if (u === "DEBUG") return "ev-debug";
    return "ev-info";
  }

  function desenhar(linhas) {
    if (!linhas || !linhas.length) return;
    const auto = $("log-auto");
    const seguir = (!auto || auto.checked) && noFim();
    if (primeira) {
      consoleEl.innerHTML = "";
      primeira = false;
    }
    const frag = document.createDocumentFragment();
    linhas.forEach((l) => {
      const div = document.createElement("div");
      div.className = "evento " + classeNivel(l.nivel);
      div.innerHTML =
        `<div class="ev-topo">` +
        `<span class="ev-hora mono">${esc(l.hora || l.ts || "")}</span>` +
        `<span class="pastilha pastilha--${esc(String(l.nivel || "info").toLowerCase())}">${esc(l.nivel || "")}</span>` +
        `<span class="ev-peer mono">${esc(l.origem || l.logger || "")}</span>` +
        `</div>` +
        `<pre>${esc(l.mensagem || l.msg || l.texto || "")}</pre>`;
      frag.appendChild(div);
      if (l.id != null) ultimoId = Math.max(ultimoId, Number(l.id) || 0);
    });
    consoleEl.appendChild(frag);
    while (consoleEl.childElementCount > 500) {
      consoleEl.removeChild(consoleEl.firstElementChild);
    }
    if (seguir) consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  function resumo(r) {
    const box = $("log-contadores");
    if (!box || !r) return;
    const partes = [];
    if (r.total != null) partes.push(`<span class="pastilha pastilha--info">${esc(r.total)} linhas</span>`);
    if (r.por_nivel) {
      Object.keys(r.por_nivel).forEach((k) => {
        partes.push(`<span class="pastilha pastilha--${esc(String(k).toLowerCase())}">${esc(k)} ${esc(r.por_nivel[k])}</span>`);
      });
    }
    box.innerHTML = partes.join(" ");
  }

  async function atualizar() {
    try {
      const r = await json("/api/logs?" + filtros());
      desenhar(r.linhas || r.itens || []);
      resumo(r.resumo || r);
    } catch (e) { /* próximo ciclo */ }
  }

  async function carregarOrigens() {
    try {
      const origens = await json("/api/logs/origens");
      const sel = $("log-origem");
      if (!sel) return;
      const atual = sel.value;
      sel.innerHTML =
        '<option value="">Todas</option>' +
        (origens || []).map((o) => `<option value="${esc(o)}">${esc(o)}</option>`).join("");
      sel.value = atual;
    } catch (e) { /* silencioso */ }
  }

  function reiniciar() {
    ultimoId = 0;
    primeira = true;
    consoleEl.innerHTML = '<p class="vazio">Aguardando linhas…</p>';
    atualizar();
  }

  ["log-nivel", "log-origem"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("change", reiniciar);
  });
  const busca = $("log-busca");
  if (busca) {
    let t = null;
    busca.addEventListener("input", () => {
      clearTimeout(t);
      t = setTimeout(reiniciar, 350);
    });
  }
  const limpar = $("log-limpar");
  if (limpar) {
    limpar.addEventListener("click", () => {
      ultimoId = 0;
      primeira = true;
      consoleEl.innerHTML = '<p class="vazio">Tela limpa. Novas linhas aparecerão aqui.</p>';
    });
  }

  /* consultas recentes na mesma página (diagnóstico / logs) */
  let fonteConsultas = "";

  function horaDe(c) {
    const s = String(c.ts || c.hora || c.quando || "");
    if (!s) return "—";
    if (s.indexOf("T") > 0) return s.replace("T", " ").slice(0, 19);
    return s;
  }

  function ehTerminal(c) {
    if (c.fonte === "terminais") return true;
    if (c.fonte === "sistema") return false;
    const ch = String(c.channel || c.canal || "").toLowerCase();
    const orig = String(c.origin || c.origem || c.ip || "");
    return ch.indexOf("terminal") === 0 || /^\d{1,3}(?:\.\d{1,3}){3}/.test(orig);
  }

  function rotuloOrigem(c) {
    if (c.origem) return String(c.origem);
    const orig = String(c.origin || c.ip || "").trim();
    if (orig) return orig;
    return ehTerminal(c) ? "terminal" : "sistema";
  }

  async function carregarConsultas() {
    const corpo = $("corpo-consultas");
    if (!corpo) return;
    try {
      const qs = "/api/consultas?limite=40" + (fonteConsultas ? "&fonte=" + encodeURIComponent(fonteConsultas) : "");
      const itens = await json(qs);
      const lista = Array.isArray(itens) ? itens : (itens.itens || []);
      if (!lista.length) {
        const msg = fonteConsultas === "terminais"
          ? "Nenhuma consulta de terminal."
          : fonteConsultas === "sistema"
            ? "Nenhuma consulta do sistema."
            : "Nenhuma consulta.";
        corpo.innerHTML = '<tr><td colspan="7" class="vazio">' + msg + "</td></tr>";
        return;
      }
      corpo.innerHTML = lista
        .map((c) => {
          const canal = c.channel || c.canal || "—";
          const terminal = ehTerminal(c);
          const origem = rotuloOrigem(c);
          const codigo = c.barcode || c.codigo || "—";
          const achou = c.found === 1 || c.found === true || c.encontrado === true;
          const prod = c.description || c.descricao || c.produto || (achou ? "—" : "não encontrado");
          const preco = c.price1 || c.preco1 || c.preco || "—";
          const ms = c.elapsed_ms != null ? c.elapsed_ms : (c.ms != null ? c.ms : c.tempo_ms);
          const canalCls = "pastilha pastilha-canal pastilha-canal--" + String(canal).toLowerCase().replace(/[^a-z0-9]+/g, "");
          const origCls = terminal ? "pastilha pastilha-canal pastilha-canal--sc501" : "pastilha pastilha--info";
          const stCls = achou ? "pastilha pastilha--ok" : "pastilha pastilha--erro";
          return `<tr class="${achou ? "" : "linha-falha"}">` +
            `<td class="mono">${esc(horaDe(c))}</td>` +
            `<td><span class="${canalCls}">${esc(canal)}</span></td>` +
            `<td><span class="${origCls} mono">${esc(origem)}</span></td>` +
            `<td class="mono">${esc(codigo)}</td>` +
            `<td><span class="${stCls}">${achou ? "ok" : "falha"}</span> ${esc(prod)}</td>` +
            `<td class="mono">${esc(preco)}</td>` +
            `<td class="dir mono">${esc(ms != null ? Math.round(Number(ms)) : "—")}</td>` +
            `</tr>`;
        })
        .join("");
    } catch (e) {
      corpo.innerHTML = `<tr><td colspan="7" class="vazio">${esc(e.message)}</td></tr>`;
    }
  }

  document.querySelectorAll(".filtro-fonte-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      fonteConsultas = btn.dataset.fonte || "";
      document.querySelectorAll(".filtro-fonte-btn").forEach((b) => {
        b.classList.toggle("filtro-fonte-btn--ativo", b === btn);
      });
      carregarConsultas();
    });
  });

  carregarOrigens();
  atualizar();
  carregarConsultas();
  setInterval(atualizar, 2000);
  setInterval(carregarOrigens, 20000);
  setInterval(carregarConsultas, 20000);
})();
