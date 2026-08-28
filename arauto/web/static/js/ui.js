/* ArautoPY — comportamento da casca do painel (barra lateral e tema).
   Só interface: não fala com a API nem altera nada do servidor. */
(function () {
  "use strict";

  var raiz = document.documentElement;
  var CHAVE_TEMA = "arauto.tema";
  var CHAVE_BARRA = "arauto.sidebar";

  function guardar(chave, valor) {
    try { localStorage.setItem(chave, valor); } catch (e) {}
  }

  function aplicarTema(tema) {
    raiz.dataset.tema = tema;
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", tema === "claro" ? "#eef0f8" : "#161826");
  }

  function alternarTema() {
    var tema = raiz.dataset.tema === "claro" ? "escuro" : "claro";
    aplicarTema(tema);
    guardar(CHAVE_TEMA, tema);
  }

  function recolherBarra(forcar) {
    var recolhida = typeof forcar === "boolean" ? forcar : !raiz.classList.contains("recolhida");
    raiz.classList.toggle("recolhida", recolhida);
    guardar(CHAVE_BARRA, recolhida ? "1" : "0");
    var btn = document.getElementById("btn-recolher");
    if (btn) btn.title = recolhida ? "Expandir a barra (Ctrl+B)" : "Recolher a barra (Ctrl+B)";
  }

  function abrirGaveta(abrir) {
    var lateral = document.getElementById("lateral");
    var veu = document.getElementById("veu");
    if (!lateral) return;
    lateral.classList.toggle("aberta", abrir);
    if (veu) veu.hidden = !abrir;
  }

  function iniciar() {
    aplicarTema(raiz.dataset.tema === "claro" ? "claro" : "escuro");
    recolherBarra(raiz.classList.contains("recolhida"));

    var btnTema = document.getElementById("btn-tema");
    if (btnTema) btnTema.addEventListener("click", alternarTema);

    var btnRecolher = document.getElementById("btn-recolher");
    if (btnRecolher) btnRecolher.addEventListener("click", function () { recolherBarra(); });

    var btnMenu = document.getElementById("btn-menu");
    if (btnMenu) btnMenu.addEventListener("click", function () { abrirGaveta(true); });

    var veu = document.getElementById("veu");
    if (veu) veu.addEventListener("click", function () { abrirGaveta(false); });

    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && (e.key === "b" || e.key === "B")) {
        e.preventDefault();
        recolherBarra();
      }
      if (e.key === "Escape") abrirGaveta(false);
    });

    /* na navegação por link em telas estreitas, fecha a gaveta */
    var lateral = document.getElementById("lateral");
    if (lateral) {
      lateral.addEventListener("click", function (e) {
        if (e.target.closest("a") && window.matchMedia("(max-width: 860px)").matches) abrirGaveta(false);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
