(function () {
  "use strict";
  const { $ } = window.TC;
  const corpo = $("docs-corpo");
  const busca = $("docs-busca");
  const status = $("docs-busca-status");
  if (!corpo || !busca) return;

  const original = corpo.innerHTML;

  function limparMarcas(html) {
    return html.replace(/<mark class="docs-mark">/g, "").replace(/<\/mark>/g, "");
  }

  busca.addEventListener("input", () => {
    const q = (busca.value || "").trim();
    if (!q) {
      corpo.innerHTML = original;
      if (status) status.hidden = true;
      return;
    }
    const texto = corpo.innerText || "";
    const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    let count = 0;
    // Highlight in HTML roughly by walking text — simple approach on textContent rebuild is hard;
    // highlight by replacing in innerHTML carefully for plain text nodes via regex on escaped content
    let html = limparMarcas(original);
    html = html.replace(/>([^<]+)</g, (m, text) => {
      const novo = text.replace(re, (hit) => {
        count += 1;
        return '<mark class="docs-mark">' + hit + '</mark>';
      });
      return '>' + novo + '<';
    });
    corpo.innerHTML = html;
    if (status) {
      status.hidden = false;
      status.textContent = count ? (count + " ocorrência(s)") : "Nada encontrado";
    }
  });
})();


