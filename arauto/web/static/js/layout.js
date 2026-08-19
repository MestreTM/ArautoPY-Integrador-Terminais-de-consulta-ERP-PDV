/* Editor de layout: arrasta, redimensiona e alinha os textos na simulação
   da tela do terminal. */
(function () {
  "use strict";

  const { $, esc, json, aviso } = window.TC;

  let dados = null;        // resposta de /api/layout
  let modelo = null;       // modelo em edição
  let layout = null;       // layout do modelo em edição
  let textos = {};         // conteúdo vindo da consulta simulada
  let selecionado = null;
  let escala = 1;
  let fatorCaractere = 0.55;
  let entrelinha = 1.15;

  const ELEMENTOS_VAZIO = ["nao_achado"];
  const ELEMENTOS_CAIXA = ["imagem"];  // retângulo (foto), não texto
  const IMA = 6;           // distância em px de tela para o elemento grudar
  const CANTOS = ["nw", "ne", "sw", "se"];

  function htmlAlcas() {
    return CANTOS.map((c) =>
      `<i class="alca alca--${c}" data-alca="${c}" title="Redimensionar (${c.toUpperCase()})"></i>`
    ).join("");
  }

  function preencherCores() {
    const cores = dados.cores || [];
    const semFundo = dados.cor_sem_fundo != null ? dados.cor_sem_fundo : -1;
    const opcoes = cores.map((c) =>
      `<option value="${c.codigo}">${esc(c.nome)} (${c.codigo})</option>`).join("");
    // Cor da tela não admite transparente (fundo sólido do terminal).
    const opcoesTela = cores
      .filter((c) => String(c.nome).toUpperCase() !== "TRANSPARENTE")
      .map((c) =>
        `<option value="${c.codigo}">${esc(c.nome)} (${c.codigo})</option>`).join("");
    const opcaoSem = `<option value="${semFundo}">SEM FUNDO (${semFundo})</option>`;
    $("cor-texto").innerHTML = opcoes;
    $("cor-tela").innerHTML = opcoesTela;
    $("cor-fundo-texto").innerHTML = opcaoSem + opcoes;
  }

  /* ------------------------------------------------------------ carga */
  async function carregar() {
    dados = await json("/api/layout");
    fatorCaractere = dados.fator_caractere || fatorCaractere;
    entrelinha = dados.entrelinha || entrelinha;
    preencherCores();
    if (modelo === null) {
      const conectado = dados.modelos.find((m) => m.conectados.length);
      modelo = (conectado || dados.modelos.find((m) => m.modelo === 506)
                || dados.modelos[0]).modelo;
    }
    pintarModelos();
    selecionarModelo(modelo);
  }

  function pintarModelos() {
    $("modelos").innerHTML = dados.modelos.map((m) => {
      const ligado = m.conectados.length;
      return `<button type="button" class="modelo ${m.modelo === modelo ? "modelo--ativo" : ""}"
                data-modelo="${m.modelo}">
        <b>${esc(m.nome)}</b>
        <span class="modelo-res mono">${m.largura}×${m.altura}</span>
        ${ligado ? `<span class="modelo-on">● conectado${ligado > 1 ? " (" + ligado + ")" : ""}</span>`
                 : `<span class="modelo-off">não conectado</span>`}
      </button>`;
    }).join("");
    document.querySelectorAll(".modelo").forEach((b) =>
      b.addEventListener("click", () => selecionarModelo(Number(b.dataset.modelo))));
  }

  function selecionarModelo(id) {
    modelo = id;
    layout = JSON.parse(JSON.stringify(dados.modelos.find((m) => m.modelo === id)));
    $("resolucao").textContent = `${layout.largura}×${layout.altura}`;
    $("fonte-normal").value = layout.fonte_normal;
    $("fonte-negrito").value = layout.fonte_negrito;
    $("cor-texto").value = layout.cor_texto;
    $("cor-fundo-texto").value = layout.cor_fundo_texto;
    $("cor-tela").value = layout.cor_tela;
    selecionado = null;
    pintarModelos();
    pintarCampos();
    desenhar();
  }

  /* ----------------------------------------------------------- prévia */
  async function buscarTextos() {
    const codigo = $("codigo-previa").value.trim() || "7896080900001";
    try {
      const r = await json("/api/layout/previa?codigo=" + encodeURIComponent(codigo));
      textos = r.textos;
      $("modo-vazio").checked = !r.encontrado;
      if (!r.encontrado) aviso("Produto não cadastrado; simulando a tela de não encontrado.");
    } catch (e) {
      textos = {
        codigo: codigo, descricao: "PRODUTO DE EXEMPLO COM NOME LONGO",
        rotulo1: "Preço", preco1: "R$ 9,99",
        rotulo2: "Preço personalizado", preco2: "R$ 8,49",
        nao_achado: "Produto não encontrado",
      };
    }
    desenhar();
  }

  function visiveis() {
    const vazio = $("modo-vazio").checked;
    return Object.keys(layout.elementos).filter((k) => {
      if (ELEMENTOS_CAIXA.includes(k)) return !vazio; // foto só no modo produto
      return vazio ? ELEMENTOS_VAZIO.includes(k) : !ELEMENTOS_VAZIO.includes(k);
    });
  }

  /* Mesma conta do servidor (arauto/core/layout.py: quebrar_texto). */
  function quebrar(texto, tamanho, largura, maxLinhas) {
    texto = (texto || "").trim();
    if (!texto) return [];
    if (largura <= 0 || maxLinhas <= 1) return [texto];

    const porLinha = Math.max(1, Math.floor(largura / Math.max(1, tamanho * fatorCaractere)));
    if (texto.length <= porLinha) return [texto];

    const linhas = [];
    let atual = "";
    for (let palavra of texto.split(/\s+/)) {
      while (palavra.length > porLinha) {
        if (atual) { linhas.push(atual); atual = ""; }
        linhas.push(palavra.slice(0, porLinha));
        palavra = palavra.slice(porLinha);
      }
      const candidata = (atual ? atual + " " + palavra : palavra);
      if (candidata.length <= porLinha) atual = candidata;
      else { if (atual) linhas.push(atual); atual = palavra; }
    }
    if (atual) linhas.push(atual);

    if (linhas.length > maxLinhas) {
      linhas.length = maxLinhas;
      const ultima = linhas[maxLinhas - 1] || "";
      linhas[maxLinhas - 1] = ultima.slice(0, Math.max(0, porLinha - 1)).trimEnd() + "…";
    }
    return linhas;
  }

  /* ----------------------------------------------------------- desenho */
  function desenhar() {
    const tela = $("tela");
    const disponivel = tela.parentElement.clientWidth - 4;
    escala = Math.min(1, disponivel / layout.largura);

    tela.style.width = layout.largura * escala + "px";
    tela.style.height = layout.altura * escala + "px";
    tela.innerHTML =
      '<div class="guia guia--v" id="guia-v" hidden></div>' +
      '<div class="guia guia--h" id="guia-h" hidden></div>';

    visiveis().forEach((chave) => {
      const el = layout.elementos[chave];
      if (!el.visivel) return;

      // Caixa da foto do produto (retângulo arrastável/redimensionável).
      if (ELEMENTOS_CAIXA.includes(chave)) {
        const bw = Math.max(20, el.largura || 120);
        const bh = Math.max(20, el.altura || 120);
        const bloco = document.createElement("div");
        bloco.className = "txt txt--img" + (selecionado === chave ? " txt--sel" : "");
        bloco.dataset.chave = chave;
        bloco.style.left = ((el.x < 0 ? 0 : el.x) * escala) + "px";
        bloco.style.top = (el.y * escala) + "px";
        bloco.style.width = (bw * escala) + "px";
        bloco.style.height = (bh * escala) + "px";
        bloco.innerHTML = '<span class="img-rotulo">Foto</span>'
          + (selecionado === chave ? htmlAlcas() : "");
        tela.appendChild(bloco);
        return;
      }

      const texto = textos[chave] || "";
      if (!texto) return;

      const partes = quebrar(texto, el.tamanho, el.largura, el.linhas);
      const bloco = document.createElement("div");
      bloco.className = "txt" + (selecionado === chave ? " txt--sel" : "");
      bloco.dataset.chave = chave;
      bloco.style.fontSize = (el.tamanho * escala) + "px";
      bloco.style.fontWeight = el.negrito ? "700" : "400";
      bloco.style.lineHeight = String(entrelinha);
      bloco.style.top = (el.y * escala) + "px";
      if (el.x < 0) {
        bloco.style.left = "0"; bloco.style.right = "0";
        bloco.style.textAlign = "center";
      } else {
        bloco.style.left = (el.x * escala) + "px";
      }
      bloco.innerHTML = partes.map((p) => `<span>${esc(p)}</span>`).join("<br>")
        + (selecionado === chave ? htmlAlcas() : "");
      tela.appendChild(bloco);
    });

    avisarCorte();
    marcarSelecionado();
  }

  function avisarCorte() {
    const estourando = [];
    $("tela").querySelectorAll(".txt").forEach((div) => {
      const el = layout.elementos[div.dataset.chave];
      const spans = [...div.querySelectorAll("span")];
      const larg = spans.length
        ? Math.max(...spans.map((s) => s.getBoundingClientRect().width)) : 0;
      const inicio = el.x < 0 ? (layout.largura * escala - larg) / 2 : el.x * escala;
      if (inicio + larg > layout.largura * escala + 1) {
        div.classList.add("txt--corta");
        estourando.push(div.dataset.chave);
      }
    });
    const caixa = $("aviso-corte");
    caixa.hidden = !estourando.length;
    if (estourando.length) {
      const nomes = estourando.map((c) =>
        (dados.elementos.find((e) => e.chave === c) || {}).rotulo || c);
      caixa.textContent = "Cortado na borda: " + nomes.join(", ")
        + ". Reduza a fonte, mova para a esquerda, ou ligue a quebra de linha.";
    }
  }

  /* ------------------------------------------- arrasto, ímã e alças */
  let acao = null;

  function larguraNaTela(chave) {
    const div = $("tela").querySelector(`.txt[data-chave="${chave}"]`);
    if (!div) return 0;
    if (ELEMENTOS_CAIXA.includes(chave)) return div.getBoundingClientRect().width;
    const span = div.querySelector("span");
    return span ? span.getBoundingClientRect().width : div.getBoundingClientRect().width;
  }

  function alturaNaTela(chave) {
    const el = layout.elementos[chave];
    if (ELEMENTOS_CAIXA.includes(chave)) {
      return Math.max(20, el.altura || 120) * escala;
    }
    return alturaDoBloco(chave) * escala;
  }

  /** Referências de alinhamento: centro da tela + bordas/centros dos outros. */
  function referenciasAlinhamento(exceto) {
    const xs = [0, (layout.largura * escala) / 2, layout.largura * escala];
    const ys = [0, (layout.altura * escala) / 2, layout.altura * escala];
    visiveis().forEach((chave) => {
      if (chave === exceto) return;
      const el = layout.elementos[chave];
      if (!el.visivel) return;
      const w = larguraNaTela(chave);
      const h = alturaNaTela(chave);
      let left;
      if (el.x < 0) left = (layout.largura * escala - w) / 2;
      else left = el.x * escala;
      const top = el.y * escala;
      xs.push(left, left + w / 2, left + w);
      ys.push(top, top + h / 2, top + h);
    });
    return { xs, ys };
  }

  /** Retorna a referência mais próxima ou `null` se estiver fora do ímã. */
  function snappoint(valor, refs) {
    let melhor = null, dist = IMA + 1;
    refs.forEach((r) => {
      const d = Math.abs(valor - r);
      if (d < dist) { dist = d; melhor = r; }
    });
    return dist <= IMA ? melhor : null;
  }

  $("tela").addEventListener("pointerdown", (ev) => {
    const alca = ev.target.closest(".alca");
    const alvo = ev.target.closest(".txt");
    if (!alvo) { selecionado = null; desenhar(); return; }

    selecionado = alvo.dataset.chave;
    const el = layout.elementos[selecionado];
    const caixa = alvo.getBoundingClientRect();
    const ehCaixa = ELEMENTOS_CAIXA.includes(selecionado);
    const canto = alca ? alca.dataset.alca : null;

    if (alca && ehCaixa) {
      acao = {
        tipo: "caixa", chave: selecionado, canto,
        x0: ev.clientX, y0: ev.clientY,
        origX: Math.max(0, el.x), origY: el.y,
        w0: el.largura || 120, h0: el.altura || 120,
      };
    } else if (alca) {
      acao = {
        tipo: "tamanho", chave: selecionado, canto,
        y0: ev.clientY, tam0: el.tamanho,
      };
    } else {
      acao = {
        tipo: "mover", chave: selecionado,
        dx: ev.clientX - caixa.left, dy: ev.clientY - caixa.top,
      };
    }

    alvo.setPointerCapture(ev.pointerId);
    desenhar();
    $("tela").focus();
    ev.preventDefault();
  });

  $("tela").addEventListener("pointermove", (ev) => {
    if (!acao) return;
    const el = layout.elementos[acao.chave];

    if (acao.tipo === "caixa") {
      const dw = (ev.clientX - acao.x0) / escala;
      const dh = (ev.clientY - acao.y0) / escala;
      let x = acao.origX, y = acao.origY, w = acao.w0, h = acao.h0;
      const c = acao.canto || "se";
      if (c.includes("e")) w = acao.w0 + dw;
      if (c.includes("w")) { w = acao.w0 - dw; x = acao.origX + dw; }
      if (c.includes("s")) h = acao.h0 + dh;
      if (c.includes("n")) { h = acao.h0 - dh; y = acao.origY + dh; }
      w = Math.max(20, Math.round(w));
      h = Math.max(20, Math.round(h));
      x = Math.max(0, Math.min(layout.largura - w, Math.round(x)));
      y = Math.max(0, Math.min(layout.altura - h, Math.round(y)));
      el.x = x; el.y = y; el.largura = w; el.altura = h;
      desenhar();
      sincronizarCampos(acao.chave);
      return;
    }

    if (acao.tipo === "tamanho") {
      // Cantos sul aumentam para baixo; norte, para cima (sinal invertido).
      const sinal = (acao.canto || "se").includes("n") ? -1 : 1;
      const delta = sinal * (ev.clientY - acao.y0) / escala;
      el.tamanho = Math.max(6, Math.min(200, Math.round(acao.tam0 + delta)));
      el.y = Math.min(el.y, Math.max(0, layout.altura - el.tamanho));
      desenhar();
      sincronizarCampos(acao.chave);
      return;
    }

    // --- mover com guias de alinhamento a outros elementos ---
    const telaCaixa = $("tela").getBoundingClientRect();
    const larg = larguraNaTela(acao.chave);
    const alt = alturaNaTela(acao.chave);
    let esquerda = ev.clientX - acao.dx - telaCaixa.left;
    let topo = ev.clientY - acao.dy - telaCaixa.top;

    const refs = referenciasAlinhamento(acao.chave);
    const leftSnap = snappoint(esquerda, refs.xs);
    const rightSnap = snappoint(esquerda + larg, refs.xs);
    const cxSnap = snappoint(esquerda + larg / 2, refs.xs);
    const topSnap = snappoint(topo, refs.ys);
    const bottomSnap = snappoint(topo + alt, refs.ys);
    const cySnap = snappoint(topo + alt / 2, refs.ys);

    let guiaVX = null, guiaHY = null;

    // Prioridade: centro > borda esquerda/topo > borda direita/base
    if (cxSnap != null) {
      esquerda = cxSnap - larg / 2; guiaVX = cxSnap;
    } else if (leftSnap != null) {
      esquerda = leftSnap; guiaVX = leftSnap;
    } else if (rightSnap != null) {
      esquerda = rightSnap - larg; guiaVX = rightSnap;
    }

    if (cySnap != null) {
      topo = cySnap - alt / 2; guiaHY = cySnap;
    } else if (topSnap != null) {
      topo = topSnap; guiaHY = topSnap;
    } else if (bottomSnap != null) {
      topo = bottomSnap - alt; guiaHY = bottomSnap;
    }

    const centroTelaX = (layout.largura * escala) / 2;
    const centroTela = Math.abs((esquerda + larg / 2) - centroTelaX) < 0.5;

    el.x = centroTela ? -1
      : Math.max(0, Math.min(layout.largura - 1, Math.round(esquerda / escala)));
    const maxY = ELEMENTOS_CAIXA.includes(acao.chave)
      ? layout.altura - Math.max(20, el.altura || 20)
      : layout.altura - el.tamanho;
    el.y = Math.max(0, Math.min(maxY, Math.round(topo / escala)));

    desenhar();
    mostrarGuias(guiaVX, guiaHY);
    sincronizarCampos(acao.chave);
  });

  ["pointerup", "pointercancel"].forEach((e) =>
    $("tela").addEventListener(e, () => { acao = null; mostrarGuias(null, null); }));

  function mostrarGuias(xPx, yPx) {
    const gv = $("guia-v"), gh = $("guia-h");
    if (gv) {
      if (xPx == null) { gv.hidden = true; }
      else {
        gv.hidden = false;
        gv.style.left = xPx + "px";
        gv.style.transform = "translateX(-0.5px)";
      }
    }
    if (gh) {
      if (yPx == null) { gh.hidden = true; }
      else {
        gh.hidden = false;
        gh.style.top = yPx + "px";
        gh.style.transform = "translateY(-0.5px)";
      }
    }
  }

  /* ------------------------------------------------ centralizar */
  function alturaDoBloco(chave) {
    const el = layout.elementos[chave];
    const n = quebrar(textos[chave] || "", el.tamanho, el.largura, el.linhas).length || 1;
    return el.tamanho + Math.round(el.tamanho * entrelinha) * (n - 1);
  }

  function centralizar(eixo) {
    if (!selecionado) { aviso("Escolha um elemento primeiro.", true); return; }
    const el = layout.elementos[selecionado];
    if (eixo === "h" || eixo === "ambos") el.x = -1;
    if (eixo === "v" || eixo === "ambos") {
      el.y = Math.max(0, Math.round((layout.altura - alturaDoBloco(selecionado)) / 2));
    }
    desenhar();
    sincronizarCampos(selecionado);
  }
  $("btn-c-h").addEventListener("click", () => centralizar("h"));
  $("btn-c-v").addEventListener("click", () => centralizar("v"));
  $("btn-c-ambos").addEventListener("click", () => centralizar("ambos"));

  $("tela").addEventListener("keydown", (ev) => {
    if (!selecionado) return;
    const passo = ev.shiftKey ? 10 : 1;
    const el = layout.elementos[selecionado];
    const mapa = { ArrowLeft: [-passo, 0], ArrowRight: [passo, 0],
                   ArrowUp: [0, -passo], ArrowDown: [0, passo] };
    if (!mapa[ev.key]) return;
    ev.preventDefault();
    const [dx, dy] = mapa[ev.key];
    if (dx) {
      // sai da centralização para poder mover no eixo X
      if (el.x < 0) {
        const larg = larguraNaTela(selecionado) / escala;
        el.x = Math.round((layout.largura - larg) / 2);
      }
      el.x = Math.max(0, Math.min(layout.largura - 1, el.x + dx));
    }
    if (dy) el.y = Math.max(0, Math.min(layout.altura - el.tamanho, el.y + dy));
    desenhar();
    sincronizarCampos(selecionado);
  });

  function marcarSelecionado() {
    document.querySelectorAll(".elemento").forEach((linha) =>
      linha.classList.toggle("elemento--sel", linha.dataset.chave === selecionado));
  }

  /* ------------------------------------------------------------ campos */
  function pintarCampos() {
    $("elementos").innerHTML = dados.elementos.map(({ chave, rotulo }) => {
      const el = layout.elementos[chave];
      const ehCaixa = ELEMENTOS_CAIXA.includes(chave);
      const campos = ehCaixa
        ? `<label>X <input type="number" data-campo="x" data-chave="${chave}"
                 value="${el.x}" min="0" max="${layout.largura - 1}"></label>
           <label>Y <input type="number" data-campo="y" data-chave="${chave}"
                 value="${el.y}" min="0" max="${layout.altura - 1}"></label>
           <label title="Largura da caixa da foto">Larg
             <input type="number" data-campo="largura" data-chave="${chave}"
                 value="${el.largura || 0}" min="20" max="${layout.largura}"></label>
           <label title="Altura da caixa da foto">Alt
             <input type="number" data-campo="altura" data-chave="${chave}"
                 value="${el.altura || 0}" min="20" max="${layout.altura}"></label>`
        : `<label>X <input type="number" data-campo="x" data-chave="${chave}"
                 value="${el.x}" min="-1" max="${layout.largura - 1}"></label>
           <label>Y <input type="number" data-campo="y" data-chave="${chave}"
                 value="${el.y}" min="0" max="${layout.altura - 1}"></label>
           <label>Tam <input type="number" data-campo="tamanho" data-chave="${chave}"
                 value="${el.tamanho}" min="6" max="200"></label>
           <label class="cx">Negrito <input type="checkbox" data-campo="negrito"
                 data-chave="${chave}" ${el.negrito ? "checked" : ""}></label>
           <label title="Largura em pixels para quebrar o texto. 0 = não quebra.">Quebra
             <input type="number" data-campo="largura" data-chave="${chave}"
                 value="${el.largura}" min="0" max="${layout.largura}"></label>
           <label title="Máximo de linhas. O excesso vira reticências.">Linhas
             <input type="number" data-campo="linhas" data-chave="${chave}"
                 value="${el.linhas}" min="1" max="6"></label>`;
      return `<div class="elemento" data-chave="${chave}">
        <div class="elemento-topo">
          <label class="interruptor-linha">
            <input type="checkbox" data-campo="visivel" data-chave="${chave}"
                   ${el.visivel ? "checked" : ""}>
            <span class="trilho"></span><span>${esc(rotulo)}</span>
          </label>
        </div>
        <div class="elemento-campos">${campos}</div>
      </div>`;
    }).join("");

    $("elementos").querySelectorAll("input").forEach((campo) => {
      campo.addEventListener("input", () => {
        const el = layout.elementos[campo.dataset.chave];
        const nome = campo.dataset.campo;
        el[nome] = campo.type === "checkbox" ? campo.checked : Number(campo.value);
        desenhar();
      });
      campo.addEventListener("focus", () => {
        selecionado = campo.dataset.chave; desenhar();
      });
    });
  }

  function sincronizarCampos(chave) {
    const el = layout.elementos[chave];
    const campos = ELEMENTOS_CAIXA.includes(chave)
      ? ["x", "y", "largura", "altura"]
      : ["x", "y", "tamanho"];
    campos.forEach((nome) => {
      const campo = document.querySelector(
        `input[data-campo="${nome}"][data-chave="${chave}"]`);
      if (campo) campo.value = el[nome];
    });
  }

  /* ------------------------------------------------------------ ações */
  function coletar() {
    return {
      elementos: layout.elementos,
      fonte_normal: $("fonte-normal").value.trim(),
      fonte_negrito: $("fonte-negrito").value.trim(),
      cor_texto: Number($("cor-texto").value),
      cor_fundo_texto: Number($("cor-fundo-texto").value),
      cor_tela: Number($("cor-tela").value),
    };
  }

  // `ev.currentTarget` vira nulo depois de um await; guardar a referência
  // antes é o que impede o botão de travar após o primeiro clique.
  $("btn-salvar").addEventListener("click", async (ev) => {
    const botao = ev.currentTarget;
    const rotulo = botao.textContent;
    botao.disabled = true;
    botao.textContent = "Salvando…";
    try {
      await json("/api/layout/" + modelo, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(coletar()),
      });
      const nome = layout.nome;
      await carregar();
      aviso(`Layout de ${nome} salvo. Vale para todos os aparelhos desse modelo.`);
    } catch (e) {
      aviso("Não foi possível salvar: " + e.message, true);
    } finally {
      botao.disabled = false;
      botao.textContent = rotulo;
    }
  });

  $("btn-restaurar").addEventListener("click", async (ev) => {
    const botao = ev.currentTarget;
    botao.disabled = true;
    try {
      await json(`/api/layout/${modelo}/restaurar`, { method: "POST" });
      await carregar();
      aviso("Layout restaurado ao padrão do servidor original.");
    } catch (e) {
      aviso("Falha ao restaurar: " + e.message, true);
    } finally {
      botao.disabled = false;
    }
  });

  /* Copiar entre modelos reescala: um layout de 480×272 colado cru num G-BOT
     de 1280×800 ficaria amontoado num canto. */
  $("btn-copiar").addEventListener("click", async (ev) => {
    const botao = ev.currentTarget;
    const outros = dados.modelos.filter((m) => m.modelo !== modelo);
    if (!outros.length) return;
    const nomes = outros.map((m) => `${m.nome} (${m.largura}×${m.altura})`).join(", ");
    if (!confirm(`Copiar este layout, reescalado, para: ${nomes}?`)) return;

    botao.disabled = true;
    let erros = 0;
    try {
      for (const alvo of outros) {
        const fx = alvo.largura / layout.largura;
        const fy = alvo.altura / layout.altura;
        const fator = Math.min(fx, fy);
        const elementos = {};
        Object.entries(layout.elementos).forEach(([chave, el]) => {
          elementos[chave] = {
            x: el.x < 0 ? -1 : Math.round(el.x * fx),
            y: Math.round(el.y * fy),
            tamanho: Math.max(6, Math.round(el.tamanho * fator)),
            negrito: el.negrito, visivel: el.visivel,
            largura: Math.round((el.largura || 0) * fx),
            linhas: el.linhas || 1,
            altura: Math.round((el.altura || 0) * fy),
          };
        });
        try {
          await json("/api/layout/" + alvo.modelo, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(Object.assign(coletar(), { elementos })),
          });
        } catch (e) { erros++; }
      }
      await carregar();
      aviso(erros ? `Copiado, mas ${erros} modelo(s) falharam.`
                  : "Layout copiado e reescalado para os outros modelos.");
    } finally {
      botao.disabled = false;
    }
  });

  $("btn-previa").addEventListener("click", buscarTextos);
  $("codigo-previa").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); buscarTextos(); }
  });
  $("modo-vazio").addEventListener("change", desenhar);
  window.addEventListener("resize", () => layout && desenhar());

  (async function () {
    await carregar();
    await buscarTextos();
  })();
})();


