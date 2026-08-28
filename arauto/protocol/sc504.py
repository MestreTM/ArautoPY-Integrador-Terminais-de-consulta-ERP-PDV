"""Servidor do protocolo SC504 (TC-504, TC-506 Mídia, TC-508, GB-600/601).

Diferente do SC501, que é ASCII, o SC504 é binário. O enquadramento e os
identificadores abaixo vêm das constantes compiladas em
`br.com.gertec.tc.server.protocol.sc504.commands.Sc504CommDefs`:

    STX                 short, valor 2      (declarado `S`, ou seja 2 bytes)
    DEFAULT_BYTE_ORDER  LITTLE_ENDIAN
    RESTART_PASSWORD    1513334220
    CODE_MAX_LENGTH     256                 (IDbReadScanner)
    TEXT_MAX_LENGTH     170                 (IDvShowText)

Quadro (padrão `B-H-I-LE`):

    ┌────────┬────────┬──────────┬──────────────┐
    │ STX    │ ID     │ TAMANHO  │ DADOS        │
    │ 1 byte │ 2 by LE│ 4 by LE  │ TAMANHO by   │
    └────────┴────────┴──────────┴──────────────┘
      cabeçalho de 7 bytes

O `Tc504Command` tem construtor `(S[B)V` — identificador `short`, dados
`byte[]` — e serializa com `put(byte)`, `putShort(short, ordem)` e
`putInt(int, ordem)`. Isso dá 1 + 2 + 4 = 7 bytes, o que também explica o
`sipush 7` presente em `Sc504CommDefs`.

Se o seu terminal não casar com esse formato, rode o sniffer para descobrir o
formato real e ajuste `SC504_FRAME`:

    python run.py --sniffer 16510

Cada requisição do terminal tem um identificador ímpar e a resposta do servidor
usa o identificador seguinte (`ID_V_LIVE`=17 → `R_ID_V_LIVE`=18). Esse par
ímpar/par vale para toda a tabela e é o que permite responder genericamente.

ATENÇÃO — reconstruído por engenharia reversa, sem terminal físico. Os
identificadores são exatos (extraídos do JAR). O enquadramento é a leitura mais
plausível das constantes, mas o cabeçalho pode ter um campo a mais. Valide
contra hardware antes de produção; o ponto de ajuste é `montar()` e `_drenar()`.
"""

from __future__ import annotations

import io
import logging
import socket
import struct
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import quote

from ..core.layout import ENTRELINHA, MODELOS, get_layouts, quebrar_texto
from ..core.service import QueryService
from ..core.settings import get_settings
from .monitor import MONITOR, hexdump
from .sniffer import analisar

log = logging.getLogger("arauto.sc504")

# Dimensões fixas da tela do TC-506 Mídia (IDvShowImg).
IMG_LARGURA = 480
IMG_ALTURA = 272
IMG_PIXELS = IMG_LARGURA * IMG_ALTURA  # 130_560
IMG_TIMEOUT_S = 3.0
# Cache simples: código -> payload IDvShowImg (evita baixar a cada consulta).
_CACHE_IMAGENS: dict[str, bytes] = {}
_CACHE_IMAGENS_MAX = 64
_CACHE_LOCK = threading.Lock()

STX = 2
CHARSET = "ISO-8859-1"

# Enquadramentos conhecidos. O padrão vem da leitura de Tc504Command; os outros
# existem porque só hardware real decide, e trocar de hipótese tem de ser uma
# linha de configuração, não uma recompilação.
FORMATOS = {
    "B-H-I-LE": ("<BHI", 7),   # STX 1 | ID 2 LE | TAM 4 LE  (padrão)
    "B-H-I-BE": (">BHI", 7),
    "B-H-H-LE": ("<BHH", 5),
    "B-B-H-LE": ("<BBH", 4),
    "H-H-H-LE": ("<HHH", 6),   # o que a versão 1.0 assumia
    "H-H-H-BE": (">HHH", 6),
}
FORMATO_PADRAO = "B-H-I-LE"

# Em modo passivo o servidor não fala primeiro. Serve para descobrir o que o
# terminal manda espontaneamente — se mandarmos um quadro que ele não entende,
# ele pode fechar a conexão antes de revelar qualquer coisa.
PASSIVO_PADRAO = False
CODE_MAX_LENGTH = 256      # IDbReadScanner
TEXT_MAX_LENGTH = 128      # ArgDisplayText.TEXT_MAX_LENGTH
FONT_NAME_MAX_LENGTH = 32  # ArgDisplayText.FONT_NAME_MAX_LENGTH

# Padrões de exibição. Confirmados na estrutura, não nos valores: sem terminal
# não dá para saber qual fonte existe no aparelho nem a paleta de cores.
# Paleta NamedColor do JAR — o campo de cor é índice, não RGB.
CORES = {
    "BLACK": 0, "RED": 1, "YELLOW": 2, "BLUE": 3, "WHITE": 4, "GREEN": 5,
    "BROWN": 6, "OLIVE": 7, "NAVY": 8, "PURPLE": 9, "METALLIC": 10,
    "GREY": 11, "SILVER": 12, "LIME": 13, "FUCHSIA": 14, "WATER": 15,
    "TRANSPARENT": 16,
}

# --- valores observados numa captura do TC Server ORIGINAL (TC-506 Mídia) ---
# Não são a paleta NamedColor: o servidor original manda 263 para o texto, -1
# para "sem fundo" e 260 no DispClear. Replicamos o que comprovadamente
# funciona em vez de deduzir da tabela de cores.
COR_TEXTO = 263
COR_SEM_FUNDO = -1
COR_LIMPAR_TELA = 260

# As fontes são arquivos TrueType do próprio aparelho. "Arial" não existe nele
# — pedir uma fonte inexistente faz o terminal não desenhar nada, que era a
# causa da tela preta.
FONTE_NORMAL = "DejaVuSans.ttf"
FONTE_NEGRITO = "DejaVuSans-Bold.ttf"

# Layout capturado do original, em coordenadas de 480x272 (TC-506 Mídia).
# (texto, x, y, tamanho, negrito)
LAYOUT_BASE = {
    "descricao":  (30, 40, 25, False),
    "codigo":     (30, 75, 16, False),
    "rotulo1":    (30, 145, 18, False),
    "rotulo2":    (245, 145, 18, False),
    "preco1":     (30, 170, 30, True),
    "preco2":     (250, 170, 30, True),
    "nao_achado": (-1, 30, 30, True),   # x = -1 centraliza
}
LAYOUT_LARGURA = 480
LAYOUT_ALTURA = 272

# O original manda um keep-alive a cada 10 s; é o que mantém o terminal
# exibindo "conectado".
INTERVALO_LIVE = 10.0
RESTART_PASSWORD = 1513334220
MARCADOR_IDENTIFY = 0x31   # primeiro byte de RIDwGetIdentify
MAX_DADOS = 1 << 20     # 1 MB: acima disso é enquadramento errado, não dado

# --- identificadores extraídos do JAR (requisição → resposta) ---
ID_V_LIVE = 17
ID_V_RECV_FILE = 97
R_ID_V_RECV_FILE = 98
ID_V_SEND_FILE = 99
R_ID_V_SEND_FILE = 100
ID_V_UPDATE_MEDIAS = 117
R_ID_V_UPDATE_MEDIAS = 118
ID_V_DELETE_FILE = 184
R_ID_V_DELETE_FILE = 185
# Limpa toda a mídia da memória interna (captura TC Server: 0xBA → 0xBB)
ID_V_DELETE_ALL_MEDIAS = 186
R_ID_V_DELETE_ALL_MEDIAS = 187

R_ID_V_LIVE = 18
ID_W_GET_IDENTIFY = 19
R_ID_W_GET_IDENTIFY = 20
ID_CONTINUE = 21
R_ID_CONTINUE = 22
ID_V_GET_UID = 27
R_ID_V_GET_UID = 28
ID_V_ALWAYS_LIVE = 29
R_ID_V_ALWAYS_LIVE = 30
ID_V_DISP_CLEAR = 33
R_ID_V_DISP_CLEAR = 34
ID_V_SHOW_TEXT = 35
R_ID_V_SHOW_TEXT = 36
ID_V_SHOW_IMG = 37
ID_B_READ_SCANNER = 89
R_ID_B_READ_SCANNER = 90
ID_GO_ADV = 43
ID_STOP_ADV = 45
ID_RESTART = 121
ID_QUERY_PROCESS_FAILURE = 214
ID_GET_MAC_ADDRESS = 218
R_ID_GET_MAC_ADDRESS = 219
ID_GET_VERSION = 216
R_ID_GET_VERSION = 217

# Tabela completa extraída do JAR. A resposta é sempre `requisição + 1`, mas a
# paridade NÃO serve para distinguir os dois: até ID_RESTART as requisições são
# ímpares, e a partir de ID_SHOW_LOCAL_MEDIA (166) passam a ser pares. Confiar
# na paridade fazia o servidor ignorar todo o bloco de áudio, vídeo e sensores.
NOMES = {
    17: "ID_V_LIVE", 19: "ID_W_GET_IDENTIFY", 21: "ID_CONTINUE",
    23: "ID_V_SET_SETUP_TCP", 25: "ID_V_GET_SETUP_TCP", 27: "ID_V_GET_UID",
    29: "ID_V_ALWAYS_LIVE", 33: "ID_V_DISP_CLEAR", 35: "ID_V_SHOW_TEXT",
    37: "ID_V_SHOW_IMG", 39: "ID_B_SET_TIME_EXHIB", 41: "ID_V_GET_TIME_EXHIB",
    43: "ID_GO_ADV", 45: "ID_STOP_ADV", 49: "ID_V_SET_ENABLE_KEY",
    51: "ID_B_GET_ENABLE_KEY", 65: "ID_V_SET_LEC", 67: "ID_B_GET_LEC",
    89: "ID_B_READ_SCANNER", 97: "ID_V_RECV_FILE", 98: "R_ID_V_RECV_FILE",
    99: "ID_V_SEND_FILE", 100: "R_ID_V_SEND_FILE",
    117: "ID_V_UPDATE_MEDIAS", 118: "R_ID_V_UPDATE_MEDIAS",
    121: "ID_RESTART", 129: "ID_V_SHOW_FRAME", 166: "ID_SHOW_LOCAL_MEDIA",
    184: "ID_V_DELETE_FILE", 185: "R_ID_V_DELETE_FILE",
    186: "ID_V_DELETE_ALL_MEDIAS", 187: "R_ID_V_DELETE_ALL_MEDIAS",
    168: "ID_SET_SENSOR", 170: "ID_GET_SENSOR_STATUS", 172: "ID_SET_AUDIO",
    176: "ID_SET_VOLUME", 180: "ID_SET_BRIGHTNESS", 208: "ID_V_PLAY_AUDIO",
    214: "ID_QUERY_PROCESS_FAILURE", 216: "ID_GET_VERSION",
    218: "ID_GET_MAC_ADDRESS",
}

REQUISICOES = set(NOMES)
RESPOSTAS = {i + 1 for i in NOMES if i != ID_QUERY_PROCESS_FAILURE}

# A tabela de modelos e o layout de tela vivem em core/layout.py, porque são
# configuráveis pela tela /layout e não fazem parte do protocolo em si.

# O original manda um keep-alive a cada 10 s; é o que mantém o terminal
# exibindo "conectado".
INTERVALO_LIVE = 10.0
RESTART_PASSWORD = 1513334220
MARCADOR_IDENTIFY = 0x31   # primeiro byte de RIDwGetIdentify
MAX_DADOS = 1 << 20     # 1 MB: acima disso é enquadramento errado, não dado

# Tabela real extraída de TerminalType: sc504Id, nome comercial e resolução.
# Os ids NÃO são 0,1,2… — são o número do modelo.
MODELOS = {
    504: ("TC-504", 320, 240),
    506: ("TC-506 Mídia", 480, 272),
    508: ("TC-508", 480, 272),
    600: ("G-BOT", 1280, 800),
    601: ("G-BOT - 2", 1280, 800),
}



def montar(identificador: int, dados: bytes = b"",
           formato: str = FORMATO_PADRAO) -> bytes:
    """Monta um quadro SC504 no enquadramento escolhido."""
    struct_fmt, _ = FORMATOS.get(formato, FORMATOS[FORMATO_PADRAO])
    return struct.pack(struct_fmt, STX, identificador, len(dados)) + dados


def dword(valor: int) -> bytes:
    """Payload de um DwordCommand: um int de 4 bytes little-endian."""
    return struct.pack("<i", valor)


def word(valor: int) -> bytes:
    """Payload de um WordCommand: 2 bytes LE (cor Gertec / 0xFFFF transparente).

    Aceita -1 ou 65535 como transparente. ``<H`` evita struct.error com 65535.
    """
    v = int(valor)
    if v < 0:
        v = 0xFFFF
    return struct.pack("<H", v & 0xFFFF)


def desmontar(dados: bytes, formato: str = FORMATO_PADRAO):
    """Lê o cabeçalho. Devolve (stx, id, tamanho) ou None se faltar byte."""
    struct_fmt, cabecalho = FORMATOS.get(formato, FORMATOS[FORMATO_PADRAO])
    if len(dados) < cabecalho:
        return None
    return struct.unpack(struct_fmt, dados[:cabecalho])


def montar_texto_display(texto: str, pos_x: int = 0, pos_y: int = 0,
                         fonte: str = FONTE_NORMAL,
                         tamanho: int = 25,
                         cor: int = COR_TEXTO,
                         fundo: int = COR_SEM_FUNDO) -> bytes:
    """Monta o ArgDisplayText de `IDvShowText`.

    Campos, na ordem declarada em `ArgDisplayText`:
        posX (short) | posY (short) | text (128) | font (32)
        | fontSize (short) | fontColor (short) | backgroundColor (short)

    Os campos de texto vão em buffers de tamanho fixo, preenchidos com zero —
    é assim que o terminal preenche o dele (o `ArgSerialData` que ele envia tem
    256 bytes com lixo no fim).
    """
    campo_texto = (texto or "").encode(CHARSET, errors="replace")[:TEXT_MAX_LENGTH]
    campo_texto = campo_texto.ljust(TEXT_MAX_LENGTH, b"\x00")
    campo_fonte = (fonte or "").encode(CHARSET, errors="replace")[:FONT_NAME_MAX_LENGTH]
    campo_fonte = campo_fonte.ljust(FONT_NAME_MAX_LENGTH, b"\x00")
    def _cor16(v: int) -> int:
        v = int(v)
        if v < 0:
            return 0xFFFF
        return v & 0xFFFF

    return (
        struct.pack("<hh", int(pos_x), int(pos_y))
        + campo_texto + campo_fonte
        + struct.pack("<HHH", int(tamanho) & 0xFFFF, _cor16(cor), _cor16(fundo))
    )


def linhas_para_display(resultado, modelo: int | None) -> list[tuple]:
    """Monta as linhas segundo o layout configurado para o modelo conectado.

    Devolve tuplas (texto, x, y, tamanho, fonte) na ordem de desenho.
    """
    layout = get_layouts().obter(modelo)

    def item(chave: str, texto: str) -> list[tuple]:
        """Um elemento vira uma linha, ou várias quando há quebra configurada.

        O protocolo não tem quebra: cada IDvShowText desenha uma linha só, então
        emitimos um comando por linha, com Y crescente.
        """
        elemento = layout.elementos.get(chave)
        if elemento is None or not elemento.visivel or not texto:
            return []
        partes = quebrar_texto(texto, elemento.tamanho,
                               elemento.largura, elemento.linhas)
        passo = int(elemento.tamanho * ENTRELINHA)
        fonte = layout.fonte(chave)
        return [(parte, elemento.x, elemento.y + i * passo,
                 elemento.tamanho, fonte)
                for i, parte in enumerate(partes)]

    if not resultado.found:
        return item("nao_achado", resultado.label_not_found)

    linhas: list[tuple] = []
    linhas += item("codigo", resultado.barcode)
    linhas += item("descricao", resultado.description)
    linhas += item("rotulo1", resultado.label1 if resultado.price1 else "")
    linhas += item("preco1", resultado.price1)
    linhas += item("rotulo2", resultado.label2 if resultado.price2 else "")
    linhas += item("preco2", resultado.price2)
    return linhas


def _url_imagem_produto(codigo: str) -> str | None:
    """Monta a URL da imagem a partir do template em PRODUCT_IMAGE_URL.

    Placeholders aceitos: {barcode}, {codigo}, {gtin}.
    Devolve None se a função estiver desligada ou a URL vazia.
    """
    settings = get_settings()
    if not settings.get_bool("SHOW_PRODUCT_IMAGE", False):
        return None
    template = (settings.get("PRODUCT_IMAGE_URL") or "").strip()
    if not template:
        return None
    # Codifica só o valor do código, preservando a estrutura da URL.
    seguro = quote(codigo, safe="")
    return (
        template
        .replace("{barcode}", seguro)
        .replace("{codigo}", seguro)
        .replace("{gtin}", seguro)
    )


def _baixar_bytes(url: str, timeout: float = IMG_TIMEOUT_S) -> bytes | None:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "TCServer-PY/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Limite de segurança: 4 MiB
            data = resp.read(4 * 1024 * 1024)
            if not data:
                return None
            return data
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        log.warning("Falha ao baixar imagem %s: %s", url, exc)
        return None
    except Exception:
        log.exception("Erro inesperado ao baixar imagem %s", url)
        return None


def montar_payload_imagem(
    dados: bytes,
    *,
    caixa: tuple[int, int, int, int] | None = None,
    fundo: tuple[int, int, int] = (255, 255, 255),
) -> bytes | None:
    """Converte bytes de imagem (JPEG/PNG/…) no payload de IDvShowImg.

    Formato exigido pelo manual TC506-Mídia:
        768 bytes de paleta RGB (256 cores × 3) + 480×272 bytes de índices.

    `caixa` = (x, y, largura, altura) da região onde a foto deve aparecer.
    O restante da tela fica preenchido com `fundo` (a cor da tela do layout),
    para o IDvShowImg não pintar o fundo de branco por cima do DispClear.
    Sem caixa, a foto ocupa a tela inteira (letterbox na mesma cor).
    """
    try:
        from PIL import Image
    except ImportError:
        log.warning(
            "Pillow não instalado — não é possível enviar imagem pelo SC504. "
            "Instale com: pip install Pillow"
        )
        return None

    try:
        img = Image.open(io.BytesIO(dados))
        # PNG com alpha: fundo branco (não preto do convert RGB cru)
        try:
            from arauto.core.product_image import imagem_rgb_fundo
            img = imagem_rgb_fundo(img, fundo if isinstance(fundo, tuple) else (255, 255, 255))
        except Exception:
            img = img.convert("RGB")

        canvas = Image.new("RGB", (IMG_LARGURA, IMG_ALTURA), fundo)

        if caixa is not None:
            bx, by, bw, bh = caixa
            bw = max(1, min(bw, IMG_LARGURA - max(0, bx)))
            bh = max(1, min(bh, IMG_ALTURA - max(0, by)))
            bx = max(0, min(bx, IMG_LARGURA - 1))
            by = max(0, min(by, IMG_ALTURA - 1))
            # Encaixa a foto dentro da caixa mantendo proporção.
            foto = img.copy()
            foto.thumbnail((bw, bh), Image.Resampling.LANCZOS)
            ox = bx + (bw - foto.width) // 2
            oy = by + (bh - foto.height) // 2
            canvas.paste(foto, (ox, oy))
        else:
            # Tela cheia com letterbox na cor de fundo.
            img.thumbnail((IMG_LARGURA, IMG_ALTURA), Image.Resampling.LANCZOS)
            ox = (IMG_LARGURA - img.width) // 2
            oy = (IMG_ALTURA - img.height) // 2
            canvas.paste(img, (ox, oy))

        quantizada = canvas.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        paleta_raw = quantizada.getpalette()
        if not paleta_raw:
            return None
        paleta = bytes(paleta_raw[:768]).ljust(768, b"\x00")
        pixels = quantizada.tobytes()
        if len(pixels) != IMG_PIXELS:
            pixels = pixels[:IMG_PIXELS].ljust(IMG_PIXELS, b"\x00")
        return paleta + pixels
    except Exception:
        log.exception("Falha ao converter imagem para IDvShowImg")
        return None


def _caixa_imagem_do_layout(modelo: int | None) -> tuple[int, int, int, int] | None:
    """Lê o elemento 'imagem' do layout. None = tela cheia ou desligado."""
    layout = get_layouts().obter(modelo)
    el = layout.elementos.get("imagem")
    if el is None or not el.visivel:
        return None
    if el.largura <= 0 or el.altura <= 0:
        # visível sem tamanho → ocupa a tela inteira
        return (0, 0, layout.largura, layout.altura)
    return (el.x if el.x >= 0 else 0, el.y, el.largura, el.altura)


def obter_payload_imagem(codigo: str, modelo: int | None = None) -> bytes | None:
    """Local/cache → fallback HTTP → conversão IDvShowImg."""
    from ..core.layout import rgb_cor

    layout = get_layouts().obter(modelo)
    el_img = layout.elementos.get("imagem")
    if el_img is None or not el_img.visivel:
        return None

    caixa = _caixa_imagem_do_layout(modelo)
    fundo = rgb_cor(layout.cor_tela, (255, 255, 255))
    chave_cache = f"{codigo}|{caixa}|{layout.cor_tela}"

    with _CACHE_LOCK:
        if chave_cache in _CACHE_IMAGENS:
            return _CACHE_IMAGENS[chave_cache]

    bruto = None
    fonte = "local"
    try:
        from ..core.product_image import obter_bytes_produto
        bruto = obter_bytes_produto(codigo)
    except Exception:
        log.debug("product_image.obter_bytes_produto falhou", exc_info=True)

    if not bruto:
        url = _url_imagem_produto(codigo)
        if not url:
            return None
        fonte = url
        bruto = _baixar_bytes(url)
    if not bruto:
        return None
    payload = montar_payload_imagem(bruto, caixa=caixa, fundo=fundo)
    if payload is None:
        return None

    with _CACHE_LOCK:
        if len(_CACHE_IMAGENS) >= _CACHE_IMAGENS_MAX:
            _CACHE_IMAGENS.pop(next(iter(_CACHE_IMAGENS)), None)
        _CACHE_IMAGENS[chave_cache] = payload
    log.info(
        "Imagem do produto %s pronta (%d bytes, caixa=%s) a partir de %s",
        codigo, len(payload), caixa, fonte,
    )
    return payload


class Sc504Connection(threading.Thread):
    def __init__(self, sock: socket.socket, endereco: tuple[str, int],
                 service: QueryService, servidor: "Sc504Server") -> None:
        super().__init__(name=f"sc504-{endereco[0]}:{endereco[1]}", daemon=True)
        self.sock = sock
        self.endereco = endereco
        self.service = service
        self.servidor = servidor
        self.peer = f"{endereco[0]}:{endereco[1]}"
        self.buffer = bytearray()
        self.formato = servidor.formato
        self.debug = servidor.debug
        self.passivo = servidor.passivo
        self._media_lock = threading.Lock()
        self._media_waiters: dict[int, list] = {}
        # Registro imediato: plugins precisam da conexão viva
        try:
            self.servidor.conexoes[self.peer] = self
        except Exception:
            pass
        self.bruto = bytearray()   # captura da sessão, para diagnóstico
        self.identificado = False
        self.tipo_terminal: int | None = None
        self.largura, self.altura = LAYOUT_LARGURA, LAYOUT_ALTURA
        self.versao = ""
        self.mac = ""
        self.nome_aparelho = ""
        self.parar = threading.Event()
        self._keepalive: threading.Thread | None = None
        self.terminal = service.terminal_connected(self.peer)
        self.terminal.model = "SC504 (não identificado)"

    # ------------------------------------------------------------------- io
    def enviar(self, identificador: int, dados: bytes = b"") -> None:
        if self.passivo:
            log.info("[passivo] não enviando id=%d para %s", identificador, self.peer)
            MONITOR.nota("SC504", self.peer,
                         f"modo passivo: envio de id={identificador} suprimido")
            return
        quadro = montar(identificador, dados, self.formato)
        try:
            self.sock.sendall(quadro)
            nome = NOMES.get(identificador - 1, "")
            MONITOR.enviado("SC504", self.peer, quadro,
                            f"id={identificador} {'R_' + nome if nome else ''}")
            log.info("ENVIADO -> %s  id=%d %s (%d bytes)\n%s", self.peer,
                     identificador, f"R_{nome}" if nome else "", len(quadro),
                     hexdump(quadro))
        except OSError as exc:
            log.debug("Falha ao escrever para %s: %s", self.peer, exc)

    def run(self) -> None:
        log.info("Terminal SC504 conectado: %s", self.peer)
        MONITOR.nota("SC504", self.peer, "conectado")
        self.sock.settimeout(120)
        try:
            if not self.passivo:
                self.enviar(ID_W_GET_IDENTIFY)  # pergunta quem é ao conectar
            while not self.servidor.parando:
                try:
                    pedaco = self.sock.recv(4096)
                except socket.timeout:
                    self.enviar(ID_V_LIVE)  # keep-alive
                    continue
                if not pedaco:
                    break
                self.bruto.extend(pedaco)
                MONITOR.recebido("SC504", self.peer, pedaco)
                # Sempre no log, sem depender de sinalizador: quando o terminal
                # manda algo inesperado é justamente quando não se pode ficar
                # sem informação.
                log.info("RECEBIDO <- %s  %d bytes:\n%s",
                         self.peer, len(pedaco), hexdump(pedaco))
                self.buffer.extend(pedaco)
                try:
                    self._drenar()
                except Exception:
                    log.exception("Erro ao processar quadro de %s", self.peer)
        except OSError as exc:
            log.debug("Conexão %s encerrada: %s", self.peer, exc)
        except Exception:
            log.exception("Erro na sessão SC504 %s", self.peer)
        finally:
            self.fechar()

    def _drenar(self) -> None:
        """Extrai quadros completos do buffer, resincronizando se preciso."""
        _, cabecalho = FORMATOS.get(self.formato, FORMATOS[FORMATO_PADRAO])

        while True:
            if len(self.buffer) < cabecalho:
                return

            campos = desmontar(bytes(self.buffer), self.formato)
            if campos is None:
                return
            stx, identificador, tamanho = campos

            if stx != STX:
                if not self._resincronizar():
                    return
                continue

            if tamanho > MAX_DADOS:
                log.error(
                    "Tamanho de dados absurdo (%d) vindo de %s. O enquadramento "
                    "configurado (%s) provavelmente não é o do seu terminal. "
                    "Rode: python run.py --sniffer %d",
                    tamanho, self.peer, self.formato, self.servidor.port,
                )
                self._diagnosticar("tamanho inválido")
                self.buffer.clear()
                return

            if len(self.buffer) < cabecalho + tamanho:
                return  # quadro ainda incompleto; espera o resto

            dados = bytes(self.buffer[cabecalho:cabecalho + tamanho])
            del self.buffer[:cabecalho + tamanho]
            self.tratar(identificador, dados)

    def _resincronizar(self) -> bool:
        """Procura o próximo STX. Devolve False se não houver mais nada útil."""
        pos = bytes(self.buffer).find(bytes([STX]), 1)
        if pos == -1:
            self._diagnosticar("nenhum STX encontrado")
            self.buffer.clear()
            return False
        log.warning("Resincronizando quadro de %s (%d byte(s) descartado(s))",
                    self.peer, pos)
        del self.buffer[:pos]
        return True

    def _diagnosticar(self, motivo: str) -> None:
        """Diante de bytes que não entendemos, mostra o que chegou.

        Descartar em silêncio era o comportamento da versão 1.0 e não deixava
        pista nenhuma de por que o terminal não funcionava. Aqui despejamos o
        início do buffer e rodamos as hipóteses de enquadramento.
        """
        amostra = bytes(self.buffer[:256])
        log.error(
            "Quadro não reconhecido de %s (%s) — %d bytes no buffer, "
            "enquadramento configurado: %s\n%s",
            self.peer, motivo, len(self.buffer), self.formato, hexdump(amostra),
        )
        try:
            melhor = analisar(bytes(self.bruto))[0]
            if melhor.completo:
                log.error(
                    "O enquadramento que explica esta captura é '%s' (%s). "
                    "Ajuste SC504_FRAME em /config e reinicie.",
                    melhor.hipotese.nome, melhor.hipotese.descricao,
                )
            else:
                log.error(
                    "Nenhuma hipótese conhecida explica a captura. Rode "
                    "'python run.py --sniffer %d', reproduza a consulta e "
                    "guarde o arquivo gerado.", self.servidor.port,
                )
        except Exception:
            log.exception("Falha ao analisar o enquadramento")

    # -------------------------------------------------------------- comandos

    def _esperar_resposta(self, id_resp: int, timeout: float = 30.0):
        import queue
        q: queue.Queue = queue.Queue(maxsize=1)
        with self._media_lock:
            self._media_waiters.setdefault(id_resp, []).append(q)
        try:
            return q.get(timeout=timeout)
        except Exception:
            return None
        finally:
            with self._media_lock:
                lst = self._media_waiters.get(id_resp) or []
                if q in lst:
                    lst.remove(q)

    def _entregar_resposta(self, identificador: int, dados: bytes) -> bool:
        with self._media_lock:
            lst = self._media_waiters.get(identificador) or []
            if not lst:
                return False
            q = lst.pop(0)
        try:
            q.put_nowait(dados)
        except Exception:
            return False
        return True

    def receber_arquivo(self, path: str, timeout: float = 30.0) -> bytes | None:
        """Pede arquivo do terminal (ID 97) e devolve o conteúdo bruto.

        A resposta (ID 98) traz nome(128) + status(int LE) + bytes. Só
        devolvemos o conteúdo se ``status == 1``.
        """
        from . import sc504_media as media
        self.enviar(ID_V_RECV_FILE, media.campo_nome(path))
        dados = self._esperar_resposta(R_ID_V_RECV_FILE, timeout=timeout)
        if dados is None:
            return None
        _nome, ok, conteudo = media.ler_resposta_arquivo(dados)
        if not ok:
            log.warning("RecvFile %s em %s: status != 1", path, self.peer)
            return None
        return conteudo

    def enviar_arquivo(self, path: str, conteudo: bytes, timeout: float = 60.0) -> bool:
        """Envia arquivo ao terminal (ID 99): nome(128) + bytes."""
        from . import sc504_media as media
        payload = media.campo_nome(path) + (conteudo or b"")
        self.enviar(ID_V_SEND_FILE, payload)
        ack = self._esperar_resposta(R_ID_V_SEND_FILE, timeout=timeout)
        return ack is not None

    def apagar_arquivo(self, path: str, timeout: float = 15.0) -> bool:
        """Apaga mídia no terminal (ID 184): caminho ASCII sem padding."""
        from . import sc504_media as media
        self.enviar(ID_V_DELETE_FILE, media.path_bytes(path))
        ack = self._esperar_resposta(R_ID_V_DELETE_FILE, timeout=timeout)
        return ack is not None

    def limpar_memoria_midias(self, timeout: float = 30.0) -> bool:
        """Apaga toda a mídia da memória interna (ID 186) e zera as playlists.

        Sequência observada no TC Server / captura real:
        1. ID_V_DELETE_ALL_MEDIAS (186)
        2. ID_V_UPDATE_MEDIAS (117)
        3. medias.conf e presence_sensor.conf vazios (``<\\n>``)
        4. all_medias.conf só com ``[INT_MEM]``
        5. ID_V_UPDATE_MEDIAS de novo
        """
        from . import sc504_media as media

        self.enviar(ID_V_DELETE_ALL_MEDIAS)
        ack = self._esperar_resposta(R_ID_V_DELETE_ALL_MEDIAS, timeout=timeout)
        if ack is None:
            log.warning("limpar_memoria_midias %s: sem ACK do ID 186", self.peer)
            return False
        self.atualizar_midias(timeout=timeout)
        vazio = media.montar_playlist([])  # "<\n>"
        inv = media.montar_inventario([]) or "[INT_MEM]\n"
        for arq, conteudo in (
            (media.ARQ_SENSOR, vazio),
            (media.ARQ_PLAYLIST, vazio),
            (media.ARQ_INVENTARIO, inv),
        ):
            try:
                self.enviar_arquivo(arq, conteudo.encode(media.CHARSET, errors="replace"))
            except Exception:
                log.exception("limpar %s em %s", arq, self.peer)
        self.atualizar_midias(timeout=timeout)
        log.info("Memória de mídia limpa em %s", self.peer)
        MONITOR.nota("SC504", self.peer, "memória de mídia limpa (ID 186)")
        return True

    def atualizar_midias(self, timeout: float = 15.0) -> bool:
        """Recarrega lista de mídias / propaganda (ID 117 ReloadADV)."""
        self.enviar(ID_V_UPDATE_MEDIAS)
        ack = self._esperar_resposta(R_ID_V_UPDATE_MEDIAS, timeout=timeout)
        return ack is not None

    def ler_estado_midia(self, timeout: float = 30.0):
        """Lê inventário + playlists e devolve EstadoTerminal."""
        from . import sc504_media as media
        estado = media.EstadoTerminal(
            peer=self.peer,
            modelo=getattr(self.terminal, "model", "") or "",
        )
        try:
            inv = self.receber_arquivo(media.ARQ_INVENTARIO, timeout=timeout)
            if inv is not None:
                estado.inventario = media.analisar_inventario(
                    inv.decode(media.CHARSET, errors="replace")
                )
            pl = self.receber_arquivo(media.ARQ_PLAYLIST, timeout=timeout)
            if pl is not None:
                estado.playlist = media.analisar_playlist(
                    pl.decode(media.CHARSET, errors="replace")
                )
            sen = self.receber_arquivo(media.ARQ_SENSOR, timeout=timeout)
            if sen is not None:
                estado.sensor = media.analisar_playlist(
                    sen.decode(media.CHARSET, errors="replace")
                )
        except Exception as exc:
            estado.erro = str(exc)
            log.exception("ler_estado_midia %s", self.peer)
        return estado

    def tratar(self, identificador: int, dados: bytes) -> None:
        nome = NOMES.get(identificador, f"desconhecido({identificador})")
        log.debug("<- %s %s (%d bytes)", self.peer, nome, len(dados))
        self.terminal.last_seen = time.time()

        if identificador in (
            R_ID_V_RECV_FILE, R_ID_V_SEND_FILE,
            R_ID_V_UPDATE_MEDIAS, R_ID_V_DELETE_FILE,
            R_ID_V_DELETE_ALL_MEDIAS,
        ):
            if self._entregar_resposta(identificador, dados):
                return

        if identificador == ID_B_READ_SCANNER:
            self.ler_codigo(dados)
            return

        if identificador == R_ID_W_GET_IDENTIFY:
            self.identificar(dados)
            return

        if identificador == R_ID_V_GET_UID:
            self.receber_uid(dados)
            return

        if identificador == ID_W_GET_IDENTIFY:
            # O terminal perguntando quem somos: só confirmamos.
            self.enviar(R_ID_W_GET_IDENTIFY)
            return

        if identificador == ID_V_LIVE:
            self.enviar(R_ID_V_LIVE)
            return
        if identificador == R_ID_V_LIVE:
            return  # é a resposta ao nosso próprio keep-alive

        if identificador == ID_V_ALWAYS_LIVE:
            self.enviar(R_ID_V_ALWAYS_LIVE, dword(1))
            return

        if identificador == ID_CONTINUE:
            self.enviar(R_ID_CONTINUE, dword(1))
            return
        if identificador == R_ID_CONTINUE:
            log.info("Terminal %s confirmou o handshake", self.peer)
            return

        if identificador == ID_QUERY_PROCESS_FAILURE:
            log.warning("Terminal %s reportou falha no processamento", self.peer)
            return

        # Resposta do terminal a um comando nosso: nada a fazer.
        if identificador in RESPOSTAS and identificador not in REQUISICOES:
            return

        if identificador in REQUISICOES:
            # Requisição conhecida mas não implementada: confirma para não
            # travar a máquina de estados do terminal.
            log.info("Comando SC504 não tratado de %s: %s", self.peer, nome)
            self.enviar(identificador + 1)
            return

        log.warning("Identificador SC504 desconhecido de %s: %d", self.peer, identificador)

    def identificar(self, dados: bytes) -> None:
        """RIDwGetIdentify: `0x31` + termType (short BIG-ENDIAN) + versão.

        Confirmado no `getData` do JAR: `put(49)`, `putShort(termType,
        BIG_ENDIAN)`, `put(...)`. Numa captura real veio `31 01 fa 50`, ou seja
        termType = 0x01FA = 506 = TC-506 Mídia. Ler little-endian a partir do
        byte 0 (o que esta implementação fazia) dava 305 e nunca casava.
        """
        if len(dados) < 3:
            log.warning("RIDwGetIdentify de %s com só %d byte(s):\n%s",
                        self.peer, len(dados), hexdump(dados))
            return

        if dados[0] != MARCADOR_IDENTIFY:
            log.warning("RIDwGetIdentify de %s sem o marcador 0x31:\n%s",
                        self.peer, hexdump(dados))

        tipo = struct.unpack(">H", dados[1:3])[0]
        # A versão vem em dígitos hexadecimais lidos como decimais (hexToDec).
        self.versao = "".join(f"{b:02X}" for b in dados[3:]).lstrip("0") or "0"

        if tipo not in MODELOS:
            log.warning(
                "Terminal %s informou termType %d, fora da tabela %s. "
                "Seguindo mesmo assim; o modelo será confirmado pelo UID.",
                self.peer, tipo, sorted(MODELOS),
            )
            nome, largura, altura = f"SC504 tipo {tipo}", 480, 272
        else:
            nome, largura, altura = MODELOS[tipo]

        self.tipo_terminal = tipo
        self.terminal.tipo = tipo
        self.largura, self.altura = largura, altura
        self.terminal.model = f"{nome} v{self.versao}".strip()
        log.info("Terminal %s identificado: %s (tela %dx%d, versão %s)",
                 self.peer, nome, largura, altura, self.versao)

        # Handshake: sem este IDContinue o terminal não se dá por conectado.
        self.enviar(ID_CONTINUE, dword(1))
        self.identificado = True
        MONITOR.nota("SC504", self.peer, f"handshake concluído — {nome}")

        # O original pergunta o UID logo em seguida: é de lá que sai o nome
        # exato do aparelho ("TC506-Media") e o MAC.
        self.enviar(ID_V_GET_UID)

        # E passa a mandar keep-alive a cada 10 s, que é o que sustenta o
        # estado "conectado" no display.
        self.iniciar_keepalive()

    def receber_uid(self, dados: bytes) -> None:
        """R_ID_V_GET_UID (id 28): ARG_UID — 6 bytes MAC + 32 bytes nome do aparelho.

        É a forma estável de identificar o terminal (IP pode mudar; MAC não).
        Prefixo OUI Gertec típico: 00:1D:5B.
        """
        if len(dados) < 6:
            log.warning("R_ID_V_GET_UID de %s com só %d byte(s):\n%s",
                        self.peer, len(dados), hexdump(dados))
            return
        self.mac = ":".join(f"{b:02X}" for b in dados[:6])
        nome = ""
        if len(dados) >= 7:
            nome = dados[6:38].split(b"\x00")[0].decode(CHARSET, errors="replace").strip()
        if nome:
            self.nome_aparelho = nome
            self.terminal.model = f"{nome} v{self.versao}".strip() if self.versao else nome
        # propaga para TerminalInfo (status/API/plugins)
        try:
            self.terminal.mac = self.mac
            self.terminal.nome_aparelho = self.nome_aparelho or nome
        except Exception:
            pass
        log.info("Terminal %s: %s (MAC %s)", self.peer,
                 self.nome_aparelho or "?", self.mac)
        MONITOR.nota("SC504", self.peer,
                     f"UID: {self.nome_aparelho or '?'} MAC {self.mac}")

    def iniciar_keepalive(self) -> None:
        if self._keepalive is not None:
            return

        def laco() -> None:
            while not self.parar.wait(INTERVALO_LIVE):
                self.enviar(ID_V_LIVE)

        self._keepalive = threading.Thread(
            target=laco, name=f"sc504-live-{self.peer}", daemon=True)
        self._keepalive.start()

    def ler_codigo(self, dados: bytes) -> None:
        """IDbReadScanner → ArgSerialData: `codeLen` (short) + `code`.

        O comprimento vem num campo próprio de 2 bytes; o resto do buffer é
        memória não inicializada do terminal e precisa ser ignorado.
        """
        codigo = self._extrair_codigo(dados)
        if not codigo:
            log.warning("IDbReadScanner de %s sem código utilizável:\n%s",
                        self.peer, hexdump(dados[:48]))
            self.enviar(R_ID_B_READ_SCANNER)
            return

        log.info("Código lido por %s: %s", self.peer, codigo)
        self.terminal.queries += 1
        self.terminal.last_barcode = codigo
        resultado = self.service.query(codigo, origin=self.peer,
                                       channel="terminal-504")

        self.enviar(R_ID_B_READ_SCANNER)   # confirma o recebimento do código
        self.mostrar_resultado(resultado)

    @staticmethod
    def _extrair_codigo(dados: bytes) -> str:
        """Extrai o código do ArgSerialData, com recuo se o campo não bater."""
        if len(dados) >= 2:
            tamanho = struct.unpack("<H", dados[:2])[0]
            if 0 < tamanho <= CODE_MAX_LENGTH and len(dados) >= 2 + tamanho:
                bruto = dados[2:2 + tamanho]
                texto = bruto.decode(CHARSET, errors="replace").strip()
                if texto:
                    return texto
        # Recuo: alguns firmwares podem mandar o código puro. Pega a primeira
        # sequência imprimível em vez de devolver vazio silenciosamente.
        legivel = "".join(chr(b) if 32 <= b < 127 else "\x00" for b in dados)
        candidatos = [p.strip() for p in legivel.split("\x00") if p.strip()]
        return candidatos[0][:CODE_MAX_LENGTH] if candidatos else ""

    def mostrar_resultado(self, resultado) -> None:
        """Limpa tela → textos (rápido) → imagem por último (best-effort).

        A imagem pode demorar (disco/HTTP/quantização). Mandar o preço antes
        evita a sensação de travamento na leitura do código.
        """
        try:
            layout = get_layouts().obter(self.tipo_terminal)
        except Exception:
            log.exception("Layout indisponível para %s", self.peer)
            return

        try:
            self.enviar(ID_V_DISP_CLEAR, word(layout.cor_tela))
        except Exception:
            log.exception("Falha ao limpar tela em %s", self.peer)

        try:
            for texto, x, y, tamanho, fonte in linhas_para_display(
                    resultado, self.tipo_terminal):
                self.enviar(ID_V_SHOW_TEXT, montar_texto_display(
                    texto, x, y, fonte, tamanho,
                    layout.cor_texto, layout.cor_fundo_texto))
        except Exception:
            log.exception("Falha ao enviar textos para %s", self.peer)

        # Imagem por último: se falhar ou demorar, o terminal já mostra o preço.
        if getattr(resultado, "found", False):
            try:
                payload_img = obter_payload_imagem(
                    getattr(resultado, "barcode", "") or "",
                    modelo=self.tipo_terminal,
                )
                if payload_img:
                    self.enviar(ID_V_SHOW_IMG, payload_img)
            except Exception:
                log.exception(
                    "Falha ao enviar imagem do produto %s para %s — textos já foram enviados",
                    getattr(resultado, "barcode", "?"), self.peer,
                )


    def fechar(self) -> None:
        self.parar.set()
        MONITOR.nota("SC504", self.peer,
                     f"desconectado após {len(self.bruto)} byte(s) recebidos")
        if self.bruto:
            # A análise no encerramento é a última chance de dizer algo útil
            # sobre uma sessão que não funcionou.
            try:
                melhor = analisar(bytes(self.bruto))[0]
                log.info("Sessão %s encerrada. Melhor hipótese de enquadramento: "
                         "%s (%.0f%% do tráfego explicado, %d quadro(s), ids %s)",
                         self.peer, melhor.hipotese.nome, melhor.pontuacao * 100,
                         melhor.quadros, melhor.ids[:10])
            except Exception:
                log.exception("Falha ao analisar a sessão")
        try:
            self.servidor.conexoes.pop(self.peer, None)
        except Exception:
            pass
        self.service.terminal_disconnected(self.peer)
        try:
            self.sock.close()
        except OSError:
            pass
        log.info("Terminal SC504 desconectado: %s", self.peer)


class Sc504Server(threading.Thread):
    def __init__(self, service: QueryService, host: str = "0.0.0.0",
                 port: int = 16510, formato: str = FORMATO_PADRAO,
                 debug: bool = False, passivo: bool = PASSIVO_PADRAO) -> None:
        super().__init__(name="sc504-server", daemon=True)
        self.service = service
        self.host = host
        self.port = port
        self.formato = formato if formato in FORMATOS else FORMATO_PADRAO
        self.debug = debug
        self.passivo = passivo
        self.parando = False
        self._sock: socket.socket | None = None
        self.conexoes: dict[str, "Sc504Connection"] = {}

    def run(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind((self.host, self.port))
        except OSError as exc:
            from arauto.core.netutil import log_falha_porta
            log_falha_porta(log, "SC504", self.port, exc, host=self.host)
            return
        self._sock.listen(64)
        log.info("Servidor SC504 escutando em %s:%s (enquadramento %s%s)",
                 self.host, self.port, self.formato,
                 ", MODO PASSIVO" if self.passivo else "")
        while not self.parando:
            try:
                cliente, endereco = self._sock.accept()
            except OSError:
                break
            conn = Sc504Connection(cliente, endereco, self.service, self)
            self.conexoes[f"{endereco[0]}:{endereco[1]}"] = conn
            conn.start()

    def stop(self) -> None:
        self.parando = True
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass


