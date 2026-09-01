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
    var padrao = (window.ARAUTO_DOCKER || (window.ARAUTO_AUTOSTART && window.ARAUTO_AUTOSTART.docker))
      ? "host.docker.internal" : "localhost";
    var host = (campos.host || padrao).trim() || padrao;
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

  function emDocker() {
    return !!(window.ARAUTO_DOCKER || (window.ARAUTO_AUTOSTART && window.ARAUTO_AUTOSTART.docker));
  }

  function hostDaUrl(url) {
    var m = String(url || "").match(/@([^/?#]+)/);
    if (!m) return "";
    return m[1].split(":")[0];
  }

  function urlComHost(url, host) {
    var atual = String(url || "");
    if (!atual || !host) return atual;
    return atual.replace(/@([^/?#]+)/, function (_, h) {
      var porta = h.indexOf(":") >= 0 ? h.slice(h.indexOf(":")) : "";
      return "@" + host + porta;
    });
  }

  function hostEhLocal(host) {
    var h = String(host || "").toLowerCase();
    return h === "localhost" || h === "127.0.0.1" || h === "::1" || h === "[::1]";
  }

  function urlSqlAmbiente(url) {
    var atual = String(url || "").trim();
    if (!atual) return atual;
    if (emDocker() && hostEhLocal(hostDaUrl(atual))) {
      return urlComHost(atual, "host.docker.internal");
    }
    return atual;
  }

  async function testarSqlUrl(url, extra) {
    extra = extra || {};
    try {
      var r = await json("/api/config/testar-sql", {
        method: "POST",
        body: Object.assign({}, extra, { DB_URL: url }),
      });
      return { ok: !!r.ok, detail: r.detail || (r.ok ? "Conectou" : "Falhou"), url: url };
    } catch (e) {
      return { ok: false, detail: e.message || String(e), url: url };
    }
  }

  async function testarSqlComFallback(url, extra) {
    var alvo = urlSqlAmbiente(String(url || "").trim());
    var a = await testarSqlUrl(alvo, extra);
    if (a.ok) return Object.assign(a, { trocou: alvo !== url });
    if (hostEhLocal(hostDaUrl(alvo))) {
      var alt = urlComHost(alvo, "host.docker.internal");
      var b = await testarSqlUrl(alt, extra);
      if (b.ok) return Object.assign(b, { trocou: true });
      a.alternativo = b;
    }
    return a;
  }

  function garantirModalHostSql() {
    if ($("modal-sql-host")) return $("modal-sql-host");
    var wrap = document.createElement("div");
    wrap.id = "modal-sql-host";
    wrap.className = "modal-sql";
    wrap.hidden = true;
    wrap.innerHTML =
      '<div class="modal-sql-fundo" id="modal-sql-host-fundo"></div>' +
      '<div class="modal-sql-caixa" role="dialog" aria-modal="true">' +
      '<header class="modal-sql-cab"><div><h2>Onde está o banco?</h2>' +
      '<p class="dica">Você usou <strong>localhost</strong>. No Docker isso costuma ser o container, não o Windows. Testamos os dois endereços com as mesmas credenciais.</p></div></header>' +
      '<div id="modal-sql-host-corpo" class="setup-plug-lista"></div>' +
      '<footer class="modal-sql-rodape" style="flex-wrap:wrap">' +
      '<button type="button" class="botao" id="modal-sql-host-local">Continuar com localhost</button>' +
      '<button type="button" class="botao botao--claro" id="modal-sql-host-docker">Usar host.docker.internal</button>' +
      '</footer></div>';
    document.body.appendChild(wrap);
    return wrap;
  }

  function confirmarHostSql(opts) {
    opts = opts || {};
    var url = String(opts.url || "").trim();
    var extra = opts.extra || {};
    return new Promise(function (resolve) {
      if (!url || !hostEhLocal(hostDaUrl(url))) {
        resolve(url);
        return;
      }
      var modal = garantirModalHostSql();
      var corpo = $("modal-sql-host-corpo");
      if (corpo) corpo.innerHTML = "<p class=\"meta-img\">Testando localhost e host.docker.internal…</p>";
      modal.hidden = false;
      var urlDocker = urlComHost(url, "host.docker.internal");
      var urlLocal = urlComHost(url, "localhost");

      function linha(nome, r) {
        return "<article class=\"setup-plug-card\"><div><strong>" + esc(nome) + "</strong>" +
          "<p class=\"meta-img\">" + esc(r.detail || (r.ok ? "Conectou" : "Não conectou")) + "</p></div>" +
          "<span class=\"badge-img " + (r.ok ? "badge-img--ok" : "badge-img--no") + "\">" +
          (r.ok ? "Conectou" : "Falhou") + "</span></article>";
      }

      function fechar(escolhida) {
        modal.hidden = true;
        resolve(escolhida || url);
      }

      Promise.all([
        json("/api/config/testar-sql", { method: "POST", body: Object.assign({}, extra, { DB_URL: urlLocal }) })
          .then(function (r) { return { ok: !!r.ok, detail: r.detail || "Conectou" }; })
          .catch(function (e) { return { ok: false, detail: e.message || String(e) }; }),
        json("/api/config/testar-sql", { method: "POST", body: Object.assign({}, extra, { DB_URL: urlDocker }) })
          .then(function (r) { return { ok: !!r.ok, detail: r.detail || "Conectou" }; })
          .catch(function (e) { return { ok: false, detail: e.message || String(e) }; }),
      ]).then(function (pares) {
        if (corpo) {
          corpo.innerHTML = linha("localhost", pares[0]) + linha("host.docker.internal", pares[1]);
        }
        var bLocal = $("modal-sql-host-local");
        var bDock = $("modal-sql-host-docker");
        if (bLocal) bLocal.onclick = function () { fechar(urlLocal); };
        if (bDock) bDock.onclick = function () { fechar(urlDocker); };
        var fundo = $("modal-sql-host-fundo");
        if (fundo) fundo.onclick = function () { fechar(url); };
      });
    });
  }

  window.TC = {
    $: $,
    esc: esc,
    json: json,
    aviso: aviso,
    montarSqlUrl: montarSqlUrl,
    emDocker: emDocker,
    hostDaUrl: hostDaUrl,
    urlComHost: urlComHost,
    urlSqlAmbiente: urlSqlAmbiente,
    testarSqlComFallback: testarSqlComFallback,
    confirmarHostSql: confirmarHostSql,
  };
})();
