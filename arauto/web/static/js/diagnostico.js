/* Alterna subpainéis Logs / Monitor na página Diagnóstico. */
(function () {
  "use strict";

  function ativar(nome) {
    document.querySelectorAll(".subaba").forEach((btn) => {
      const on = btn.dataset.sub === nome;
      btn.classList.toggle("subaba--ativa", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll("[data-subpainel]").forEach((p) => {
      const on = p.dataset.subpainel === nome;
      p.hidden = !on;
    });
    try {
      if (history.replaceState) {
        history.replaceState(null, "", "#" + nome);
      } else {
        location.hash = nome;
      }
    } catch (e) {}
  }

  document.querySelectorAll(".subaba").forEach((btn) => {
    btn.addEventListener("click", () => ativar(btn.dataset.sub));
  });

  const hash = (location.hash || "").replace(/^#/, "");
  if (hash === "monitor" || hash === "logs") ativar(hash);
})();
