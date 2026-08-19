(function(){
  const {$, esc, json, aviso} = window.TC;
  let arquivos = [], seq = [];
  function peer(){ return ($("peer") && $("peer").value) || ""; }

  function modal(html) {
    const fundo = document.createElement("div");
    fundo.className = "midia-modal-fundo";
    fundo.innerHTML = `<div class="midia-modal-caixa">${html}</div>`;
    document.body.appendChild(fundo);
    const caixa = fundo.querySelector(".midia-modal-caixa");
    fundo.addEventListener("click", (e) => { if (e.target === fundo) fundo.remove(); });
    return { fundo, caixa, fechar: () => fundo.remove() };
  }

  async function carregarPeers(){
    const r = await json("/plugins/midia-tc506/api/peers");
    const sel = $("peer");
    const cur = sel.value;
    sel.innerHTML = (r.peers||[]).map(p =>
      `<option value="${esc(p.peer)}">${esc(p.peer)} — ${esc(p.model||"?")}</option>`
    ).join("") || '<option value="">Nenhum SC504</option>';
    if (cur) sel.value = cur;
  }

  async function listar(){
    const p = peer();
    if (!p) return;
    $("status").textContent = "Lendo...";
    try {
      const r = await json("/plugins/midia-tc506/api/listar?peer="+encodeURIComponent(p));
      if (!r.ok) throw new Error(r.detail||"Falha");
      arquivos = r.arquivos||[]; seq = r.sequencia||[];
      renderArquivos(); renderSeq();
      $("status").textContent = arquivos.length+" arquivo(s) · seq "+seq.length;
    } catch(e){ $("status").textContent = e.message; aviso(e.message, true); }
  }

  function urlBaixar(path) {
    return "/plugins/midia-tc506/api/baixar?peer="+encodeURIComponent(peer())+"&path="+encodeURIComponent(path);
  }

  async function visualizar(path) {
    const m = modal(`
      <h3>Visualizar</h3>
      <p class="meta-img mono">${esc(path)}</p>
      <div class="midia-preview-box" id="prev-box"><p class="meta-img">Carregando do terminal…</p></div>
      <div class="midia-modal-acoes">
        <a class="botao" href="${urlBaixar(path)}" download>Baixar</a>
        <button type="button" class="botao botao--fantasma" data-x>Fechar</button>
      </div>`);
    m.caixa.querySelector("[data-x]").onclick = m.fechar;
    try {
      const r = await fetch(urlBaixar(path));
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || "Falha ao obter arquivo");
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const box = m.caixa.querySelector("#prev-box");
      const low = path.toLowerCase();
      if (/\.(jpg|jpeg|png|gif|bmp|tif|tiff|webp)$/.test(low)) {
        box.innerHTML = `<img src="${url}" alt="">`;
      } else if (/\.(mp4|avi|webm)$/.test(low)) {
        box.innerHTML = `<video src="${url}" controls></video>`;
      } else if (/\.(mp3|wav)$/.test(low)) {
        box.innerHTML = `<audio src="${url}" controls style="width:100%"></audio>`;
      } else {
        box.innerHTML = `<p class="meta-img">Pré-visualização não disponível para este tipo.<br>
          <a class="botao botao--claro" href="${url}" download style="margin-top:.6rem;display:inline-block">Baixar arquivo</a></p>`;
      }
    } catch (e) {
      const box = m.caixa.querySelector("#prev-box");
      if (box) box.innerHTML = `<p class="meta-img" style="color:var(--alerta)">${esc(e.message)}</p>`;
    }
  }

  function abrirUpload() {
    if (!peer()) { aviso("Selecione um terminal.", true); return; }
    const m = modal(`
      <h3>Enviar mídia</h3>
      <p class="meta-img">Arquivo será gravado em INT_MEM no terminal selecionado.</p>
      <div class="midia-upload-zone" id="up-zone">
        <strong>Arraste a imagem aqui</strong>
        <span class="meta-img">ou clique para escolher · jpg, png, bmp, gif, mp3, avi…</span>
        <input type="file" id="up-file" accept="image/*,.bmp,.jpg,.jpeg,.png,.gif,.mp3,.avi" hidden>
      </div>
      <p class="meta-img" id="up-nome" style="margin-top:.6rem"></p>
      <div class="midia-modal-acoes">
        <button type="button" class="botao botao--fantasma" data-x>Cancelar</button>
        <button type="button" class="botao botao--claro" id="up-go" disabled>Enviar</button>
      </div>`);
    const zone = m.caixa.querySelector("#up-zone");
    const input = m.caixa.querySelector("#up-file");
    const nome = m.caixa.querySelector("#up-nome");
    const go = m.caixa.querySelector("#up-go");
    let file = null;
    m.caixa.querySelector("[data-x]").onclick = m.fechar;
    zone.addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      file = input.files && input.files[0];
      nome.textContent = file ? file.name + " (" + Math.round(file.size/1024) + " KB)" : "";
      go.disabled = !file;
    });
    ["dragenter","dragover"].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add("is-over"); }));
    ["dragleave","drop"].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.remove("is-over"); }));
    zone.addEventListener("drop", e => {
      file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) {
        nome.textContent = file.name + " (" + Math.round(file.size/1024) + " KB)";
        go.disabled = false;
      }
    });
    go.addEventListener("click", async () => {
      if (!file) return;
      go.disabled = true;
      go.textContent = "Enviando…";
      try {
        const fd = new FormData();
        fd.append("peer", peer());
        fd.append("arquivo", file, file.name);
        const r = await fetch("/plugins/midia-tc506/api/upload", {method:"POST", body: fd});
        const c = await r.json();
        if (!c.ok) throw new Error(c.detail||"Falha");
        aviso("Enviado: " + (c.path||file.name));
        m.fechar();
        listar();
      } catch(e) {
        aviso(e.message, true);
        go.disabled = false;
        go.textContent = "Enviar";
      }
    });
  }

  function renderArquivos(){
    const box = $("lista-arquivos");
    if (!arquivos.length){ box.innerHTML = '<p class="meta-img" style="padding:.6rem">Vazio</p>'; return; }
    box.innerHTML = arquivos.map(a =>
      `<div class="midia-item"><span title="${esc(a.path)}">${esc(a.path)}</span>
      <span class="midia-acoes-item">
        <button type="button" class="botao botao--fantasma botao--mini" data-view="${esc(a.path)}">Visualizar</button>
        <a class="botao botao--fantasma botao--mini" href="${urlBaixar(a.path)}" download>Baixar</a>
        <button type="button" class="botao botao--fantasma botao--mini" data-del="${esc(a.path)}">Apagar</button>
      </span></div>`
    ).join("");
    box.querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () => visualizar(b.dataset.view)));
    box.querySelectorAll("[data-del]").forEach(b => b.addEventListener("click", async () => {
      if (!confirm("Apagar "+b.dataset.del+"?")) return;
      try {
        const r = await json("/plugins/midia-tc506/api/apagar", {
          method:"POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({peer: peer(), path: b.dataset.del})
        });
        if (!r.ok) throw new Error(r.detail||"Falha");
        aviso("Apagado."); listar();
      } catch(e){ aviso(e.message, true); }
    }));
  }

  function renderSeq(){
    const box = $("lista-seq");
    const opts = arquivos.map(a => `<option value="${esc(a.path)}">${esc(a.path)}</option>`).join("");
    box.innerHTML = seq.map((s,i) =>
      `<div class="seq-item" data-i="${i}">
        <select class="seq-path">${opts}<option value="${esc(s.path||s.caminho||"")}" selected>${esc(s.path||s.caminho||"")}</option></select>
        <input type="number" class="seq-tempo" min="1" value="${s.tempo||5}" title="segundos">
        <input type="number" class="seq-loops" min="1" value="${s.loops||s.vezes||1}" title="loops">
        <button type="button" class="botao botao--fantasma botao--mini seq-rm">×</button>
      </div>`
    ).join("") || '<p class="meta-img">Sequência vazia</p>';
    box.querySelectorAll(".seq-rm").forEach(b => b.addEventListener("click", () => {
      seq.splice(+b.closest(".seq-item").dataset.i, 1); renderSeq();
    }));
  }
  function coletarSeq(){
    const items = [];
    document.querySelectorAll("#lista-seq .seq-item").forEach(el => {
      const path = el.querySelector(".seq-path").value;
      if (path) items.push({
        path,
        tempo: +el.querySelector(".seq-tempo").value||5,
        loops: +el.querySelector(".seq-loops").value||1
      });
    });
    return items;
  }

  $("btn-peers").addEventListener("click", async () => { await carregarPeers(); await listar(); });
  $("peer").addEventListener("change", listar);
  $("btn-abrir-upload").addEventListener("click", abrirUpload);
  $("btn-add-seq").addEventListener("click", () => {
    seq.push({path: (arquivos[0]&&arquivos[0].path)||"INT_MEM/bmp1.bmp", tempo:5, loops:1});
    renderSeq();
  });
  $("btn-salvar-seq").addEventListener("click", async () => {
    try {
      const r = await json("/plugins/midia-tc506/api/sequencia", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({peer: peer(), itens: coletarSeq()})
      });
      if (!r.ok) throw new Error(r.detail||"Falha");
      aviso("Sequência salva."); listar();
    } catch(e){ aviso(e.message, true); }
  });

  carregarPeers().then(listar);
})();


