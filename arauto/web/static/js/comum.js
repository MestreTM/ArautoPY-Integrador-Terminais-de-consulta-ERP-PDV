/* ArautoPY — helpers compartilhados do painel (window.TC).
   Usado por config.js, plugins.js, monitor.js e demais scripts de página. */
(function () {
  "use strict";

  function $(id) {
    return typeof id === "string" ? document.getElementById(id) : id;
  }

  function esc(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function json(url, opts) {
    opts = opts || {};
    var headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData)) {
      headers["Content-Type"] = headers["Content-Type"] || "application/json";
      opts = Object.assign({}, opts, { body: JSON.stringify(opts.body) });
    }
    var res = await fetch(url, Object.assign({}, opts, { headers: headers }));
    var ct = res.headers.get("content-type") || "";
    var data = null;
    if (ct.indexOf("application/json") !== -1) {
      data = await res.json();
    } else {
      var txt = await res.text();
      try { data = JSON.parse(txt); } catch (e) { data = { detail: txt || res.statusText }; }
    }
    if (!res.ok) {
      var msg = (data && (data.detail || data.message || data.erro)) || ("HTTP " + res.status);
      if (Array.isArray(msg)) msg = msg.map(function (m) { return m.msg || m; }).join(" · ");
      var err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  var _avisoTimer = null;
  var AVISO_ROTULO = { ok: "OK", aviso: "Atenção", erro: "Erro", info: "Info" };
  function aviso(texto, tipo) {
    var kind = "ok";
    if (tipo === true || tipo === "erro" || tipo === "error") kind = "erro";
    else if (tipo === "aviso" || tipo === "warn" || tipo === "alerta") kind = "aviso";
    else if (tipo === "info") kind = "info";
    else if (tipo === false || tipo === "ok" || tipo === "sucesso" || tipo == null || tipo === "") kind = "ok";
    else kind = "ok";
    var el = $("aviso");
    var span = $("aviso-texto");
    if (!el || !span) {
      try { console[kind === "erro" ? "error" : "log"](texto); } catch (e) {}
      return;
    }
    var badge = $("aviso-tipo");
    if (!badge) {
      badge = document.createElement("strong");
      badge.id = "aviso-tipo";
      badge.className = "aviso-tipo";
      el.insertBefore(badge, span);
    }
    badge.textContent = AVISO_ROTULO[kind] || "OK";
    span.textContent = texto == null ? "" : String(texto);
    el.className = "aviso aviso--" + kind;
    if (kind === "erro") el.classList.add("erro");
    el.removeAttribute("hidden");
    el.hidden = false;
    el.setAttribute("role", kind === "erro" ? "alert" : "status");
    if (_avisoTimer) clearTimeout(_avisoTimer);
    _avisoTimer = setTimeout(function () {
      el.hidden = true;
      el.setAttribute("hidden", "");
    }, kind === "erro" ? 8000 : 4500);
  }

  function montarSqlUrl(d, campos) {
    campos = campos || {};
    if (campos.avancado) {
      return String(campos.url || "").trim();
    }
    if (!d) return "";
    var host = (campos.host || "localhost").trim() || "localhost";
    var porta = String(campos.porta || "").trim();
    var user = campos.user || "";
    var pass = campos.pass || "";
    var db = String(campos.db || "").trim().replace(/\\/g, "/");
    if (d.id === "sqlite") return "sqlite:///" + db;
    var auth = user ? (encodeURIComponent(user) + (pass !== "" ? ":" + encodeURIComponent(pass) : "") + "@") : "";
    var portPart = porta ? (":" + porta) : "";
    if (d.arquivo && /^[A-Za-z]:/.test(db) && db.charAt(0) !== "/") db = "/" + db;
    var path = db ? (db.charAt(0) === "/" ? db : "/" + db) : "/";
    var url = (d.scheme || "") + "://" + auth + host + portPart + path;
    if (d.id === "mssql" && String(d.scheme || "").indexOf("pyodbc") >= 0 && url.indexOf("driver=") < 0) {
      url += "?driver=ODBC+Driver+17+for+SQL+Server";
    }
    return url;
  }

  window.TC = {
    $: $,
    esc: esc,
    json: json,
    aviso: aviso,
    montarSqlUrl: montarSqlUrl,
  };
})();
