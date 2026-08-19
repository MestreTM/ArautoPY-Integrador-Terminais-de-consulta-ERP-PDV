(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);

  function ativar(sub) {
    document.querySelectorAll(".subaba").forEach((b) => {
      const on = b.dataset.sub === sub;
      b.classList.toggle("subaba--ativa", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll("[data-subpainel]").forEach((p) => {
      p.hidden = p.dataset.subpainel !== sub;
    });
    try {
      localStorage.setItem("arauto.diag.sub", sub);
      history.replaceState(null, "", "/diagnostico#" + sub);
    } catch (_) {}
  }

  document.querySelectorAll(".subaba").forEach((b) => {
    b.addEventListener("click", () => ativar(b.dataset.sub));
  });

  const hash = (location.hash || "").replace(/^#/, "");
  let ini = hash === "monitor" || hash === "logs" ? hash : null;
  if (!ini) {
    try { ini = localStorage.getItem("arauto.diag.sub"); } catch (_) {}
  }
  if (ini !== "monitor" && ini !== "logs") ini = "logs";
  ativar(ini);
})();


