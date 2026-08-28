/* Documentação de plugins — busca no markdown renderizado. */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }

  const campo = $("docs-busca");
  const corpo = $("docs-corpo");
  const status = $("docs-busca-status");
  if (!campo || !corpo) return;

  const n = document.getElementById("tab-n-instalados");
  if (n && window.TC && window.TC.json) {
    window.TC.json("/api/plugins").then((r) => {
      n.textContent = String((r.plugins || []).length);
    }).catch(() => {});
  }

  let htmlOriginal = corpo.innerHTML;

  function contarMarks(root) {
    return root.querySelectorAll("mark").length;
  }

  campo.addEventListener("input", () => {
    const q = (campo.value || "").trim();
    if (!q) {
      corpo.innerHTML = htmlOriginal;
      if (status) status.hidden = true;
      return;
    }
    const tmp = document.createElement("div");
    tmp.innerHTML = htmlOriginal;
    const qLower = q.toLowerCase();
    const walker = document.createTreeWalker(tmp, NodeFilter.SHOW_TEXT, null);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((node) => {
      const t = node.nodeValue;
      if (!t || !t.trim()) return;
      const lower = t.toLowerCase();
      let idx = lower.indexOf(qLower);
      if (idx === -1) return;
      const frag = document.createDocumentFragment();
      let last = 0;
      while (idx !== -1) {
        if (idx > last) frag.appendChild(document.createTextNode(t.slice(last, idx)));
        const mark = document.createElement("mark");
        mark.textContent = t.slice(idx, idx + q.length);
        frag.appendChild(mark);
        last = idx + q.length;
        idx = lower.indexOf(qLower, last);
      }
      if (last < t.length) frag.appendChild(document.createTextNode(t.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
    corpo.innerHTML = tmp.innerHTML;
    if (status) {
      const n = contarMarks(corpo);
      status.hidden = false;
      status.textContent = n ? n + " ocorrência(s)" : "Nada encontrado";
    }
  });
})();
