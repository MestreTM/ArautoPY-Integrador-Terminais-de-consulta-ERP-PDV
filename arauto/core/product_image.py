"""Imagens de produto: cache local (EAN) + fallback HTTP + pacote GitHub.
"""

from __future__ import annotations

import io
import json
import logging
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import quote

from .settings import APP_DIR, get_settings

log = logging.getLogger("arauto.product_image")

IMG_TIMEOUT_S = 3.0
SC501_IMG_MAX_BYTES = 45 * 1024

# Repositório oficial do pacote (mesmo do ArautoPY).
# Não precisa republicar o ZIP em todo release do programa: o sistema
# resolve o *último* release que tiver o asset ``prod_ean_imagens.zip``.
GITHUB_REPO_IMAGENS = "MestreTM/ArautoPY-Integrador-Terminais-de-consulta-ERP-PDV"
PACOTE_ASSET_NOME = "prod_ean_imagens.zip"
# Fallback se a API do GitHub falhar (release histórico conhecido)
PACOTE_URL_PADRAO = (
    f"https://github.com/{GITHUB_REPO_IMAGENS}/releases/download/v1.0.0/{PACOTE_ASSET_NOME}"
)

IMAGENS_DIR = APP_DIR / "imagens"
ESTADO_ARQUIVO = IMAGENS_DIR / "pacote_status.json"

_CACHE: dict[str, bytes] = {}
_CACHE_MAX = 128
_CACHE_LOCK = threading.Lock()
_DOWNLOAD_LOCK = threading.Lock()
_download_status: dict[str, object] = {
    "em_andamento": False,
    "ultimo_erro": None,
    "ultimo_ok": None,
    "arquivos": 0,
    "fase": "idle",
    "progresso": 0,
    "mensagem": "",
    "bytes_baixados": 0,
    "bytes_total": 0,
    "arquivos_extraidos": 0,
    "arquivos_total": 0,
}


def ean13(codigo: str) -> str:
    digitos = "".join(c for c in (codigo or "") if c.isdigit())
    if not digitos:
        return ""
    if len(digitos) > 13:
        digitos = digitos[-13:]
    return digitos.zfill(13)


def caminho_imagem_local(codigo: str) -> Path | None:
    ean = ean13(codigo)
    if not ean:
        return None
    return IMAGENS_DIR / f"{ean}.jpg"


def garantir_pasta_imagens() -> Path:
    IMAGENS_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGENS_DIR


def time_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now().isoformat(timespec="seconds")


def _ler_estado() -> dict:
    garantir_pasta_imagens()
    padrao = {
        "baixado": False,
        "nunca_rodou": True,
        "ultimo_ok": None,
        "ultimo_erro": None,
        "arquivos": 0,
    }
    if not ESTADO_ARQUIVO.is_file():
        return padrao
    try:
        dados = json.loads(ESTADO_ARQUIVO.read_text(encoding="utf-8"))
        padrao.update({k: dados.get(k, padrao[k]) for k in padrao})
        return padrao
    except Exception:
        return padrao


def _gravar_estado(dados: dict) -> None:
    garantir_pasta_imagens()
    atual = _ler_estado()
    atual.update(dados)
    ESTADO_ARQUIVO.write_text(
        json.dumps(atual, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def url_imagem_produto(codigo: str) -> str | None:
    settings = get_settings()
    if not settings.get_bool("SHOW_PRODUCT_IMAGE", False):
        return None
    template = (settings.get("PRODUCT_IMAGE_URL") or "").strip()
    if not template:
        return None
    bruto = "".join(c for c in (codigo or "") if c.isdigit()) or (codigo or "")
    ean = ean13(codigo) or bruto
    for chave, valor in (
        ("{barcode}", ean),
        ("{codigo}", bruto),
        ("{gtin}", ean),
        ("{ean}", ean),
    ):
        template = template.replace(chave, quote(valor, safe=""))
    return template


def baixar_bytes(url: str, timeout: float = IMG_TIMEOUT_S) -> bytes | None:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ArautoPY/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(4 * 1024 * 1024)
            return data or None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        log.warning("Falha ao baixar imagem %s: %s", url, exc)
        return None
    except Exception:
        log.exception("Erro inesperado ao baixar imagem %s", url)
        return None


def imagem_rgb_fundo(
    img,
    fundo: tuple[int, int, int] = (255, 255, 255),
):
    """Converte para RGB composando transparência (PNG/LA/P) sobre fundo sólido.

    Sem isso, ``convert("RGB")`` do Pillow pinta alpha de preto — PNG de produto
    sem fundo ficava com fundo preto no cache e nos terminais.
    """
    from PIL import Image

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in getattr(img, "info", {})):
        rgba = img.convert("RGBA")
        base = Image.new("RGBA", rgba.size, (*fundo, 255))
        return Image.alpha_composite(base, rgba).convert("RGB")
    return img.convert("RGB")


def _jpeg_metade_qualidade(dados: bytes) -> bytes | None:
    try:
        from PIL import Image
    except ImportError:
        return dados if dados[:2] == b"\xff\xd8" else None
    try:
        img = Image.open(io.BytesIO(dados))
        img = imagem_rgb_fundo(img, (255, 255, 255))
        img.thumbnail((480, 480), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=50, optimize=True)
        return buf.getvalue()
    except Exception:
        log.exception("Falha ao recomprimir imagem para cache local")
        return None


def salvar_cache_local(codigo: str, dados: bytes) -> Path | None:
    caminho = caminho_imagem_local(codigo)
    if not caminho:
        return None
    garantir_pasta_imagens()
    jpeg = _jpeg_metade_qualidade(dados)
    if not jpeg:
        return None
    try:
        caminho.write_bytes(jpeg)
        log.info("Imagem local salva %s (%d bytes)", caminho.name, len(jpeg))
        return caminho
    except OSError:
        log.exception("Não foi possível gravar %s", caminho)
        return None


def ler_imagem_local(codigo: str) -> bytes | None:
    caminho = caminho_imagem_local(codigo)
    if not caminho or not caminho.is_file():
        return None
    try:
        data = caminho.read_bytes()
        return data or None
    except OSError:
        return None


def obter_bytes_produto(codigo: str) -> bytes | None:
    """Bytes da imagem: local primeiro, depois fallback remoto (+ grava local)."""
    settings = get_settings()
    if not settings.get_bool("SHOW_PRODUCT_IMAGE", False):
        return None

    chave = f"raw|{ean13(codigo) or codigo}"
    with _CACHE_LOCK:
        if chave in _CACHE:
            return _CACHE[chave]

    local = ler_imagem_local(codigo)
    if local:
        with _CACHE_LOCK:
            if len(_CACHE) >= _CACHE_MAX:
                _CACHE.pop(next(iter(_CACHE)), None)
            _CACHE[chave] = local
        return local

    url = url_imagem_produto(codigo)
    if not url:
        return None

    bruto = baixar_bytes(url)
    if not bruto:
        return None

    salvo = salvar_cache_local(codigo, bruto)
    resultado = salvo.read_bytes() if salvo and salvo.is_file() else bruto

    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)), None)
        _CACHE[chave] = resultado
    return resultado


def jpeg_para_sc501(
    dados: bytes,
    *,
    max_bytes: int = SC501_IMG_MAX_BYTES,
    max_lado: int = 320,
) -> bytes | None:
    try:
        from PIL import Image
    except ImportError:
        log.warning("Pillow não instalado — #img no SC501 indisponível")
        return None
    try:
        img = Image.open(io.BytesIO(dados))
        img = imagem_rgb_fundo(img, (255, 255, 255))
        img.thumbnail((max_lado, max_lado), Image.Resampling.LANCZOS)
        for qualidade in (85, 75, 65, 55, 45, 35, 25):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=qualidade, optimize=True)
            out = buf.getvalue()
            if len(out) <= max_bytes:
                return out
        for lado in (240, 200, 160, 120):
            menor = img.copy()
            menor.thumbnail((lado, lado), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            menor.save(buf, format="JPEG", quality=40, optimize=True)
            out = buf.getvalue()
            if len(out) <= max_bytes:
                return out
        return None
    except Exception:
        log.exception("Falha ao preparar JPEG para SC501")
        return None


def obter_jpeg_produto(codigo: str) -> bytes | None:
    bruto = obter_bytes_produto(codigo)
    if not bruto:
        return None
    jpeg = jpeg_para_sc501(bruto)
    if not jpeg:
        return None
    log.info("JPEG produto %s: %d bytes", codigo, len(jpeg))
    return jpeg


def montar_comando_img_sc501(
    jpeg: bytes,
    *,
    indice: str = "00",
    loops: str = "01",
    tempo_s: int = 12,
) -> bytes:
    tempo_hex = f"{max(0, min(255, tempo_s)):02X}"
    tamanho_hex = f"{len(jpeg):06X}"
    cabecalho = (
        b"#img"
        + indice.encode("ascii")
        + loops.encode("ascii")
        + tempo_hex.encode("ascii")
        + tamanho_hex.encode("ascii")
        + b"0000"
        + bytes([0x17])
    )
    return cabecalho + jpeg



def _url_pacote_github_recente() -> str | None:
    """Último asset ``prod_ean_imagens.zip`` entre os releases do repositório.

    Percorre releases (mais recentes primeiro) e devolve a URL do primeiro
    que contiver o ZIP. Assim o pack de imagens só precisa ser anexado quando
    *ele* mudar — não em todo release do ArautoPY.
    """
    import json
    import urllib.request

    api = f"https://api.github.com/repos/{GITHUB_REPO_IMAGENS}/releases?per_page=30"
    req = urllib.request.Request(
        api,
        headers={
            "User-Agent": "ArautoPY/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            releases = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log.debug("Não foi possível listar releases de imagens: %s", exc)
        return None
    if not isinstance(releases, list):
        return None
    alvo = PACOTE_ASSET_NOME.lower()
    for rel in releases:
        if not isinstance(rel, dict):
            continue
        for asset in rel.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            nome = str(asset.get("name") or "")
            if nome.lower() == alvo:
                url = str(asset.get("browser_download_url") or "").strip()
                if url:
                    tag = rel.get("tag_name") or "?"
                    log.info("Pacote de imagens: %s (release %s)", nome, tag)
                    return url
    return None


def url_pacote_efetiva(url: str | None = None) -> str:
    """URL a usar no download.

    Prioridade:
      1. ``url`` explícita (chamada externa) / ``PRODUCT_IMAGE_PACK_URL`` manual
      2. Último ``prod_ean_imagens.zip`` via API de releases
      3. URL pública ``/releases/latest/download/prod_ean_imagens.zip``
      4. Fallback fixo na tag ``v1.0.0``
    """
    settings = get_settings()
    cfg = (url if url is not None else settings.get("PRODUCT_IMAGE_PACK_URL") or "").strip()
    auto_markers = (
        "Prod-EAN-Imagens",
        f"{GITHUB_REPO_IMAGENS}/releases/download/",
        f"{GITHUB_REPO_IMAGENS}/releases/latest/download/",
    )
    if cfg and not any(m in cfg for m in auto_markers):
        return cfg
    recente = _url_pacote_github_recente()
    if recente:
        return recente
    # Sem API (rate limit etc.): GitHub resolve a tag "latest" sozinho
    latest = (
        f"https://github.com/{GITHUB_REPO_IMAGENS}/releases/latest/download/"
        f"{PACOTE_ASSET_NOME}"
    )
    return latest



def status_pacote() -> dict:
    garantir_pasta_imagens()
    qtd = sum(1 for p in IMAGENS_DIR.glob("*.jpg") if p.is_file())
    estado = _ler_estado()
    with _DOWNLOAD_LOCK:
        st = dict(_download_status)
    st.update(estado)
    st["pasta"] = str(IMAGENS_DIR)
    st["arquivos_locais"] = qtd
    em_andamento = bool(st.get("em_andamento"))
    st["pedir_download"] = (
        not em_andamento
        and not estado.get("baixado")
        and (estado.get("nunca_rodou", True) or bool(estado.get("ultimo_erro")))
    )
    try:
        st["url_pacote"] = url_pacote_efetiva()
    except Exception:
        st["url_pacote"] = (
            get_settings().get("PRODUCT_IMAGE_PACK_URL") or PACOTE_URL_PADRAO
        ).strip()
    return st


def baixar_pacote_imagens(url: str | None = None) -> dict:
    """Baixa o ZIP e extrai *.jpg; sobrescreve só os EAN presentes no pacote."""
    settings = get_settings()
    url = url_pacote_efetiva(url)
    with _DOWNLOAD_LOCK:
        if _download_status["em_andamento"]:
            return {"ok": False, "detail": "Download já em andamento.", **status_pacote()}
        _download_status.update({
            "em_andamento": True,
            "ultimo_erro": None,
            "fase": "baixando",
            "progresso": 0,
            "mensagem": "Conectando…",
            "bytes_baixados": 0,
            "bytes_total": 0,
            "arquivos_extraidos": 0,
            "arquivos_total": 0,
        })
    try:
        _gravar_estado({"nunca_rodou": False, "ultimo_erro": None})
    except Exception:
        pass

    try:
        garantir_pasta_imagens()
        log.info("Baixando pacote de imagens: %s", url)
        req = urllib.request.Request(url, headers={"User-Agent": "ArautoPY/1.0"})
        try:
            resp_ctx = urllib.request.urlopen(req, timeout=180)
        except urllib.error.HTTPError as http_exc:
            if http_exc.code == 404 and "/latest/download/" not in url:
                alt = (
                    f"https://github.com/{GITHUB_REPO_IMAGENS}/releases/latest/download/"
                    f"{PACOTE_ASSET_NOME}"
                )
                log.warning("404 em %s — tentando %s", url, alt)
                url = alt
                req = urllib.request.Request(url, headers={"User-Agent": "ArautoPY/1.0"})
                resp_ctx = urllib.request.urlopen(req, timeout=180)
            else:
                raise
        with resp_ctx as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            with _DOWNLOAD_LOCK:
                _download_status["bytes_total"] = total
                _download_status["mensagem"] = "Baixando pacote ZIP…"
            chunks: list[bytes] = []
            lidos = 0
            while True:
                bloco = resp.read(64 * 1024)
                if not bloco:
                    break
                chunks.append(bloco)
                lidos += len(bloco)
                pct = int(lidos * 55 / total) if total else min(50, 5 + lidos // (512 * 1024))
                with _DOWNLOAD_LOCK:
                    _download_status["bytes_baixados"] = lidos
                    _download_status["progresso"] = min(55, pct)
                    _download_status["mensagem"] = (
                        f"Baixando… {lidos // 1024} KB"
                        + (f" / {total // 1024} KB" if total else "")
                    )
            zip_bytes = b"".join(chunks)
        if not zip_bytes:
            raise RuntimeError("ZIP vazio")

        with _DOWNLOAD_LOCK:
            _download_status["fase"] = "extraindo"
            _download_status["progresso"] = 60
            _download_status["mensagem"] = "Extraindo imagens…"

        extraiu = 0
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            membros = [
                info for info in zf.infolist()
                if not info.is_dir()
                and Path(info.filename).name.lower().endswith((".jpg", ".jpeg"))
            ]
            total_arq = len(membros)
            with _DOWNLOAD_LOCK:
                _download_status["arquivos_total"] = total_arq
            for i, info in enumerate(membros):
                nome = Path(info.filename).name
                base = Path(nome).stem
                digitos = "".join(c for c in base if c.isdigit())
                if not digitos:
                    continue
                ean = digitos[-13:].zfill(13) if len(digitos) >= 8 else digitos.zfill(13)
                destino = IMAGENS_DIR / f"{ean}.jpg"
                data = zf.read(info)
                jpeg = _jpeg_metade_qualidade(data) or data
                destino.write_bytes(jpeg)
                extraiu += 1
                pct = 60 + int((i + 1) * 40 / max(1, total_arq))
                with _DOWNLOAD_LOCK:
                    _download_status["arquivos_extraidos"] = extraiu
                    _download_status["progresso"] = min(99, pct)
                    _download_status["mensagem"] = f"Extraindo… {extraiu}/{total_arq}"

        ok_em = time_iso()
        with _DOWNLOAD_LOCK:
            _download_status.update({
                "em_andamento": False,
                "ultimo_ok": ok_em,
                "ultimo_erro": None,
                "arquivos": extraiu,
                "fase": "concluido",
                "progresso": 100,
                "mensagem": f"Concluído: {extraiu} imagens",
            })
        _gravar_estado({
            "baixado": True,
            "nunca_rodou": False,
            "ultimo_ok": ok_em,
            "ultimo_erro": None,
            "arquivos": extraiu,
        })
        log.info("Pacote de imagens: %d arquivos em %s", extraiu, IMAGENS_DIR)
        return {"ok": True, "arquivos": extraiu, "pasta": str(IMAGENS_DIR), **status_pacote()}
    except Exception as exc:
        log.exception("Falha ao baixar pacote de imagens")
        with _DOWNLOAD_LOCK:
            _download_status.update({
                "em_andamento": False,
                "ultimo_erro": str(exc),
                "fase": "erro",
                "progresso": 0,
                "mensagem": str(exc),
            })
        _gravar_estado({
            "baixado": False,
            "nunca_rodou": False,
            "ultimo_erro": str(exc),
        })
        return {"ok": False, "detail": str(exc), **status_pacote()}


def baixar_pacote_em_background(url: str | None = None) -> None:
    def _run() -> None:
        baixar_pacote_imagens(url)

    threading.Thread(target=_run, name="img-pack", daemon=True).start()


def limpar_banco_imagens() -> dict:
    garantir_pasta_imagens()
    apagados = 0
    for f in list(IMAGENS_DIR.glob("*.jpg")) + list(IMAGENS_DIR.glob("*.jpeg")):
        try:
            f.unlink()
            apagados += 1
        except OSError:
            log.exception("Falha ao apagar %s", f)
    with _CACHE_LOCK:
        _CACHE.clear()
    _gravar_estado({
        "baixado": False,
        "nunca_rodou": True,
        "ultimo_ok": None,
        "ultimo_erro": None,
        "arquivos": 0,
    })
    log.info("Banco de imagens limpo: %d arquivos removidos", apagados)
    return {"ok": True, "apagados": apagados, **status_pacote()}


def apagar_imagem_ean(codigo: str) -> dict:
    caminho = caminho_imagem_local(codigo)
    if not caminho:
        return {"ok": False, "detail": "Código inválido."}
    ean = caminho.stem
    if not caminho.is_file():
        return {"ok": False, "detail": f"Não há imagem local para {ean}.", "ean": ean}
    try:
        caminho.unlink()
    except OSError as exc:
        return {"ok": False, "detail": str(exc), "ean": ean}
    with _CACHE_LOCK:
        for k in list(_CACHE.keys()):
            if ean in k or (codigo or "") in k:
                _CACHE.pop(k, None)
    log.info("Imagem local removida: %s", caminho.name)
    return {"ok": True, "ean": ean, "arquivo": caminho.name, **status_pacote()}
