/* ==========================================================================
   ArautoPY — Terminal de consulta
   Fluxo: ocioso -> buscando -> produto | não encontrado -> ocioso.
   Entrada apenas pelo leitor 2D/USB (modo teclado + Enter).
   ========================================================================== */
(function () {
  "use strict";

  const cfg = document.body.dataset;
  const RESET_MS = (parseInt(cfg.reset, 10) || 12) * 1000;
  const TEMPO_LEITOR_MS = 80;   // intervalo máximo entre teclas de um leitor
  const MIN_DIGITOS = 4;

  const $ = (id) => document.getElementById(id);

  const cenas = {
    ocioso: $("cena-ocioso"),
    buscando: $("cena-buscando"),
    produto: $("cena-produto"),
    vazio: $("cena-vazio"),
  };

  const captura = $("captura");
  const contagem = $("contagem");
  const barra = $("contagem-barra");
  const sinal = $("sinal");

  let digitado = "";
  let ultimaTecla = 0;
  let timerReset = null;
  let cenaAtual = "ocioso";
  let buscando = false;

  function mostrar(nome) {
    Object.entries(cenas).forEach(([chave, el]) => {
      el.classList.toggle("cena--ativa", chave === nome);
    });
    cenaAtual = nome;
  }

  function agendarVolta() {
    cancelarVolta();
    contagem.hidden = false;
    barra.style.transition = "none";
    barra.style.transform = "scaleX(1)";
    void barra.offsetWidth;
    barra.style.transition = `transform ${RESET_MS}ms linear`;
    barra.style.transform = "scaleX(0)";
    timerReset = setTimeout(voltarAoInicio, RESET_MS);
  }

  function cancelarVolta() {
    if (timerReset) clearTimeout(timerReset);
    timerReset = null;
    contagem.hidden = true;
  }

  function voltarAoInicio() {
    cancelarVolta();
    digitado = "";
    mostrar("ocioso");
  }

  let audio = null;
  function bipe(freq, dur) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
      const osc = audio.createOscillator();
      const vol = audio.createGain();
      osc.type = "square";
      osc.frequency.value = freq;
      vol.gain.setValueAtTime(0.05, audio.currentTime);
      vol.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + dur);
      osc.connect(vol).connect(audio.destination);
      osc.start();
      osc.stop(audio.currentTime + dur);
    } catch (e) { /* som é enfeite */ }
  }

  async function consultar(codigo) {
    codigo = (codigo || "").trim();
    if (codigo.length < MIN_DIGITOS || buscando) return;

    buscando = true;
    cancelarVolta();
    $("buscando-codigo").textContent = codigo;
    mostrar("buscando");

    try {
      const resp = await fetch("/consulta/" + encodeURIComponent(codigo), {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      const dados = await resp.json();
      conectado(true);
      dados.encontrado ? pintarProduto(dados) : pintarVazio(dados);
    } catch (erro) {
      conectado(false);
      pintarFalha(codigo);
    } finally {
      buscando = false;
      digitado = "";
      agendarVolta();
    }
  }

  function pintarProduto(d) {
    $("res-codigo").textContent = formatarCodigo(d.codigo_barras);
    $("res-descricao").textContent = d.descricao || "Produto sem descrição";
    $("res-rotulo1").textContent = d.rotulo1 || cfg.rotulo1 || "Preço";
    pintarValor($("res-preco1"), d.preco1);

    const peso = $("res-peso");
    const et = d.etiqueta_balanca || d.consulta_por_peso;
    if (et) {
      const qtd = (v) => Number(v).toLocaleString("pt-BR", {
        minimumFractionDigits: 3, maximumFractionDigits: 3,
      });
      peso.textContent = et.tipo === "total"
        ? `total da etiqueta · ${et.preco1_unitario} por kg`
        : `${qtd(et.peso)} kg × ${et.preco1_unitario} por kg`;
      peso.hidden = false;
    } else {
      peso.hidden = true;
    }

    const oferta = $("oferta");
    if (d.preco2) {
      $("res-rotulo2").textContent = d.rotulo2 || cfg.rotulo2 || "Preço personalizado";
      $("res-preco2").textContent = d.preco2;
      oferta.hidden = false;
    } else {
      oferta.hidden = true;
    }

    mostrar("produto");
    bipe(1320, 0.09);
  }

  function pintarVazio(d) {
    $("vazio-titulo").textContent = (d && d.mensagem) || cfg.naoEncontrado || "Produto não encontrado";
    $("vazio-codigo").textContent = formatarCodigo((d && d.codigo_barras) || "");
    mostrar("vazio");
    bipe(220, 0.22);
  }

  function pintarFalha(codigo) {
    $("vazio-titulo").textContent = "Sem conexão com o servidor";
    $("vazio-codigo").textContent = formatarCodigo(codigo);
    mostrar("vazio");
    bipe(180, 0.3);
  }

  function pintarValor(alvo, texto) {
    alvo.textContent = "";
    if (!texto) { alvo.textContent = "—"; return; }
    const m = String(texto).trim().match(/^([^\d\-]+)?\s*(.+)$/);
    const simbolo = (m && m[1] || "").trim();
    const numero = (m && m[2] || texto).trim();
    if (simbolo) {
      const s = document.createElement("span");
      s.className = "moeda";
      s.textContent = simbolo;
      alvo.appendChild(s);
    }
    const n = document.createElement("span");
    n.className = "numero";
    n.textContent = numero;
    alvo.appendChild(n);
  }

  function formatarCodigo(codigo) {
    if (!codigo) return "";
    if (codigo.length === 13) {
      return `${codigo[0]} ${codigo.slice(1, 7)} ${codigo.slice(7)}`;
    }
    return codigo;
  }

  function conectado(ok) {
    sinal.classList.toggle("off", !ok);
    const texto = sinal.childNodes[sinal.childNodes.length - 1];
    if (texto && texto.nodeType === 3) {
      texto.textContent = ok ? "on-line" : "sem conexão";
    }
  }

  /* Leitor 2D em modo teclado: rajada rápida + Enter. */
  document.addEventListener("keydown", (ev) => {
    const agora = Date.now();
    const rajada = agora - ultimaTecla < TEMPO_LEITOR_MS;
    ultimaTecla = agora;

    if (ev.key === "Enter") {
      ev.preventDefault();
      consultar(digitado);
      return;
    }
    if (ev.key === "Escape") {
      ev.preventDefault();
      voltarAoInicio();
      return;
    }
    // Códigos de barras: dígitos e alfanumérico (Code 128 / QR embutido)
    if (ev.key.length === 1 && /[0-9A-Za-z\-]/.test(ev.key)) {
      ev.preventDefault();
      if (!rajada && (cenaAtual === "produto" || cenaAtual === "vazio")) {
        digitado = "";
        cancelarVolta();
        mostrar("ocioso");
      }
      if (digitado.length < 64) digitado += ev.key;
    }
  });

  function focar() {
    if (document.activeElement !== captura) captura.focus({ preventScroll: true });
  }
  ["click", "touchend", "focusin"].forEach((ev) =>
    document.addEventListener(ev, () => setTimeout(focar, 0))
  );
  setInterval(focar, 2500);
  focar();

  $("btn-tela").addEventListener("click", () => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  });

  async function verificarConexao() {
    try {
      const r = await fetch("/api/status", { cache: "no-store" });
      conectado(r.ok);
    } catch (e) {
      conectado(false);
    }
  }
  setInterval(verificarConexao, 20000);
  verificarConexao();
})();


