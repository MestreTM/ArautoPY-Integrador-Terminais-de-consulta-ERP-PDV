/* Terminal de consulta — captura leitor USB/2D e mostra preço. */
(function () {
  "use strict";

  const body = document.body;
  const captura = document.getElementById("captura");
  const resetSeg = Math.max(4, Number(body.dataset.reset || 12));
  const rotulo1 = body.dataset.rotulo1 || "Preço";
  const rotulo2 = body.dataset.rotulo2 || "Oferta";
  const naoEncontrado = body.dataset.naoEncontrado || "Produto não encontrado";

  let buffer = "";
  let lastKey = 0;
  let timerReset = null;
  let online = true;

  function cena(nome) {
    document.querySelectorAll(".cena").forEach((c) => c.classList.remove("cena--ativa"));
    const el = document.getElementById("cena-" + nome);
    if (el) el.classList.add("cena--ativa");
  }

  function reiniciarContagem() {
    const box = document.getElementById("contagem");
    const barra = document.getElementById("contagem-barra");
    if (!box || !barra) return;
    box.hidden = false;
    barra.style.transition = "none";
    barra.style.transform = "scaleX(1)";
    void barra.offsetWidth;
    barra.style.transition = "transform " + resetSeg + "s linear";
    barra.style.transform = "scaleX(0)";
    clearTimeout(timerReset);
    timerReset = setTimeout(function () {
      box.hidden = true;
      cena("ocioso");
      focar();
    }, resetSeg * 1000);
  }

  function focar() {
    try { if (captura) captura.focus({ preventScroll: true }); } catch (e) {
      try { if (captura) captura.focus(); } catch (e2) {}
    }
  }

  function fmtPreco(v) {
    if (v == null || v === "") return "";
    const n = Number(String(v).replace(",", "."));
    if (Number.isFinite(n)) {
      return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    }
    return String(v);
  }

  async function consultar(codigo) {
    codigo = String(codigo || "").replace(/\D+/g, "");
    if (!codigo) return;
    cena("buscando");
    const elCod = document.getElementById("buscando-codigo");
    if (elCod) elCod.textContent = codigo;

    try {
      const res = await fetch("/consulta/" + encodeURIComponent(codigo), {
        headers: { Accept: "application/json" },
      });
      const data = await res.json().catch(function () { return {}; });
      online = true;
      atualizarSinal();

      if (res.ok && (data.found || data.encontrado)) {
        document.getElementById("res-codigo").textContent = data.codigo || data.barcode || codigo;
        document.getElementById("res-descricao").textContent =
          data.descricao || data.nome || data.label || "";
        document.getElementById("res-rotulo1").textContent = data.rotulo1 || rotulo1;
        document.getElementById("res-preco1").textContent =
          fmtPreco(data.preco != null ? data.preco : (data.preco1 != null ? data.preco1 : data.price));
        const peso = document.getElementById("res-peso");
        if (peso) {
          if (data.peso || data.peso_kg) {
            peso.hidden = false;
            peso.textContent = data.peso || (data.peso_kg + " kg");
          } else peso.hidden = true;
        }
        const oferta = document.getElementById("oferta");
        const p2 = data.preco2 != null ? data.preco2 : data.preco_promocional;
        if (oferta) {
          if (p2 != null && p2 !== "") {
            oferta.hidden = false;
            document.getElementById("res-rotulo2").textContent = data.rotulo2 || rotulo2;
            document.getElementById("res-preco2").textContent = fmtPreco(p2);
          } else oferta.hidden = true;
        }
        cena("produto");
      } else {
        document.getElementById("vazio-titulo").textContent =
          data.descricao || data.label || data.nao_encontrado || naoEncontrado;
        document.getElementById("vazio-codigo").textContent = data.codigo || codigo;
        cena("vazio");
      }
      reiniciarContagem();
    } catch (e) {
      online = false;
      atualizarSinal();
      document.getElementById("vazio-titulo").textContent = "Sem conexão com o servidor";
      document.getElementById("vazio-codigo").textContent = codigo;
      cena("vazio");
      reiniciarContagem();
    }
  }

  function atualizarSinal() {
    const s = document.getElementById("sinal");
    if (!s) return;
    s.classList.toggle("off", !online);
    s.innerHTML = online ? "<i></i>on-line" : "<i></i>off-line";
  }

  document.addEventListener("keydown", function (e) {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") && e.target !== captura) {
      return;
    }
    const now = Date.now();
    if (now - lastKey > 120) buffer = "";
    lastKey = now;

    if (e.key === "Enter") {
      e.preventDefault();
      const codigo = buffer || (captura && captura.value) || "";
      buffer = "";
      if (captura) captura.value = "";
      consultar(codigo);
      return;
    }
    if (e.key.length === 1 && /[0-9A-Za-z]/.test(e.key)) {
      buffer += e.key;
    }
  });

  const btnTela = document.getElementById("btn-tela");
  if (btnTela) {
    btnTela.addEventListener("click", function () {
      const el = document.documentElement;
      if (!document.fullscreenElement) {
        if (el.requestFullscreen) el.requestFullscreen();
      } else if (document.exitFullscreen) {
        document.exitFullscreen();
      }
    });
  }

  async function ping() {
    try {
      const r = await fetch("/api/status", { headers: { Accept: "application/json" } });
      online = r.ok;
    } catch (e) {
      online = false;
    }
    atualizarSinal();
  }

  document.addEventListener("click", focar);
  focar();
  cena("ocioso");
  ping();
  setInterval(ping, 12000);
  setInterval(focar, 3000);
})();
