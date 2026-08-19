/* Tela de logs: busca incremental por id, para não reenviar o que já chegou. */
(function () {
  "use strict";

  const { $, esc, json, aviso, hora } = window.TC;

  const consoleEl = $("log-console");
  let ultimoId = 0;
  let primeiraCarga = true;

  function filtros() {
    const p = new URLSearchParams();
    p.set("desde", String(ultimoId));
    p.set("nivel", $("log-nivel").value);
    if ($("log-origem").value) p.set("origem", $("log-origem").value);
    if ($("log-busca").value.trim()) p.set("busca", $("log-busca").value.trim());
    return p.toString();
  }

  function coladoNoFim() {
    return consoleEl.scrollHeight - consoleEl.scrollTop - consoleEl.clientHeight < 60;
  }

  function desenhar(linhas) {
    if (!linhas.length) return;
    const seguir = $("log-auto").checked && coladoNoFim();

    if (primeiraCarga) { consoleEl.innerHTML = ""; primeiraCarga = false; }

    const fragmento = document.createDocumentFragment();
    linhas.forEach((l) => {
      const div = document.createElement("div");
      div.className = `linha-log n-${l.nivel}` + (ultimoId ? " nova" : "");
      div.innerHTML =
        `<span class="ts">${esc(l.ts.slice(11))}</span>` +
        `<span class="nivel">${esc(l.nivel)}</span>` +
        `<span class="origem">${esc(l.origem)}</span>` +
        `<span class="msg">${esc(l.mensagem)}</span>`;
      fragmento.appendChild(div);
      ultimoId = Math.max(ultimoId, l.id);
    });
    consoleEl.appendChild(fragmento);

    // segura o crescimento infinito do DOM numa tela que fica aberta o dia todo
    while (consoleEl.childElementCount > 1500) {
      consoleEl.removeChild(consoleEl.firstElementChild);
    }
    if (seguir) consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  function pintarContadores(resumo) {
    const n = resumo.por_nivel || {};
    $("log-contadores").innerHTML =
      `<span>${resumo.total_em_memoria} de ${resumo.capacidade} em memória</span>` +
      `<span>${n.INFO || 0} informação</span>` +
      `<span class="n-warning">${n.WARNING || 0} aviso</span>` +
      `<span class="n-error">${(n.ERROR || 0) + (n.CRITICAL || 0)} erro</span>`;
  }

  async function carregarOrigens() {
    try {
      const origens = await json("/api/logs/origens");
      const seletor = $("log-origem");
      const atual = seletor.value;
      seletor.innerHTML = '<option value="">Todas</option>' +
        origens.map((o) => `<option value="${esc(o)}">${esc(o)}</option>`).join("");
      seletor.value = atual;
    } catch (e) { /* a lista se preenche na próxima volta */ }
  }

  async function atualizar() {
    try {
      const r = await json("/api/logs?" + filtros());
      desenhar(r.linhas);
      pintarContadores(r.resumo);
    } catch (e) { /* servidor caiu; tenta de novo no próximo ciclo */ }
  }

  function reiniciar() {
    ultimoId = 0;
    primeiraCarga = true;
    consoleEl.innerHTML = '<p class="vazio">Aguardando linhas…</p>';
    atualizar();
  }

  ["log-nivel", "log-origem"].forEach((id) =>
    $(id).addEventListener("change", reiniciar));

  let debounce = null;
  $("log-busca").addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(reiniciar, 320);
  });

  $("log-limpar").addEventListener("click", () => {
    consoleEl.innerHTML = '<p class="vazio">Tela limpa. Novas linhas aparecem aqui.</p>';
    primeiraCarga = true;
    aviso("Tela limpa. O arquivo de log continua intacto.");
  });

  /* ---------------------------------------------------- consultas */
  async function carregarConsultas() {
    try {
      const linhas = await json("/api/consultas?limite=60");
      $("corpo-consultas").innerHTML = linhas.length
        ? linhas.map((c) => `
            <tr class="${c.found ? "" : "falhou"}">
              <td class="hora">${esc(hora(c.ts))}</td>
              <td><span class="pastilha">${esc(c.channel || "—")}</span></td>
              <td class="mono">${esc(c.origin || "—")}</td>
              <td class="codigo">${esc(c.barcode)}</td>
              <td class="produto">${c.found ? esc(c.description) : "não encontrado"}</td>
              <td>${esc(c.price1 || "—")}</td>
              <td class="dir">${Number(c.elapsed_ms).toFixed(1)}</td>
            </tr>`).join("")
        : '<tr><td colspan="7" class="vazio">Nenhuma consulta registrada.</td></tr>';
    } catch (e) { /* silencioso */ }
  }

  carregarOrigens();
  atualizar();
  carregarConsultas();
  setInterval(atualizar, 2000);
  setInterval(carregarConsultas, 8000);
  setInterval(carregarOrigens, 30000);
})();


