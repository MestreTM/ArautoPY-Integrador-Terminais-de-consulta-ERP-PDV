/* Monitor de tráfego: leitura incremental por id, como a tela de logs. */
(function () {
  "use strict";

  const { $, esc, json, aviso } = window.TC;
  const consoleEl = $("mon-console");
  let ultimoId = 0;
  let primeira = true;

  const LARGURA = 16;

  function hexdump(hex, ascii) {
    const bytes = hex.match(/../g) || [];
    const linhas = [];
    for (let pos = 0; pos < bytes.length; pos += LARGURA) {
      const pedaco = bytes.slice(pos, pos + LARGURA);
      const hexa = pedaco.join(" ").padEnd(LARGURA * 3 - 1, " ");
      const txt = ascii.slice(pos, pos + LARGURA);
      linhas.push(`${pos.toString(16).padStart(4, "0")}  ${hexa}  |${txt}|`);
    }
    return linhas.join("\n");
  }

  function filtros() {
    const p = new URLSearchParams({ desde: String(ultimoId) });
    if ($("mon-proto").value) p.set("protocolo", $("mon-proto").value);
    if ($("mon-peer").value) p.set("peer", $("mon-peer").value);
    return p.toString();
  }

  const noFim = () =>
    consoleEl.scrollHeight - consoleEl.scrollTop - consoleEl.clientHeight < 60;

  function desenhar(eventos) {
    if (!eventos.length) return;
    const seguir = $("mon-auto").checked && noFim();
    if (primeira) { consoleEl.innerHTML = ""; primeira = false; }
    const soAscii = $("mon-ascii").checked;

    const frag = document.createDocumentFragment();
    eventos.forEach((e) => {
      const div = document.createElement("div");
      div.className = `evento ev-${e.direcao}`;
      const seta = { recebido: "◀", enviado: "▶", nota: "•" }[e.direcao] || "•";
      const corpo = e.bytes
        ? `<pre>${esc(soAscii ? e.ascii : hexdump(e.hex, e.ascii))}</pre>`
        : "";
      div.innerHTML =
        `<div class="ev-topo">` +
        `<span class="ev-seta">${seta}</span>` +
        `<span class="ev-hora">${esc(e.hora)}</span>` +
        `<span class="pastilha">${esc(e.protocolo)}</span>` +
        `<span class="ev-peer">${esc(e.peer)}</span>` +
        (e.bytes ? `<span class="ev-tam">${e.bytes} bytes</span>` : "") +
        (e.nota ? `<span class="ev-nota">${esc(e.nota)}</span>` : "") +
        `</div>${corpo}`;
      frag.appendChild(div);
      ultimoId = Math.max(ultimoId, e.id);
    });
    consoleEl.appendChild(frag);
    while (consoleEl.childElementCount > 400) {
      consoleEl.removeChild(consoleEl.firstElementChild);
    }
    if (seguir) consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  function contadores(r) {
    $("mon-contadores").innerHTML =
      `<span>${r.eventos} de ${r.capacidade} eventos</span>` +
      `<span>${r.recebidos} recebidos</span>` +
      `<span>${r.enviados} enviados</span>` +
      `<span>${r.bytes_recebidos} bytes do terminal</span>` +
      `<span>${r.sessoes} sessão(ões)</span>`;
  }

  async function atualizar() {
    try {
      const r = await json("/api/monitor?" + filtros());
      desenhar(r.eventos);
      contadores(r.resumo);
    } catch (e) { /* tenta de novo no próximo ciclo */ }
  }

  async function carregarPeers() {
    try {
      const peers = await json("/api/monitor/peers");
      const sel = $("mon-peer");
      const atual = sel.value;
      sel.innerHTML = '<option value="">Todos</option>' +
        peers.map((p) => `<option value="${esc(p)}">${esc(p)}</option>`).join("");
      sel.value = atual;
    } catch (e) { /* silencioso */ }
  }

  function reiniciar() {
    ultimoId = 0; primeira = true;
    consoleEl.innerHTML = '<p class="vazio">Aguardando tráfego…</p>';
    atualizar();
  }

  ["mon-proto", "mon-peer", "mon-ascii"].forEach((id) =>
    $(id).addEventListener("change", reiniciar));

  $("mon-limpar").addEventListener("click", async () => {
    await json("/api/monitor/limpar", { method: "POST" });
    reiniciar();
    aviso("Monitor limpo.");
  });

  $("mon-analisar").addEventListener("click", async () => {
    const caixa = $("mon-analise");
    caixa.hidden = false;
    caixa.textContent = "analisando…";
    try {
      const p = $("mon-peer").value ? "?peer=" + encodeURIComponent($("mon-peer").value) : "";
      const r = await json("/api/monitor/analise" + p);
      if (!r.bytes) {
        caixa.className = "sim-saida erro";
        caixa.textContent = "Nenhum byte recebido ainda. Conecte o terminal e faça uma consulta.";
        return;
      }
      caixa.className = "sim-saida";
      const linhas = r.hipoteses.map((h) =>
        `${h.completo ? "✓" : " "} ${h.nome.padEnd(10)} ${String(h.pontuacao.toFixed(1)).padStart(5)}%  ` +
        `${String(h.quadros).padStart(3)} quadro(s)  ids: ${h.ids.join(", ") || "—"}`);
      const outras = (r.sessoes || []).filter((s) => s.peer !== r.peer);
      const rodape = outras.length
        ? `\n\nOutras sessões: ${outras.map((s) => s.peer + " (" + s.bytes + "b)").join(", ")}`
        : "";
      caixa.innerHTML = `<pre>${esc(r.bytes)} bytes de ${esc(r.peer)}\n\n` +
        esc(linhas.join("\n")) + `\n\n${esc(r.conclusao)}${esc(rodape)}</pre>`;
    } catch (e) {
      caixa.className = "sim-saida erro";
      caixa.textContent = "Falha: " + e.message;
    }
  });

  $("mon-peer").addEventListener("change", () => {
    const p = $("mon-peer").value;
    $("mon-baixar").href = "/api/monitor/captura" + (p ? "?peer=" + encodeURIComponent(p) : "");
  });

  carregarPeers();
  atualizar();
  setInterval(atualizar, 1500);
  setInterval(carregarPeers, 15000);
})();


