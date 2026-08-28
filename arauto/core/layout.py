"""Layout da tela dos terminais, por modelo de aparelho.

O terminal não tem layout próprio: quem posiciona cada texto é o servidor, um
`IDvShowText` por linha. Isso significa que a tela é inteiramente configurável —
e que cada modelo precisa do seu, porque um TC-504 tem 320×240 e um G-BOT tem
1280×800.

O padrão é o layout do TC Server original, copiado de uma captura real com um
TC-506 Mídia (480×272), e escalado para os demais modelos.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .settings import APP_DIR

ARQUIVO = APP_DIR / "layouts.json"

# id do modelo (termType) -> (nome, largura, altura)
MODELOS: dict[int, tuple[str, int, int]] = {
    504: ("TC-504", 320, 240),
    506: ("TC-506 Mídia", 480, 272),
    508: ("TC-508", 480, 272),
    600: ("G-BOT", 1280, 800),
    601: ("G-BOT - 2", 1280, 800),
}

MODELO_PADRAO = 506          # o da captura; base de todos os outros
BASE_LARGURA, BASE_ALTURA = 480, 272

FONTE_NORMAL = "DejaVuSans.ttf"
FONTE_NEGRITO = "DejaVuSans-Bold.ttf"

# Arquivos de fonte que existem no firmware do TC Server / aparelho.
# Roboto é o padrão de fábrica do TC-508 (mesmo sem extensão de arquivo).
FONTES_APARELHO: tuple[str, ...] = (
    "DejaVuSans.ttf",
    "DejaVuSans-Bold.ttf",
    "DejaVuSans-Oblique.ttf",
    "DejaVuSans-BoldOblique.ttf",
    "DejaVuSansMono.ttf",
    "DejaVuSansMono-Bold.ttf",
    "DejaVuSansMono-Oblique.ttf",
    "DejaVuSansMono-BoldOblique.ttf",
    "DejaVuSerif.ttf",
    "DejaVuSerif-Bold.ttf",
    "DejaVuSerif-Oblique.ttf",
    "DejaVuSerif-BoldOblique.ttf",
    "Roboto",
    "Vera.ttf",
    "VeraBd.ttf",
    "VeraIt.ttf",
    "VeraBI.ttf",
    "VeraMono.ttf",
    "VeraMoBd.ttf",
    "VeraMoIt.ttf",
    "VeraMoBI.ttf",
    "VeraSe.ttf",
    "VeraSeBd.ttf",
    "swz721m.ttf",
    "SWZ721MI.TTF",
    "cour.pfa",
    "courb.pfa",
    "couri.pfa",
    "courbi.pfa",
    "cursor.pfa",
    "c0583bt_.pfb",
    "c0611bt_.pfb",
    "c0632bt_.pfb",
    "c0633bt_.pfb",
    "c0648bt_.pfb",
    "c0649bt_.pfb",
    "l047013t.pfa",
    "l047016t.pfa",
    "l047033t.pfa",
    "l047036t.pfa",
    "l048013t.pfa",
    "l048016t.pfa",
    "l048033t.pfa",
    "l048036t.pfa",
    "l049013t.pfa",
    "l049016t.pfa",
    "l049033t.pfa",
    "l049036t.pfa",
    "UTRG____.pfa",
    "UTB_____.pfa",
    "UTI_____.pfa",
    "UTBI____.pfa",
    "helvetica_80_50.qpf",
    "helvetica_80_50i.qpf",
    "helvetica_80_75.qpf",
    "helvetica_80_75i.qpf",
    "helvetica_100_50.qpf",
    "helvetica_100_50i.qpf",
    "helvetica_100_75.qpf",
    "helvetica_100_75i.qpf",
    "helvetica_120_50.qpf",
    "helvetica_120_50i.qpf",
    "helvetica_120_75.qpf",
    "helvetica_120_75i.qpf",
    "helvetica_140_50.qpf",
    "helvetica_140_50i.qpf",
    "helvetica_140_75.qpf",
    "helvetica_140_75i.qpf",
    "helvetica_180_50.qpf",
    "helvetica_180_50i.qpf",
    "helvetica_180_75.qpf",
    "helvetica_180_75i.qpf",
    "helvetica_240_50.qpf",
    "helvetica_240_50i.qpf",
    "helvetica_240_75.qpf",
    "helvetica_240_75i.qpf",
    "fixed_70_50.qpf",
    "fixed_120_50.qpf",
    "micro_40_50.qpf",
    "unifont_160_50.qpf",
    "japanese_230_50.qpf",
)

# Padrão de fábrica por termType (captura do ExhibitionDialog / SC504).
FONTES_PADRAO_MODELO: dict[int, tuple[str, str]] = {
    504: ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    506: ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    508: ("Roboto", "Roboto"),
    600: ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    601: ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
}

CORES_HEX: dict[int, str] = {
    256: "#000000",
    257: "#8B4513",
    258: "#008000",
    259: "#808000",
    260: "#000080",
    261: "#800080",
    262: "#708090",
    263: "#C0C0C0",
    264: "#C0C0C0",
    265: "#FF0000",
    266: "#00FF00",
    267: "#FFFF00",
    268: "#0000FF",
    269: "#FF00FF",
    270: "#00FFFF",
    271: "#FFFFFF",
    65535: "transparent",
}

# Paleta oficial dos terminais Gertec (códigos 0x0100–0x010F + transparente).
# Valores decimais usados em IDvShowText / limpeza de tela.
CORES: dict[str, int] = {
    "PRETO": 256,          # 0x0100
    "MARROM": 257,         # 0x0101
    "VERDE": 258,          # 0x0102
    "OLIVA": 259,          # 0x0103
    "AZUL MARINHO": 260,   # 0x0104
    "ROXO": 261,           # 0x0105
    "METÁLICO": 262,       # 0x0106
    "CINZA": 263,          # 0x0107
    "PRATA": 264,          # 0x0108
    "VERMELHO": 265,       # 0x0109
    "LIMA": 266,           # 0x010A
    "AMARELO": 267,        # 0x010B
    "AZUL": 268,           # 0x010C
    "FUCHSIA": 269,        # 0x010D
    "ÁGUA": 270,           # 0x010E
    "BRANCO": 271,         # 0x010F
    "TRANSPARENTE": 65535, # 0xFFFF
}

# Padrões alinhados à paleta e à captura do TC Server original.
COR_TEXTO = CORES["CINZA"]            # 263
COR_SEM_FUNDO = -1                    # sem fundo (não confundir com TRANSPARENTE)
COR_LIMPAR_TELA = CORES["AZUL MARINHO"]  # 260

# O protocolo não tem quebra de linha: cada IDvShowText desenha uma linha só.
# Para quebrar, o servidor manda vários comandos com Y crescente. Como não
# temos as métricas da fonte do aparelho, a largura de caractere é estimada —
# o mesmo fator é usado no editor, para a prévia bater com o que vai à tela.
FATOR_LARGURA_CARACTERE = 0.55
ENTRELINHA = 1.15

# Ordem em que os elementos são desenhados, e o que cada um mostra.
# "imagem" é um retângulo (x, y, largura, altura) usado pelo SC504 para
# posicionar a foto do produto no bitmap de IDvShowImg.
ELEMENTOS = [
    ("imagem", "Foto do produto"),
    ("codigo", "Código de barras"),
    ("descricao", "Descrição do produto"),
    ("rotulo1", "Rótulo do preço 1"),
    ("preco1", "Preço 1"),
    ("rotulo2", "Rótulo do preço 2"),
    ("preco2", "Preço 2"),
    ("nao_achado", "Produto não encontrado"),
]
NOMES_ELEMENTOS = dict(ELEMENTOS)

# Layout capturado do TC Server original (480×272).
# A foto fica à direita; textos à esquerda — evita fundo preto em tela cheia.
PADRAO_BASE: dict[str, dict] = {
    "imagem":     {"x": 290, "y": 20, "tamanho": 16, "negrito": False,
                   "visivel": True, "largura": 170, "linhas": 1, "altura": 170,
                   "trava_proporcao": False},
    "codigo":     {"x": 20, "y": 75, "tamanho": 16, "negrito": False,
                   "visivel": True, "largura": 0, "linhas": 1, "altura": 0},
    "descricao":  {"x": 20, "y": 40, "tamanho": 22, "negrito": False,
                   "visivel": True, "largura": 250, "linhas": 2, "altura": 0},
    "rotulo1":    {"x": 20, "y": 145, "tamanho": 18, "negrito": False,
                   "visivel": True, "largura": 0, "linhas": 1, "altura": 0},
    "preco1":     {"x": 20, "y": 170, "tamanho": 30, "negrito": True,
                   "visivel": True, "largura": 0, "linhas": 1, "altura": 0},
    "rotulo2":    {"x": 20, "y": 210, "tamanho": 16, "negrito": False,
                   "visivel": True, "largura": 0, "linhas": 1, "altura": 0},
    "preco2":     {"x": 20, "y": 230, "tamanho": 24, "negrito": True,
                   "visivel": True, "largura": 0, "linhas": 1, "altura": 0},
    "nao_achado": {"x": -1, "y": 30, "tamanho": 30, "negrito": True,
                   "visivel": True, "largura": 0, "linhas": 1, "altura": 0},
}


@dataclass
class Elemento:
    x: int = 0
    y: int = 0
    tamanho: int = 20
    negrito: bool = False
    visivel: bool = True
    largura: int = 0    # texto: largura de quebra; imagem: largura da caixa
    linhas: int = 1     # máximo de linhas quando há quebra
    altura: int = 0     # só imagem: altura da caixa em pixels
    trava_proporcao: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Layout:
    modelo: int
    elementos: dict[str, Elemento] = field(default_factory=dict)
    cor_texto: int = COR_TEXTO
    cor_fundo_texto: int = COR_SEM_FUNDO
    cor_tela: int = COR_LIMPAR_TELA
    fonte_normal: str = FONTE_NORMAL
    fonte_negrito: str = FONTE_NEGRITO

    @property
    def nome(self) -> str:
        return MODELOS.get(self.modelo, (f"Modelo {self.modelo}", 0, 0))[0]

    @property
    def largura(self) -> int:
        return MODELOS.get(self.modelo, ("", BASE_LARGURA, BASE_ALTURA))[1]

    @property
    def altura(self) -> int:
        return MODELOS.get(self.modelo, ("", BASE_LARGURA, BASE_ALTURA))[2]

    def to_dict(self) -> dict:
        return {
            "modelo": self.modelo,
            "nome": self.nome,
            "largura": self.largura,
            "altura": self.altura,
            "cor_texto": self.cor_texto,
            "cor_fundo_texto": self.cor_fundo_texto,
            "cor_tela": self.cor_tela,
            "fonte_normal": self.fonte_normal,
            "fonte_negrito": self.fonte_negrito,
            "elementos": {k: v.to_dict() for k, v in self.elementos.items()},
        }

    def fonte(self, chave: str) -> str:
        elemento = self.elementos.get(chave)
        return self.fonte_negrito if (elemento and elemento.negrito) else self.fonte_normal


def _escalar(base: dict, largura: int, altura: int) -> dict:
    """Adapta o layout de 480×272 para outra resolução."""
    if (largura, altura) == (BASE_LARGURA, BASE_ALTURA):
        return dict(base)
    fx, fy = largura / BASE_LARGURA, altura / BASE_ALTURA
    fator = min(fx, fy)
    return {
        # x = -1 significa "centralizar", não é coordenada: não escala
        "x": base["x"] if base["x"] < 0 else int(base["x"] * fx),
        "y": int(base["y"] * fy),
        "tamanho": max(8, int(base["tamanho"] * fator)),
        "negrito": base["negrito"],
        "visivel": base["visivel"],
        "largura": int(base.get("largura", 0) * fx),
        "linhas": base.get("linhas", 1),
        "altura": int(base.get("altura", 0) * fy),
        "trava_proporcao": bool(base.get("trava_proporcao", False)),
    }


def quebrar_texto(texto: str, tamanho: int, largura: int,
                  max_linhas: int = 1) -> list[str]:
    """Quebra o texto em linhas que caibam na largura pedida.

    `largura` em pixels; 0 desliga a quebra. A largura de caractere é estimada
    a partir do tamanho da fonte, porque não temos as métricas reais do
    aparelho. O editor usa exatamente a mesma conta.
    """
    texto = (texto or "").strip()
    if not texto:
        return []
    if largura <= 0 or max_linhas <= 1:
        return [texto]

    por_linha = max(1, int(largura / max(1.0, tamanho * FATOR_LARGURA_CARACTERE)))
    if len(texto) <= por_linha:
        return [texto]

    linhas: list[str] = []
    atual = ""
    for palavra in texto.split():
        while len(palavra) > por_linha:        # palavra maior que a linha
            if atual:
                linhas.append(atual); atual = ""
            linhas.append(palavra[:por_linha])
            palavra = palavra[por_linha:]
        candidata = f"{atual} {palavra}".strip()
        if len(candidata) <= por_linha:
            atual = candidata
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)

    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        ultima = linhas[-1]
        linhas[-1] = (ultima[:max(0, por_linha - 1)].rstrip() + "…") if ultima else "…"
    return linhas


def layout_padrao(modelo: int) -> Layout:
    _, largura, altura = MODELOS.get(modelo, ("", BASE_LARGURA, BASE_ALTURA))
    fonte_n, fonte_b = FONTES_PADRAO_MODELO.get(modelo, (FONTE_NORMAL, FONTE_NEGRITO))
    return Layout(
        modelo=modelo,
        elementos={
            chave: Elemento(**_escalar(base, largura, altura))
            for chave, base in PADRAO_BASE.items()
        },
        fonte_normal=fonte_n,
        fonte_negrito=fonte_b,
    )


class Layouts:
    """Coleção de layouts, um por modelo, persistida em JSON."""

    def __init__(self, caminho: Path = ARQUIVO) -> None:
        self.caminho = caminho
        self._lock = threading.RLock()
        self._layouts: dict[int, Layout] = {}
        self.carregar()

    # --------------------------------------------------------------- io
    def carregar(self) -> None:
        with self._lock:
            self._layouts = {m: layout_padrao(m) for m in MODELOS}
            if not self.caminho.exists():
                return
            try:
                dados = json.loads(self.caminho.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return  # arquivo corrompido: segue com os padrões
            for chave, bruto in (dados.get("modelos") or {}).items():
                try:
                    modelo = int(chave)
                except ValueError:
                    continue
                self._layouts[modelo] = self._do_dict(modelo, bruto)

    def _do_dict(self, modelo: int, bruto: dict) -> Layout:
        padrao = layout_padrao(modelo)
        elementos = {}
        for chave, _ in ELEMENTOS:
            valores = (bruto.get("elementos") or {}).get(chave)
            if not isinstance(valores, dict):
                elementos[chave] = padrao.elementos[chave]
                continue
            base = padrao.elementos[chave]
            elementos[chave] = Elemento(
                x=int(valores.get("x", base.x)),
                y=int(valores.get("y", base.y)),
                tamanho=max(6, int(valores.get("tamanho", base.tamanho))),
                negrito=bool(valores.get("negrito", base.negrito)),
                visivel=bool(valores.get("visivel", base.visivel)),
                largura=max(0, int(valores.get("largura", base.largura))),
                linhas=max(1, min(6, int(valores.get("linhas", base.linhas)))),
                altura=max(0, int(valores.get("altura", base.altura))),
                trava_proporcao=bool(valores.get("trava_proporcao", False)),
            )
        return Layout(
            modelo=modelo,
            elementos=elementos,
            cor_texto=int(bruto.get("cor_texto", COR_TEXTO)),
            cor_fundo_texto=int(bruto.get("cor_fundo_texto", COR_SEM_FUNDO)),
            cor_tela=int(bruto.get("cor_tela", COR_LIMPAR_TELA)),
            fonte_normal=str(bruto.get("fonte_normal") or FONTES_PADRAO_MODELO.get(modelo, (FONTE_NORMAL, FONTE_NEGRITO))[0]),
            fonte_negrito=str(bruto.get("fonte_negrito") or FONTES_PADRAO_MODELO.get(modelo, (FONTE_NORMAL, FONTE_NEGRITO))[1]),
        )

    def salvar(self) -> None:
        with self._lock:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            self.caminho.write_text(json.dumps({
                "versao": 1,
                "modelos": {str(m): l.to_dict() for m, l in self._layouts.items()},
            }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ----------------------------------------------------------- acesso
    def obter(self, modelo: int | None) -> Layout:
        with self._lock:
            if modelo in self._layouts:
                return self._layouts[modelo]
            # Terminal não identificado ou modelo desconhecido: usa o padrão,
            # que é melhor do que não desenhar nada.
            return self._layouts.get(MODELO_PADRAO) or layout_padrao(MODELO_PADRAO)

    def gravar(self, modelo: int, bruto: dict) -> Layout:
        if modelo not in MODELOS:
            raise ValueError(f"Modelo desconhecido: {modelo}")
        erros = validar(modelo, bruto)
        if erros:
            raise ValueError(" · ".join(erros))
        with self._lock:
            self._layouts[modelo] = self._do_dict(modelo, bruto)
            self.salvar()
            return self._layouts[modelo]

    def restaurar(self, modelo: int) -> Layout:
        with self._lock:
            self._layouts[modelo] = layout_padrao(modelo)
            self.salvar()
            return self._layouts[modelo]

    def todos(self) -> list[dict]:
        with self._lock:
            return [self._layouts[m].to_dict() for m in sorted(MODELOS)]


def validar(modelo: int, bruto: dict) -> list[str]:
    """Impede salvar um layout que o terminal não conseguiria desenhar."""
    _, largura, altura = MODELOS.get(modelo, ("", BASE_LARGURA, BASE_ALTURA))
    erros: list[str] = []

    for chave, rotulo in ELEMENTOS:
        valores = (bruto.get("elementos") or {}).get(chave)
        if not isinstance(valores, dict):
            continue
        try:
            x = int(valores.get("x", 0))
            y = int(valores.get("y", 0))
            tamanho = int(valores.get("tamanho", 20))
            box_w = int(valores.get("largura", 0) or 0)
            box_h = int(valores.get("altura", 0) or 0)
        except (TypeError, ValueError):
            erros.append(f"{rotulo}: valores precisam ser números")
            continue
        if x < -1 or x >= largura:
            erros.append(f"{rotulo}: X fora da tela (use -1 para centralizar, "
                         f"ou 0 a {largura - 1})")
        if y < 0 or y >= altura:
            erros.append(f"{rotulo}: Y fora da tela (0 a {altura - 1})")

        if chave == "imagem":
            # Caixa da foto: x,y + largura x altura precisam caber na tela.
            if box_w < 0 or box_h < 0:
                erros.append(f"{rotulo}: largura/altura não podem ser negativas")
            elif box_w > 0 and box_h > 0:
                if x >= 0 and x + box_w > largura:
                    erros.append(f"{rotulo}: a caixa passa da borda direita")
                if y + box_h > altura:
                    erros.append(f"{rotulo}: a caixa passa da borda de baixo")
            continue

        if not 6 <= tamanho <= 200:
            erros.append(f"{rotulo}: tamanho da fonte fora de 6 a 200")
        linhas = max(1, min(6, int(valores.get("linhas", 1) or 1)))
        altura_total = tamanho + int(tamanho * ENTRELINHA) * (linhas - 1)
        if y + altura_total > altura:
            erros.append(f"{rotulo}: o texto passaria da borda de baixo"
                         + (f" ({linhas} linhas)" if linhas > 1 else ""))
        if box_w < 0:
            erros.append(f"{rotulo}: a largura da quebra não pode ser negativa")

    ext_ok = (".ttf", ".otf", ".pfb", ".pfa", ".qpf")
    for campo in ("fonte_normal", "fonte_negrito"):
        nome = str(bruto.get(campo, "")).strip()
        if not nome:
            erros.append(f"{campo}: informe o arquivo da fonte do aparelho")
        elif "." in nome and not nome.lower().endswith(ext_ok):
            erros.append(f"{campo}: extensão não reconhecida no aparelho")
    return erros


_instancia: Layouts | None = None
_trava = threading.Lock()


def get_layouts() -> Layouts:
    global _instancia
    with _trava:
        if _instancia is None:
            _instancia = Layouts()
        return _instancia


def hex_cor(codigo: int, fallback: str = "#C0C0C0") -> str:
    if int(codigo) == COR_SEM_FUNDO:
        return "transparent"
    if int(codigo) == 271:
        return "#FFFFFF"
    return CORES_HEX.get(int(codigo), fallback)


def rgb_cor(codigo: int, fallback: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    """RGB 0–255 da paleta Gertec — usado no bitmap de IDvShowImg."""
    hex_ = hex_cor(codigo, "")
    if not hex_ or hex_ == "transparent" or not hex_.startswith("#") or len(hex_) < 7:
        return fallback
    return (int(hex_[1:3], 16), int(hex_[3:5], 16), int(hex_[5:7], 16))


