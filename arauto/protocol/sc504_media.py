"""Protocolo de gerência de mídia do TC-506 Mídia.

Todo o formato abaixo foi extraído de uma captura real do TC Server original
(``--proxy``), em que se fez upload de uma imagem, exclusão dela e gravação da
sequência de propaganda. O manual de desenvolvimento da Gertec confirma os
comandos; a captura deu os detalhes que o manual não escreve.

Comandos usados
---------------

    97  IDvRecvFile     servidor pede um arquivo ao terminal
    98  resposta        nome(128) + status(int LE) + bytes do arquivo
    99  IDvSendFile     servidor envia arquivo: nome(128) + bytes
   100  resposta        dword 1 = gravado
   117  IDReloadADV     recarrega a lista de mídias
   118  resposta        dword 1
   184  apagar mídia    caminho em ASCII **sem** preenchimento
   185  resposta        dword 1

Arquivos de configuração do aparelho
------------------------------------

    CONF_DIR/all_medias.conf         inventário do que está gravado
    CONF_DIR/medias.conf             playlist principal (propaganda)
    CONF_DIR/presence_sensor.conf    playlist do sensor de presença
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

# --- identificadores ---
ID_RECV_FILE = 97
ID_SEND_FILE = 99
ID_RELOAD_ADV = 117
ID_DELETE_MEDIA = 184

R_RECV_FILE = 98
R_SEND_FILE = 100
R_RELOAD_ADV = 118
R_DELETE_MEDIA = 185

# ARG_FILENAME e ARG_GETFILENAME têm 128 bytes de nome (manual).
TAM_NOME = 128
CHARSET = "latin-1"

ARQ_INVENTARIO = "CONF_DIR/all_medias.conf"
ARQ_PLAYLIST = "CONF_DIR/medias.conf"
ARQ_SENSOR = "CONF_DIR/presence_sensor.conf"

DESTINOS = ("INT_MEM", "SDCARD1")

# Formatos aceitos pelo terminal, conforme o manual.
EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
EXT_ANIMACAO = {".gif"}
EXT_AUDIO = {".mp3"}
EXT_VIDEO = {".avi"}
EXT_ACEITAS = EXT_IMAGEM | EXT_ANIMACAO | EXT_AUDIO | EXT_VIDEO


def campo_nome(caminho: str) -> bytes:
    """ARG_FILENAME: nome em buffer fixo de 128 bytes, preenchido com zero."""
    bruto = caminho.encode(CHARSET, errors="replace")[:TAM_NOME]
    return bruto.ljust(TAM_NOME, b"\x00")


def path_bytes(caminho: str) -> bytes:
    """Caminho em ASCII sem preenchimento (comando apagar)."""
    return (caminho or "").encode(CHARSET, errors="replace")


def ler_resposta_arquivo(dados: bytes) -> tuple[str, bool, bytes]:
    """Decompõe ARG_GETFILENAME: nome(128) + status(int LE) + conteúdo."""
    if len(dados) < TAM_NOME + 4:
        return "", False, b""
    nome = dados[:TAM_NOME].split(b"\x00")[0].decode(CHARSET, errors="replace")
    status = struct.unpack("<i", dados[TAM_NOME:TAM_NOME + 4])[0]
    return nome, status == 1, dados[TAM_NOME + 4:]


def tipo_da_extensao(nome: str) -> str:
    ext = ("." + nome.rsplit(".", 1)[-1]).lower() if "." in nome else ""
    if ext in EXT_ANIMACAO:
        return "animacao"
    if ext in EXT_AUDIO:
        return "audio"
    if ext in EXT_VIDEO:
        return "video"
    if ext in EXT_IMAGEM:
        return "imagem"
    return "desconhecido"


# --------------------------------------------------------------- inventário
def analisar_inventario(texto: str) -> list[dict]:
    """Lê ``all_medias.conf``.

    Formato observado::

        [INT_MEM]
        media1=bmp1.bmp
        media2=bmp2.bmp

    O cabeçalho entre colchetes é o destino (memória interna ou cartão), e vale
    para as linhas seguintes até o próximo cabeçalho.
    """
    itens: list[dict] = []
    destino = "INT_MEM"
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("[") and linha.endswith("]"):
            destino = linha[1:-1].strip() or destino
            continue
        if "=" not in linha:
            continue
        chave, _, arquivo = linha.partition("=")
        arquivo = arquivo.strip()
        if not arquivo:
            continue
        itens.append({
            "chave": chave.strip(),
            "arquivo": arquivo,
            "destino": destino,
            "caminho": f"{destino}/{arquivo}",
            "tipo": tipo_da_extensao(arquivo),
        })
    return itens


def montar_inventario(itens: list[dict]) -> str:
    """Gera ``all_medias.conf`` a partir da lista de ``analisar_inventario``."""
    por: dict[str, list[dict]] = {}
    for it in itens:
        por.setdefault(it.get("destino") or "INT_MEM", []).append(it)
    linhas: list[str] = []
    for destino, lista in por.items():
        linhas.append(f"[{destino}]")
        for i, it in enumerate(lista, 1):
            chave = it.get("chave") or f"media{i}"
            arquivo = it.get("arquivo") or ""
            if arquivo:
                linhas.append(f"{chave}={arquivo}")
    return "\n".join(linhas) + ("\n" if linhas else "")


# ----------------------------------------------------------------- playlist
@dataclass
class ItemPlaylist:
    """Uma linha de ``medias.conf``.

    Duas formas, segundo o manual:

        |caminho|tempo|vezes|           mídia simples
        |audio|tempo|vezes|imagem|      áudio com imagem de fundo

    ``tempo`` só vale para imagem estática (segundos na tela); ``vezes`` é o
    número de ciclos para animação, áudio e vídeo.
    """
    caminho: str
    tempo: int = 5
    vezes: int = 1
    imagem_fundo: str = ""

    def to_dict(self) -> dict:
        return {
            "caminho": self.caminho,
            "tempo": self.tempo,
            "vezes": self.vezes,
            "imagem_fundo": self.imagem_fundo,
            "tipo": tipo_da_extensao(self.caminho),
            # aliases para a UI do plugin
            "path": self.caminho,
            "loops": self.vezes,
        }

    def linha(self) -> str:
        base = f"|{self.caminho}|{self.tempo}|{self.vezes}|"
        return base + f"{self.imagem_fundo}|" if self.imagem_fundo else base


def analisar_playlist(texto: str) -> list[ItemPlaylist]:
    """Lê ``medias.conf`` / ``presence_sensor.conf``."""
    itens: list[ItemPlaylist] = []
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if not linha or linha in ("<", ">"):
            continue
        partes = [p for p in linha.split("|")]
        # `|a|b|c|` produz ['', 'a', 'b', 'c', '']
        partes = [p.strip() for p in partes if p.strip() != ""] if linha.count("|") >= 2 else []
        if not partes:
            continue
        caminho = partes[0]
        tempo = _inteiro(partes[1] if len(partes) > 1 else "5", 5)
        vezes = _inteiro(partes[2] if len(partes) > 2 else "1", 1)
        fundo = partes[3] if len(partes) > 3 else ""
        itens.append(ItemPlaylist(caminho, tempo, vezes, fundo))
    return itens


def montar_playlist(itens: list[ItemPlaylist]) -> str:
    """Gera o texto de ``medias.conf``.

    A captura mostra o arquivo abrindo com ``<`` e fechando com ``>``, uma linha
    por mídia, com quebra ``\n`` (não ``\r\n``).

    Sem quebra após o ``>``: o arquivo do TC Server original termina exatamente
    aqui, e reproduzimos byte a byte em vez de contar com a tolerância do
    firmware.
    """
    linhas = ["<"]
    linhas += [item.linha() for item in itens]
    linhas.append(">")
    return "\n".join(linhas)


def _inteiro(valor: str, padrao: int) -> int:
    try:
        return max(0, int(str(valor).strip()))
    except (TypeError, ValueError):
        return padrao


# ------------------------------------------------------------------- nomes
_SEGURO = re.compile(r"[^A-Za-z0-9._-]+")


def nome_seguro(nome: str) -> str:
    """Normaliza o nome do arquivo antes de gravar no terminal.

    O aparelho aceita acentos (a captura tinha ``Sem Título-1.jpg``), mas nomes
    com espaço e acento complicam a edição manual do ``medias.conf`` e a
    depuração. Normalizamos na subida.
    """
    nome = (nome or "").strip().replace('\\', "/").rsplit("/", 1)[-1]
    if "." in nome:
        base, _, ext = nome.rpartition(".")
    else:
        base, ext = nome, ""
    base = _SEGURO.sub("_", base).strip("_") or "midia"
    ext = _SEGURO.sub("", ext).lower()
    return f"{base}.{ext}" if ext else base


@dataclass
class EstadoTerminal:
    """Retrato do que está gravado num terminal."""
    peer: str
    modelo: str = ""
    inventario: list[dict] = field(default_factory=list)
    playlist: list[ItemPlaylist] = field(default_factory=list)
    sensor: list[ItemPlaylist] = field(default_factory=list)
    erro: str = ""

    def to_dict(self) -> dict:
        return {
            "peer": self.peer,
            "modelo": self.modelo,
            "inventario": self.inventario,
            "playlist": [i.to_dict() for i in self.playlist],
            "sensor": [i.to_dict() for i in self.sensor],
            "erro": self.erro,
        }


