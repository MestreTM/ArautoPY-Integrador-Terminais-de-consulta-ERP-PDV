/* Painel do operador — leitura periódica do estado do servidor. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const json = (url) => fetch(url, { cache: "no-store" }).then((r) => r.json());

  const hora = (iso) => {
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleTimeString("pt-BR", { hour12: false });
  };

  const desdeAgora = (epoch) => {
    const s = Math.max(0, Math.round(Date.now() / 1000 - epoch));
    if (s < 60) return s + "s";
    if (s < 3600) return Math.round(s / 60) + " min";
    return Math.round(s / 3600) + " h";
  };

  /* --------------------------------------------------------------- base */
  async function carregarStatus() {
    const s = await json("/api/status");
    const b = s.base || {};

    const itens = [
      ["Modo", b.modo || "—"],
      ["Produtos", (b.produtos ?? 0).toLocaleString("pt-BR")],
      ["Escrita", b.somente_leitura ? "somente leitura" : "habilitada"],
    ];
    if (b.arquivo) itens.push(["Arquivo", b.arquivo]);
    if (b.tabela) itens.push(["Tabela", b.tabela]);
    if (b.ultima_carga) itens.push(["Última carga", "há " + desdeAgora(b.ultima_carga)]);
    if (b.erro) itens.push(["Erro", b.erro]);
    itens.push(["Servidor ativo há", desdeAgora(s.iniciado_em)]);

    $("dados-base").innerHTML = itens
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");

    const term = s.terminais || [];
    $("lista-terminais").innerHTML = term.length
      ? term.map((t) => `
          <li>
            <span><span class="pastilha">${esc(t.modelo)}</span>
            <span class="mono">${esc(t.endereco)}</span></span>
            <span class="contador">${t.consultas} consultas</span>
          </li>`).join("")
      : '<li class="vazio">Nenhum terminal conectado.</li>';
  }

  /* -------------------------------------------------------- estatísticas */
  async function carregarEstatisticas() {
    const e = await json("/api/estatisticas?dias=7");
    $("n-total").textContent = (e.total || 0).toLocaleString("pt-BR");
    $("n-acerto").textContent = (e.taxa_acerto || 0).toFixed(1).replace(".", ",") + "%";
    $("n-tempo").textContent = (e.tempo_medio_ms || 0).toFixed(1).replace(".", ",") + " ms";

    const faltantes = e.nao_encontrados_top || [];
    $("lista-faltantes").innerHTML = faltantes.length
      ? faltantes.map((f) => `
          <li>
            <span class="mono">${esc(f.barcode)}</span>
            <span class="contador">${f.n}×</span>
          </li>`).join("")
      : '<li class="vazio">Nada por enquanto.</li>';
  }

  /* ------------------------------------------------------------ recentes */
  async function carregarConsultas() {
    const linhas = await json("/api/consultas?limite=40");
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
  }

  /* ------------------------------------------------------ consulta rápida */
  async function consultar() {
    const codigo = $("entrada-codigo").value.trim();
    const caixa = $("resultado");
    if (!codigo) return;

    try {
      const resp = await fetch("/consulta/" + encodeURIComponent(codigo), { cache: "no-store" });
      const d = await resp.json();
      caixa.hidden = false;
      caixa.className = "resultado " + (d.encontrado ? "ok" : "erro");

      if (!d.encontrado) {
        caixa.innerHTML = `<h3>${esc(d.mensagem || "Produto não encontrado")}</h3>
          <p class="meta">${esc(d.codigo_barras)} · ${d.tempo_ms} ms</p>`;
      } else {
        const peso = d.consulta_por_peso
          ? `<p class="meta">por peso: ${d.consulta_por_peso.peso} kg × ${esc(d.consulta_por_peso.preco1_unitario)} — código base ${esc(d.consulta_por_peso.codigo_base)}</p>`
          : "";
        const p2 = d.preco2 ? `<p class="meta">${esc(d.rotulo2)}: ${esc(d.preco2)}</p>` : "";
        caixa.innerHTML = `<h3>${esc(d.descricao)}</h3>
          <p class="meta">${esc(d.codigo_barras)} · ${d.tempo_ms} ms</p>
          <p class="preco">${esc(d.preco1 || "—")}</p>${p2}${peso}`;
      }
      carregarConsultas();
    } catch (e) {
      caixa.hidden = false;
      caixa.className = "resultado erro";
      caixa.innerHTML = "<h3>Sem conexão com o servidor</h3>";
    }
  }

  $("btn-consultar").addEventListener("click", consultar);
  $("entrada-codigo").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") consultar();
  });

  function atualizar() {
    carregarStatus().catch(() => {});
    carregarEstatisticas().catch(() => {});
    carregarConsultas().catch(() => {});
  }

  atualizar();
  setInterval(atualizar, 8000);
})();


