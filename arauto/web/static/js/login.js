(function () {
  "use strict";
  const { $, json, aviso } = window.TC;
  const form = $("form-login");
  if (!form) return;
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = $("btn-login");
    const err = $("login-erro");
    btn.disabled = true;
    if (err) err.hidden = true;
    try {
      await json("/api/auth/login", {
        method: "POST",
        body: {
          usuario: $("login-usuario").value,
          senha: $("login-senha").value,
        },
      });
      const q = new URLSearchParams(location.search);
      const nxt = q.get("next") || "/painel";
      location.href = nxt.charAt(0) === "/" ? nxt : "/painel";
    } catch (e) {
      if (err) {
        err.hidden = false;
        err.textContent = e.message || "Não foi possível entrar.";
        err.style.color = "var(--erro)";
      }
      aviso(e.message || "Falha no login", true);
      btn.disabled = false;
    }
  });
})();
