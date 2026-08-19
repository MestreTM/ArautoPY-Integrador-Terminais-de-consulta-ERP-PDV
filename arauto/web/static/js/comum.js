/* Utilidades compartilhadas pelas telas de administração. */
window.TC = (function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function json(url, opcoes) {
    const r = await fetch(url, Object.assign({ cache: "no-store" }, opcoes || {}));
    let corpo = null;
    try { corpo = await r.json(); } catch (e) { /* resposta sem corpo */ }
    if (!r.ok) {
      const erro = new Error((corpo && (corpo.detail || corpo.erro)) || `HTTP ${r.status}`);
      erro.status = r.status;
      erro.corpo = corpo;
      throw erro;
    }
    return corpo;
  }

  let timerAviso = null;
  function aviso(texto, ehErro) {
    const caixa = $("aviso");
    if (!caixa) return;
    $("aviso-texto").textContent = texto;
    caixa.classList.toggle("erro", !!ehErro);
    caixa.hidden = false;
    if (timerAviso) clearTimeout(timerAviso);
    timerAviso = setTimeout(() => { caixa.hidden = true; }, ehErro ? 6000 : 3200);
  }

  const hora = (iso) => {
    const d = new Date(iso);
    return isNaN(d) ? String(iso) : d.toLocaleTimeString("pt-BR", { hour12: false });
  };

  const desdeAgora = (epoch) => {
    const s = Math.max(0, Math.round(Date.now() / 1000 - epoch));
    if (s < 60) return s + "s";
    if (s < 3600) return Math.round(s / 60) + " min";
    if (s < 86400) return Math.round(s / 3600) + " h";
    return Math.round(s / 86400) + " dias";
  };

  let _imgPoll = null;
  let _imgOculto = false;
  let _imgJaMostrouFim = false;

  function _setToast(visivel, st) {
    const el = $("toast-download");
    if (!el) return;
    if (!visivel || _imgOculto) { el.hidden = true; return; }
    el.hidden = false;
    el.classList.toggle("toast-download--erro", st && st.fase === "erro");
    el.classList.toggle("toast-download--ok", st && st.fase === "concluido");
    const progresso = Math.max(0, Math.min(100, Number(st && st.progresso) || 0));
    const msg = $("toast-download-msg");
    const fill = $("toast-download-fill");
    const pct = $("toast-download-pct");
    if (msg) msg.textContent = (st && st.mensagem) || "Processando…";
    if (fill) fill.style.width = progresso + "%";
    if (pct) pct.textContent = progresso + "%";
  }

  async function _pollImagens() {
    try {
      const r = await fetch("/api/imagens/status", { cache: "no-store" });
      if (!r.ok) return;
      const st = await r.json();
      if (st.em_andamento) {
        _imgOculto = false;
        _imgJaMostrouFim = false;
        _setToast(true, st);
        return;
      }
      if (st.fase === "concluido" && st.progresso === 100 && !_imgJaMostrouFim) {
        _imgJaMostrouFim = true;
        _setToast(true, st);
        setTimeout(() => _setToast(false), 4500);
        return;
      }
      if (st.fase === "erro" && st.mensagem && !_imgJaMostrouFim) {
        _imgJaMostrouFim = true;
        _setToast(true, st);
        setTimeout(() => _setToast(false), 8000);
        return;
      }
      if (!st.em_andamento && st.fase !== "concluido" && st.fase !== "erro") {
        _setToast(false);
      }
    } catch (e) { /* kiosk / offline */ }
  }

  function iniciarMonitorImagens() {
    if (_imgPoll) return;
    const fechar = $("toast-download-fechar");
    if (fechar) {
      fechar.addEventListener("click", () => {
        _imgOculto = true;
        _setToast(false);
      });
    }
    _pollImagens();
    _imgPoll = setInterval(_pollImagens, 1500);
  }

  if (document.getElementById("toast-download")) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", iniciarMonitorImagens);
    } else {
      iniciarMonitorImagens();
    }
  }

  return { $, esc, json, aviso, hora, desdeAgora, iniciarMonitorImagens };
})();



