"""Plugin: Gerador de Cartaz (A4/A2/personalizado) com editor de camadas.

- Dados do produto vêm do QueryService / repositório ativo
- Imagem do produto: sempre Bluesoft Cosmos (qualidade cheia)
- Templates em JSON sob APP_DIR/folhas_promocionais/
- Exportação PNG e PDF (Pillow)
"""

from __future__ import annotations

import io
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import Body, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse

log = logging.getLogger("arauto.plugin.folhas")
_DIR = Path(__file__).resolve().parent

# Tamanhos em milímetros (largura × altura, retrato)
PAPEIS = {
    "A4": {"largura_mm": 210.0, "altura_mm": 297.0, "rotulo": "A4 (210×297 mm)"},
    "A2": {"largura_mm": 420.0, "altura_mm": 594.0, "rotulo": "A2 (420×594 mm)"},
    "A3": {"largura_mm": 297.0, "altura_mm": 420.0, "rotulo": "A3 (297×420 mm)"},
    "A5": {"largura_mm": 148.0, "altura_mm": 210.0, "rotulo": "A5 (148×210 mm)"},
    "custom": {"largura_mm": 210.0, "altura_mm": 297.0, "rotulo": "Personalizado"},
}


def _sem_acentos(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _tokens_busca(texto: str) -> list[str]:
    """Palavras alfanuméricas sem acento (ignora pontuação: KG., etc.)."""
    s = _sem_acentos(texto)
    return [t for t in re.split(r"[^a-z0-9]+", s) if t]


def _parece_venda_peso(barcode: str, description: str) -> bool:
    """Heurística: PLU/balança costuma ter código curto ou descrição com kg."""
    bc = (barcode or "").strip()
    dig = "".join(c for c in bc if c.isdigit())
    # EAN/UPC clássicos
    if len(dig) in (8, 12, 13, 14) and dig == bc.replace(" ", ""):
        # ainda pode ser peso se a descrição indicar
        pass
    elif dig and len(dig) <= 7:
        return True
    elif bc and len(bc) <= 7:
        return True
    desc = _sem_acentos(description or "")
    for token in (" kg", "kg ", "quilo", "balanca", "/kg", "por kg", "p/kg"):
        if token in f" {desc} ":
            return True
    if desc.endswith(" kg") or desc.endswith("/kg"):
        return True
    return False


def _produto_resumo(p) -> dict:
    if hasattr(p, "to_dict"):
        d = p.to_dict()
    else:
        d = {
            "barcode": getattr(p, "barcode", ""),
            "description": getattr(p, "description", ""),
            "price_1": getattr(p, "price1", None),
            "price_2": getattr(p, "price2", None),
        }
    barcode = d.get("barcode") or d.get("codigo_barras") or ""
    description = d.get("description") or d.get("descricao") or ""
    price_1 = d.get("price_1") if d.get("price_1") is not None else d.get("preco1")
    price_2 = d.get("price_2") if d.get("price_2") is not None else d.get("preco2")
    return {
        "barcode": barcode,
        "description": description,
        "price_1": price_1,
        "price_2": price_2,
        "venda_peso": _parece_venda_peso(str(barcode), str(description)),
    }


COSMOS_URL = "https://cdn-cosmos.bluesoft.com.br/products/{barcode}"
DPI_EXPORT = 150
_ID_SEGURO = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _page() -> str:
    return (_DIR / "page.html").read_text(encoding="utf-8")


def _pasta_templates() -> Path:
    from arauto.core.settings import APP_DIR
    p = APP_DIR / "folhas_promocionais"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _pasta_midia() -> Path:
    p = _pasta_templates() / "midia"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _template_path(tid: str) -> Path | None:
    if not _ID_SEGURO.match(tid or ""):
        return None
    return _pasta_templates() / f"{tid}.json"


def _service(ctx):
    return ctx.service


def _produto_dict(service, codigo: str) -> dict:
    codigo = (codigo or "").strip()
    if not codigo:
        return {"ok": False, "detail": "Código vazio."}
    try:
        if hasattr(service, "query"):
            r = service.query(codigo, channel="plugin_folhas")
            d_raw = r.to_dict() if hasattr(r, "to_dict") else {}
            if not getattr(r, "found", False) and not d_raw.get("encontrado"):
                return {
                    "ok": False,
                    "detail": d_raw.get("mensagem") or f"Produto {codigo} não encontrado.",
                    "codigo": codigo,
                }
            d = {
                "barcode": d_raw.get("codigo_barras") or getattr(r, "barcode", codigo),
                "description": d_raw.get("descricao") or getattr(r, "description", "") or "",
                "price_1": d_raw.get("preco1") if d_raw.get("preco1") is not None else getattr(r, "price1", None),
                "price_2": d_raw.get("preco2") if d_raw.get("preco2") is not None else getattr(r, "price2", None),
                "label1": d_raw.get("rotulo1"),
                "label2": d_raw.get("rotulo2"),
                "by_weight": bool(getattr(r, "by_weight", False)),
            }
            d["venda_peso"] = bool(d["by_weight"]) or _parece_venda_peso(str(d["barcode"]), str(d["description"]))
            return {"ok": True, "produto": d, "codigo": codigo}
        repo = getattr(service, "repo", None)
        if repo and hasattr(repo, "get"):
            prod = repo.get(codigo)
            if not prod and hasattr(service, "buscar_candidatos"):
                prod = service.buscar_candidatos([codigo])
            if not prod:
                return {"ok": False, "detail": f"Produto {codigo} não encontrado.", "codigo": codigo}
            if hasattr(prod, "to_dict"):
                raw = prod.to_dict()
            else:
                raw = {
                    "barcode": getattr(prod, "barcode", codigo),
                    "description": getattr(prod, "description", ""),
                    "price_1": getattr(prod, "price1", None),
                    "price_2": getattr(prod, "price2", None),
                }
            d = {
                "barcode": raw.get("barcode") or raw.get("codigo_barras") or codigo,
                "description": raw.get("description") or raw.get("descricao") or "",
                "price_1": raw.get("price_1") if raw.get("price_1") is not None else raw.get("preco1"),
                "price_2": raw.get("price_2") if raw.get("price_2") is not None else raw.get("preco2"),
            }
            return {"ok": True, "produto": d, "codigo": codigo}
    except Exception as exc:
        log.exception("consulta produto")
        return {"ok": False, "detail": str(exc), "codigo": codigo}
    return {"ok": False, "detail": "Serviço de consulta indisponível.", "codigo": codigo}


def _cosmos_bytes(ean: str) -> bytes | None:
    """Sempre Cosmos — não usa cache local de qualidade reduzida."""
    from arauto.core.product_image import baixar_bytes, ean13

    code = ean13(ean) or "".join(c for c in (ean or "") if c.isdigit())
    if not code:
        return None
    # Cosmos aceita EAN sem zfill em vários casos; tenta 13 dígitos e o original
    candidatos = []
    if len(code) == 13:
        candidatos.append(code)
        candidatos.append(code.lstrip("0") or code)
    else:
        candidatos.append(code)
        candidatos.append(code.zfill(13))
    seen = set()
    for c in candidatos:
        if c in seen:
            continue
        seen.add(c)
        url = COSMOS_URL.format(barcode=c)
        data = baixar_bytes(url, timeout=8.0)
        if data and len(data) > 100:
            return data
    return None


def _mm_to_px(mm: float, dpi: int = DPI_EXPORT, *, minimo: int | None = 1) -> int:
    """Converte mm → pixels. ``minimo=None`` permite valores negativos (posição)."""
    v = int(round(float(mm) / 25.4 * dpi))
    if minimo is None:
        return v
    return max(minimo, v)


def _hex_rgb(cor: str, default=(0, 0, 0)) -> tuple[int, int, int]:
    cor = (cor or "").strip().lstrip("#")
    if len(cor) == 3:
        cor = "".join(c * 2 for c in cor)
    if len(cor) != 6:
        return default
    try:
        return int(cor[0:2], 16), int(cor[2:4], 16), int(cor[4:6], 16)
    except ValueError:
        return default


def _parse_preco_num(val) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    s = s.replace("R$", "").replace("r$", "").strip()
    try:
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except (TypeError, ValueError):
        return None


def _fmt_preco_br(n: float) -> str:
    return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _valor_campo(produto: dict, campo: str) -> str:
    if not produto:
        return ""
    mapa = {
        "barcode": ("barcode", "codigo", "ean", "gtin"),
        "description": ("description", "descricao", "nome", "name"),
        "price_1": ("price_1", "preco1", "price", "preco"),
        "price_2": ("price_2", "preco2"),
        "price_1_fmt": ("price_1", "preco1", "price"),
        "price_2_fmt": ("price_2", "preco2"),
    }
    chaves = mapa.get(campo, (campo,))
    val = None
    for k in chaves:
        if k in produto and produto[k] is not None and str(produto[k]).strip() != "":
            val = produto[k]
            break
    if val is None:
        return ""
    if campo.endswith("_fmt") or campo in ("price_1", "price_2"):
        n = _parse_preco_num(val)
        if n is None:
            return str(val)
        venda_peso = bool(produto.get("venda_peso") or produto.get("by_weight"))
        modo = (produto.get("preco_modo") or "kg").lower()
        sufixo = ""
        if venda_peso:
            if modo in ("100g", "100", "g", "grama", "gramas"):
                n = n / 10.0
                sufixo = "\n(100g)"
            else:
                sufixo = "\nO kilo"
        return _fmt_preco_br(n) + sufixo
    return str(val)


def _render_pil(template: dict, produto: dict, imagem: bytes | None, dpi: int = DPI_EXPORT):
    from PIL import Image, ImageDraw, ImageFont

    papel = template.get("papel") or {}
    w_mm = float(papel.get("largura_mm") or 210)
    h_mm = float(papel.get("altura_mm") or 297)
    W, H = _mm_to_px(w_mm, dpi), _mm_to_px(h_mm, dpi)
    fundo = _hex_rgb(template.get("cor_fundo") or "#ffffff", (255, 255, 255))
    img = Image.new("RGB", (W, H), fundo)
    draw = ImageDraw.Draw(img)

    def font_for(size_mm: float, bold: bool = False):
        px = max(8, _mm_to_px(size_mm, dpi))
        candidatos = [
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        for path in candidatos:
            if Path(path).is_file():
                try:
                    return ImageFont.truetype(path, px)
                except OSError:
                    continue
        return ImageFont.load_default()

    camadas = sorted(template.get("camadas") or [], key=lambda c: int(c.get("z") or 0))
    for cam in camadas:
        if cam.get("visivel") is False:
            continue
        tipo = (cam.get("tipo") or "").lower()
        x = _mm_to_px(float(cam.get("x_mm") or 0), dpi, minimo=None)
        y = _mm_to_px(float(cam.get("y_mm") or 0), dpi, minimo=None)
        w = _mm_to_px(float(cam.get("largura_mm") or 10), dpi)
        h = _mm_to_px(float(cam.get("altura_mm") or 10), dpi)

        if tipo == "rect":
            cor_f = (cam.get("cor_fundo") or "#eeeeee")
            cor_b = (cam.get("cor_borda") or "#000000")
            fill = None if cor_f == "transparent" else _hex_rgb(cor_f, (238, 238, 238))
            outline = None if cor_b == "transparent" else _hex_rgb(cor_b, (0, 0, 0))
            bw = max(0, int(cam.get("borda_px") or 0))
            if fill is not None or outline is not None:
                draw.rectangle(
                    [x, y, x + w, y + h],
                    fill=fill,
                    outline=outline if (bw or outline) else None,
                    width=bw or 1,
                )
        elif tipo in ("text", "text_field"):
            if tipo == "text_field":
                texto = _valor_campo(produto, cam.get("campo") or "description")
            else:
                texto = str(cam.get("texto") or "")
            if not texto:
                continue
            if (cam.get("cor") or "") == "transparent":
                continue
            cor = _hex_rgb(cam.get("cor") or "#000000")
            size_mm = float(cam.get("fonte_mm") or 5)
            bold = bool(cam.get("negrito"))
            font = font_for(size_mm, bold)
            # quebra simples por largura
            max_w = w if w > 10 else W - x
            linhas: list[str] = []
            for paragrafo in texto.split("\n"):
                palavras = paragrafo.split(" ")
                atual = ""
                for p in palavras:
                    teste = (atual + " " + p).strip()
                    bbox = draw.textbbox((0, 0), teste, font=font)
                    if bbox[2] - bbox[0] <= max_w or not atual:
                        atual = teste
                    else:
                        linhas.append(atual)
                        atual = p
                if atual:
                    linhas.append(atual)
            line_h = int(font.size * 1.25) if hasattr(font, "size") else 16
            cy = y
            align = (cam.get("align") or "left").lower()
            font_unid = None
            for ln in linhas:
                eh_unid = ln.strip() in ("O kilo", "(100g)")
                f = font
                if eh_unid:
                    if font_unid is None:
                        font_unid = font_for(max(1.6, size_mm * 0.22), True)
                    f = font_unid
                bbox = draw.textbbox((0, 0), ln, font=f)
                tw = bbox[2] - bbox[0]
                if align == "center":
                    tx = x + max(0, (w - tw) // 2)
                elif align == "right":
                    tx = x + max(0, w - tw)
                else:
                    tx = x
                draw.text((tx, cy), ln, fill=cor, font=f)
                cy += int((f.size * 1.15) if eh_unid and hasattr(f, "size") else line_h)
                if cy > y + h + line_h:
                    break
        elif tipo in ("image_product", "image_custom"):
            raw = None
            if tipo == "image_custom":
                src = (cam.get("src") or "").strip().replace("\\", "/")
                if src.startswith("data:"):
                    try:
                        import base64
                        b64 = src.split(",", 1)[-1]
                        raw = base64.b64decode(b64)
                    except Exception:
                        raw = None
                elif "/api/midia/" in src or src.startswith("midia/"):
                    nome = src.rsplit("/", 1)[-1]
                    mid = _pasta_midia() / nome
                    if mid.is_file():
                        raw = mid.read_bytes()
                elif src.startswith("http://") or src.startswith("https://"):
                    from arauto.core.product_image import baixar_bytes
                    raw = baixar_bytes(src, timeout=10.0)
            else:
                raw = imagem
            if not raw:
                continue
            try:
                from PIL import Image as PILImage
                im = PILImage.open(io.BytesIO(raw)).convert("RGBA")
                if im.width < 1 or im.height < 1:
                    continue
                fit = (cam.get("object_fit") or "contain").lower()
                # fill_height: preenche a altura da caixa (pode transbordar na largura)
                # fill_width: preenche a largura
                # cover: preenche a caixa cortando o excesso
                # contain: imagem inteira dentro da caixa
                if fit in ("fill_height", "preencher_vertical", "height"):
                    scale = h / im.height
                elif fit in ("fill_width", "preencher_horizontal", "width"):
                    scale = w / im.width
                elif fit == "cover":
                    scale = max(w / im.width, h / im.height)
                else:
                    scale = min(w / im.width, h / im.height)
                nw = max(1, int(round(im.width * scale)))
                nh = max(1, int(round(im.height * scale)))
                im = im.resize((nw, nh), PILImage.Resampling.LANCZOS)
                # centraliza na caixa da camada (igual object-fit no CSS)
                px = int(round(x + (w - nw) / 2))
                py = int(round(y + (h - nh) / 2))
                # recorte explícito (Pillow + coords negativas)
                left = max(0, px)
                top = max(0, py)
                right = min(W, px + nw)
                bottom = min(H, py + nh)
                if right > left and bottom > top:
                    sx0 = left - px
                    sy0 = top - py
                    recorte = im.crop((sx0, sy0, sx0 + (right - left), sy0 + (bottom - top)))
                    if recorte.mode == "RGBA":
                        img.paste(recorte, (left, top), recorte)
                    else:
                        img.paste(recorte.convert("RGB"), (left, top))
            except Exception:
                log.debug("falha ao colar imagem", exc_info=True)
    return img


def _template_padrao() -> dict:
    return {
        "id": "",
        "nome": "Novo template",
        "papel": {"tipo": "A4", "largura_mm": 210, "altura_mm": 297},
        "cor_fundo": "#ffffff",
        "camadas": [
            {
                "id": "fundo-faixa",
                "nome": "Faixa topo",
                "tipo": "rect",
                "x_mm": 0, "y_mm": 0, "largura_mm": 210, "altura_mm": 40,
                "cor_fundo": "#1d6fe0", "cor_borda": "#1d6fe0", "borda_px": 0,
                "z": 0, "visivel": True,
            },
            {
                "id": "titulo",
                "nome": "Título promoção",
                "tipo": "text",
                "texto": "OFERTA",
                "x_mm": 10, "y_mm": 12, "largura_mm": 190, "altura_mm": 20,
                "fonte_mm": 12, "negrito": True, "cor": "#ffffff", "align": "center",
                "z": 1, "visivel": True,
            },
            {
                "id": "img",
                "nome": "Foto produto",
                "tipo": "image_product",
                "x_mm": 45, "y_mm": 55, "largura_mm": 120, "altura_mm": 120,
                "trava_proporcao": True,
                "z": 2, "visivel": True,
            },
            {
                "id": "desc",
                "nome": "Descrição",
                "tipo": "text_field",
                "campo": "description",
                "x_mm": 15, "y_mm": 185, "largura_mm": 180, "altura_mm": 30,
                "fonte_mm": 6, "negrito": True, "cor": "#111111", "align": "center",
                "z": 3, "visivel": True,
            },
            {
                "id": "preco",
                "nome": "Preço",
                "tipo": "text_field",
                "campo": "price_1",
                "x_mm": 15, "y_mm": 225, "largura_mm": 180, "altura_mm": 35,
                "fonte_mm": 16, "negrito": True, "cor": "#c62828", "align": "center",
                "z": 4, "visivel": True,
            },
            {
                "id": "ean",
                "nome": "Código de barras",
                "tipo": "text_field",
                "campo": "barcode",
                "x_mm": 15, "y_mm": 275, "largura_mm": 180, "altura_mm": 12,
                "fonte_mm": 4, "negrito": False, "cor": "#666666", "align": "center",
                "z": 5, "visivel": True,
            },
        ],
    }


def setup(ctx):
    ctx.adicionar_aba("folhas-promocionais", "Gerador de Cartaz", "/plugins/folhas-promocionais/", ordem=55)

    @ctx.app.get("/plugins/folhas-promocionais/", response_class=HTMLResponse)
    def pagina(request: Request):
        scripts = '<script src="/plugins/folhas-promocionais/static/app.js"></script>'
        return ctx.render(
            request,
            titulo="Gerador de Cartaz",
            conteudo=_page(),
            pagina="folhas-promocionais",
            scripts=scripts,
        )

    @ctx.app.get("/plugins/folhas-promocionais/static/app.js")
    def static_js():
        return FileResponse(_DIR / "app.js", media_type="application/javascript")

    @ctx.app.get("/plugins/folhas-promocionais/api/meta")
    def api_meta():
        return {
            "ok": True,
            "papeis": PAPEIS,
            "campos_produto": [
                {"id": "barcode", "rotulo": "Código de barras"},
                {"id": "description", "rotulo": "Descrição"},
                {"id": "price_1", "rotulo": "Preço 1"},
                {"id": "price_2", "rotulo": "Preço 2"},
            ],
            "tipos_camada": [
                {"id": "text", "rotulo": "Texto livre"},
                {"id": "text_field", "rotulo": "Campo do produto"},
                {"id": "image_product", "rotulo": "Imagem Cosmos (EAN)"},
                {"id": "image_custom", "rotulo": "Imagem personalizada"},
                {"id": "rect", "rotulo": "Retângulo"},
            ],
            "template_padrao": _template_padrao(),
            "dpi_export": DPI_EXPORT,
        }


    @ctx.app.get("/plugins/folhas-promocionais/api/buscar")
    def api_buscar(q: str = Query(""), modo: str = Query("desc"), limit: int = Query(40)):
        """Busca produtos por EAN (prefixo/contém) ou descrição (sem acentos)."""
        q = (q or "").strip()
        modo = (modo or "desc").lower()
        limit = max(1, min(int(limit or 40), 80))
        service = _service(ctx)
        repo = getattr(service, "repo", None)
        if not repo:
            return {"ok": False, "detail": "Repositório indisponível.", "itens": []}

        itens = []
        try:
            if modo in ("ean", "barcode", "codigo"):
                # Aceita EAN, código de balança e qualquer código de cadastro
                candidatos = []
                qlimpo = q.strip()
                digitos = "".join(c for c in qlimpo if c.isdigit())
                for c in (qlimpo, digitos, digitos.zfill(13) if digitos else "", digitos.lstrip("0") if digitos else ""):
                    if c and c not in candidatos:
                        candidatos.append(c)
                # Etiqueta de balança comum: 2 + código (ex.: 2001100… → 001100 / 1100)
                if digitos.startswith("2") and len(digitos) >= 5:
                    miolo = digitos[1:]
                    for c in (
                        miolo,
                        miolo[:6].zfill(6),
                        miolo[:5].zfill(5),
                        miolo[:4].zfill(4),
                        miolo.lstrip("0"),
                        miolo[:6],
                        miolo[:5],
                        miolo[:4],
                    ):
                        if c and c not in candidatos:
                            candidatos.append(c)
                    # prefixos zeros à esquerda típicos de PLU
                    for n in (4, 5, 6, 7):
                        if len(digitos) > n:
                            trecho = digitos[1 : 1 + n]
                            for c in (trecho, trecho.zfill(n), trecho.zfill(6)):
                                if c and c not in candidatos:
                                    candidatos.append(c)
                exato = None
                for c in candidatos:
                    exato = repo.get(c)
                    if exato:
                        break
                if not exato and hasattr(service, "buscar_candidatos"):
                    exato = service.buscar_candidatos(candidatos)
                if not exato and hasattr(service, "query"):
                    try:
                        r = service.query(qlimpo, channel="plugin_folhas_busca")
                        if getattr(r, "found", False):
                            return {
                                "ok": True,
                                "exato": True,
                                "itens": [{
                                    "barcode": getattr(r, "barcode", qlimpo) or qlimpo,
                                    "description": getattr(r, "description", "") or "",
                                    "price_1": getattr(r, "price1", None),
                                    "price_2": getattr(r, "price2", None),
                                }],
                            }
                    except Exception:
                        pass
                if exato:
                    return {"ok": True, "exato": True, "itens": [_produto_resumo(exato)]}
                # parcial: código contém o trecho digitado
                termo = digitos or qlimpo
                brutos = repo.search(termo, limit=200, offset=0)
                for p in brutos:
                    bc = (getattr(p, "barcode", None) or "")
                    if termo and termo.lower() not in bc.lower() and termo not in bc:
                        # ainda inclui se search() já filtrou por descrição demais
                        if termo not in (getattr(p, "description", "") or "").lower():
                            if digitos and digitos not in bc:
                                continue
                    itens.append(_produto_resumo(p))
                    if len(itens) >= limit:
                        break
            else:
                # Descrição: tokens sem acento/pontuação ("BATATA DOCE KG." → batata, doce, kg)
                tokens = _tokens_busca(q)
                alvo = _sem_acentos(q)
                vistos: set[str] = set()

                def _casa(p) -> bool:
                    bc = (getattr(p, "barcode", None) or "").strip()
                    desc = getattr(p, "description", "") or ""
                    blob = _sem_acentos(f"{bc} {desc}")
                    if tokens:
                        return all(t in blob for t in tokens)
                    return bool(alvo) and alvo in blob

                # 1) search nativo com a query e com cada token
                brutos = []
                for termo in [q] + tokens:
                    if not termo:
                        continue
                    try:
                        brutos.extend(repo.search(termo, limit=500, offset=0) or [])
                    except Exception:
                        pass

                for p in brutos:
                    bc = (getattr(p, "barcode", None) or "").strip()
                    key = bc or str(id(p))
                    if key in vistos:
                        continue
                    if _casa(p):
                        vistos.add(key)
                        itens.append(_produto_resumo(p))
                        if len(itens) >= limit:
                            break

                # 2) se ainda faltam resultados, percorre a base em páginas
                #    (importante p/ PLU tipo 001100 fora do TOP do LIKE)
                if len(itens) < limit:
                    try:
                        total = int(repo.count() or 0)
                    except Exception:
                        total = 0
                    offset = 0
                    page = 800
                    while offset < max(total, page) and len(itens) < limit:
                        try:
                            batch = list(repo.search("", limit=page, offset=offset) or [])
                        except Exception:
                            break
                        if not batch:
                            break
                        for p in batch:
                            bc = (getattr(p, "barcode", None) or "").strip()
                            key = bc or str(id(p))
                            if key in vistos:
                                continue
                            if _casa(p):
                                vistos.add(key)
                                itens.append(_produto_resumo(p))
                                if len(itens) >= limit:
                                    break
                        if len(batch) < page:
                            break
                        offset += page
        except Exception as exc:
            log.exception("buscar produtos")
            return JSONResponse({"ok": False, "detail": str(exc), "itens": []}, status_code=500)
        return {"ok": True, "exato": False, "itens": itens}

    @ctx.app.get("/plugins/folhas-promocionais/api/produto")
    def api_produto(codigo: str = Query("")):
        return _produto_dict(_service(ctx), codigo)

    @ctx.app.get("/plugins/folhas-promocionais/api/imagem-cosmos")
    def api_imagem_cosmos(codigo: str = Query("")):
        data = _cosmos_bytes(codigo)
        if not data:
            return JSONResponse(
                {"ok": False, "detail": "Imagem não encontrada no Cosmos."},
                status_code=404,
            )
        return Response(content=data, media_type="image/jpeg")

    @ctx.app.get("/plugins/folhas-promocionais/api/templates")
    def api_listar_templates():
        itens = []
        for f in sorted(_pasta_templates().glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                itens.append({
                    "id": d.get("id") or f.stem,
                    "nome": d.get("nome") or f.stem,
                    "papel": (d.get("papel") or {}).get("tipo") or "custom",
                })
            except Exception:
                continue
        return {"ok": True, "templates": itens}

    @ctx.app.get("/plugins/folhas-promocionais/api/templates/{tid}")
    def api_get_template(tid: str):
        path = _template_path(tid)
        if not path or not path.is_file():
            return JSONResponse({"ok": False, "detail": "Template não encontrado."}, status_code=404)
        try:
            return {"ok": True, "template": json.loads(path.read_text(encoding="utf-8"))}
        except Exception as exc:
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=500)

    @ctx.app.post("/plugins/folhas-promocionais/api/templates")
    def api_salvar_template(corpo: dict = Body(...)):
        tpl = corpo.get("template") if isinstance(corpo, dict) else None
        if not isinstance(tpl, dict):
            return JSONResponse({"ok": False, "detail": "Template inválido."}, status_code=400)
        tid = (tpl.get("id") or "").strip() or uuid.uuid4().hex[:12]
        if not _ID_SEGURO.match(tid):
            tid = uuid.uuid4().hex[:12]
        tpl["id"] = tid
        tpl["nome"] = (tpl.get("nome") or "Template").strip() or "Template"
        path = _template_path(tid)
        assert path is not None
        path.write_text(json.dumps(tpl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "id": tid, "detail": "Template salvo."}

    @ctx.app.delete("/plugins/folhas-promocionais/api/templates/{tid}")
    def api_apagar_template(tid: str):
        path = _template_path(tid)
        if not path or not path.is_file():
            return JSONResponse({"ok": False, "detail": "Não encontrado."}, status_code=404)
        path.unlink(missing_ok=True)
        return {"ok": True, "detail": "Template removido."}


    @ctx.app.post("/plugins/folhas-promocionais/api/upload")
    async def api_upload(request: Request):
        """Recebe imagem personalizada (multipart file)."""
        from fastapi import UploadFile
        form = await request.form()
        arquivo = form.get("file")
        if arquivo is None or not hasattr(arquivo, "read"):
            return JSONResponse({"ok": False, "detail": "Arquivo ausente."}, status_code=400)
        data = await arquivo.read()
        if not data or len(data) < 32:
            return JSONResponse({"ok": False, "detail": "Arquivo vazio."}, status_code=400)
        if len(data) > 12 * 1024 * 1024:
            return JSONResponse({"ok": False, "detail": "Arquivo maior que 12 MB."}, status_code=400)
        nome_orig = getattr(arquivo, "filename", "") or "img.png"
        ext = Path(nome_orig).suffix.lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            ext = ".png"
        nome = uuid.uuid4().hex[:16] + ext
        path = _pasta_midia() / nome
        path.write_bytes(data)
        url = f"/plugins/folhas-promocionais/api/midia/{nome}"
        return {"ok": True, "url": url, "nome": nome}

    @ctx.app.get("/plugins/folhas-promocionais/api/midia/{nome}")
    def api_midia(nome: str):
        if not _ID_SEGURO.match(nome.replace(".", "x")[:1] + "x") and not re.match(r"^[A-Za-z0-9._-]+$", nome):
            return JSONResponse({"ok": False, "detail": "Nome inválido."}, status_code=400)
        if not re.match(r"^[A-Za-z0-9._-]+$", nome):
            return JSONResponse({"ok": False, "detail": "Nome inválido."}, status_code=400)
        path = _pasta_midia() / nome
        if not path.is_file():
            return JSONResponse({"ok": False, "detail": "Não encontrado."}, status_code=404)
        media = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        if path.suffix.lower() == ".webp":
            media = "image/webp"
        return Response(content=path.read_bytes(), media_type=media)


    @ctx.app.post("/plugins/folhas-promocionais/api/template/export-zip")
    def api_template_export_zip(corpo: dict = Body(...)):
        """Exporta template em ZIP: template.json + midia/ usadas."""
        import zipfile
        import base64

        tpl = corpo.get("template") if isinstance(corpo, dict) else None
        if not isinstance(tpl, dict):
            return JSONResponse({"ok": False, "detail": "Template inválido."}, status_code=400)

        tpl = json.loads(json.dumps(tpl))  # deep copy
        camadas = tpl.get("camadas") or []
        buf = io.BytesIO()
        usados = set()

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for cam in camadas:
                if (cam.get("tipo") or "") != "image_custom":
                    continue
                src = (cam.get("src") or "").strip()
                if not src:
                    continue
                data = None
                nome_arq = None
                if src.startswith("data:"):
                    try:
                        header, b64 = src.split(",", 1)
                        ext = ".png"
                        if "jpeg" in header or "jpg" in header:
                            ext = ".jpg"
                        elif "webp" in header:
                            ext = ".webp"
                        data = base64.b64decode(b64)
                        nome_arq = (cam.get("id") or uuid.uuid4().hex[:8]) + ext
                    except Exception:
                        continue
                elif "/api/midia/" in src:
                    nome_arq = src.rsplit("/", 1)[-1]
                    path = _pasta_midia() / nome_arq
                    if path.is_file():
                        data = path.read_bytes()
                elif src.startswith("http://") or src.startswith("https://"):
                    from arauto.core.product_image import baixar_bytes
                    data = baixar_bytes(src, timeout=12.0)
                    if data:
                        nome_arq = (cam.get("id") or uuid.uuid4().hex[:8]) + ".jpg"
                if not data or not nome_arq:
                    continue
                # evita colisão de nomes no zip
                base_n = nome_arq
                n = 1
                while nome_arq in usados:
                    stem = Path(base_n).stem
                    suf = Path(base_n).suffix
                    nome_arq = f"{stem}_{n}{suf}"
                    n += 1
                usados.add(nome_arq)
                zf.writestr(f"midia/{nome_arq}", data)
                cam["src"] = f"midia/{nome_arq}"

            zf.writestr(
                "template.json",
                json.dumps(tpl, ensure_ascii=False, indent=2) + "\n",
            )

        nome = (tpl.get("nome") or "template").replace(" ", "_")
        data = buf.getvalue()
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{nome}.zip"'},
        )

    @ctx.app.post("/plugins/folhas-promocionais/api/template/import-zip")
    async def api_template_import_zip(request: Request):
        """Importa ZIP (template.json + midia/) ou JSON puro."""
        import zipfile
        import base64

        form = await request.form()
        arquivo = form.get("file")
        if arquivo is None or not hasattr(arquivo, "read"):
            return JSONResponse({"ok": False, "detail": "Arquivo ausente."}, status_code=400)
        bruto = await arquivo.read()
        if not bruto:
            return JSONResponse({"ok": False, "detail": "Arquivo vazio."}, status_code=400)

        nome_up = (getattr(arquivo, "filename", "") or "").lower()
        tpl = None

        if nome_up.endswith(".json") or bruto[:1] in (b"{", b"["):
            try:
                tpl = json.loads(bruto.decode("utf-8"))
                if isinstance(tpl, dict) and "template" in tpl:
                    tpl = tpl["template"]
            except Exception as exc:
                return JSONResponse({"ok": False, "detail": f"JSON inválido: {exc}"}, status_code=400)
        else:
            try:
                with zipfile.ZipFile(io.BytesIO(bruto)) as zf:
                    nomes = zf.namelist()
                    tj = None
                    for n in nomes:
                        if n.replace("\\", "/").endswith("template.json") or n.endswith(".json"):
                            tj = n
                            if n.endswith("template.json"):
                                break
                    if not tj:
                        return JSONResponse(
                            {"ok": False, "detail": "ZIP sem template.json"},
                            status_code=400,
                        )
                    tpl = json.loads(zf.read(tj).decode("utf-8"))
                    if isinstance(tpl, dict) and "template" in tpl and "camadas" not in tpl:
                        tpl = tpl["template"]
                    # extrai midias
                    for n in nomes:
                        nn = n.replace("\\", "/")
                        if "/midia/" in nn or nn.startswith("midia/"):
                            fname = nn.rsplit("/", 1)[-1]
                            if not fname or not re.match(r"^[A-Za-z0-9._-]+$", fname):
                                continue
                            dest = _pasta_midia() / fname
                            dest.write_bytes(zf.read(n))
            except zipfile.BadZipFile:
                return JSONResponse({"ok": False, "detail": "Não é um ZIP válido."}, status_code=400)
            except Exception as exc:
                log.exception("import zip")
                return JSONResponse({"ok": False, "detail": str(exc)}, status_code=500)

        if not isinstance(tpl, dict) or not isinstance(tpl.get("camadas"), list):
            return JSONResponse({"ok": False, "detail": "Template inválido."}, status_code=400)

        # remapeia src midia/xxx → URL da API
        for cam in tpl.get("camadas") or []:
            if (cam.get("tipo") or "") != "image_custom":
                continue
            src = (cam.get("src") or "").strip().replace("\\", "/")
            if src.startswith("midia/"):
                fname = src.split("/", 1)[-1]
                cam["src"] = f"/plugins/folhas-promocionais/api/midia/{fname}"
            elif src and not src.startswith("/") and not src.startswith("http") and not src.startswith("data:"):
                # nome solto
                if re.match(r"^[A-Za-z0-9._-]+$", src):
                    cam["src"] = f"/plugins/folhas-promocionais/api/midia/{src}"

        return {"ok": True, "template": tpl}

    @ctx.app.post("/plugins/folhas-promocionais/api/exportar")
    def api_exportar(corpo: dict = Body(...)):
        """Gera PNG ou PDF a partir do template + código do produto."""
        tpl = corpo.get("template") if isinstance(corpo, dict) else None
        codigo = (corpo.get("codigo") or "").strip() if isinstance(corpo, dict) else ""
        formato = ((corpo.get("formato") or "png") if isinstance(corpo, dict) else "png").lower()
        dpi = int((corpo.get("dpi") if isinstance(corpo, dict) else None) or DPI_EXPORT)
        dpi = max(72, min(dpi, 300))
        if not isinstance(tpl, dict):
            return JSONResponse({"ok": False, "detail": "Template inválido."}, status_code=400)

        prod_r = _produto_dict(_service(ctx), codigo) if codigo else {"ok": True, "produto": {}}
        produto = dict(prod_r.get("produto") or {})
        if isinstance(corpo, dict):
            if corpo.get("preco_modo"):
                produto["preco_modo"] = str(corpo.get("preco_modo") or "kg")
            if corpo.get("venda_peso") is not None:
                produto["venda_peso"] = bool(corpo.get("venda_peso"))
            elif produto.get("venda_peso") is None and produto.get("by_weight"):
                produto["venda_peso"] = True
        img_bytes = _cosmos_bytes(codigo) if codigo else None

        try:
            pil = _render_pil(tpl, produto, img_bytes, dpi=dpi)
        except Exception as exc:
            log.exception("render folha")
            return JSONResponse({"ok": False, "detail": f"Falha ao renderizar: {exc}"}, status_code=500)

        buf = io.BytesIO()
        nome = (tpl.get("nome") or "folha").replace(" ", "_")
        if formato == "pdf":
            rgb = pil.convert("RGB")
            rgb.save(buf, format="PDF", resolution=float(dpi))
            media = "application/pdf"
            filename = f"{nome}.pdf"
        elif formato in ("jpg", "jpeg"):
            pil.convert("RGB").save(buf, format="JPEG", quality=92, optimize=True)
            media = "image/jpeg"
            filename = f"{nome}.jpg"
        else:
            pil.save(buf, format="PNG", optimize=True)
            media = "image/png"
            filename = f"{nome}.png"
        data = buf.getvalue()
        return Response(
            content=data,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
