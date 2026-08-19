"""Servidor do protocolo SC501 (terminais Gertec Busca Preço).

ATENÇÃO — este módulo foi reconstruído por engenharia reversa das constantes do
JAR original (`Sc501CommDefs`, `Sc501CommandBuilder`, `ProductResponse`). Os
identificadores de comando e o formato da resposta de produto conferem com o
que está compilado no JAR, mas o enquadramento exato de alguns comandos de
configuração e mídia não pôde ser verificado sem um terminal real na bancada.

Valide contra hardware antes de colocar em produção. Consulta de preço,
identificação de terminal e keep-alive são a parte crítica e estão implementados
por completo.

Formato observado: comandos ASCII (ISO-8859-1) terminados em NUL. Qualquer
payload que não bata com um comando conhecido é tratado como código de barras,
que é exatamente o que o `Sc501CommandBuilder` faz.
"""

from __future__ import annotations

import logging
import socket
import threading
import time

from ..core.service import QueryService
from .monitor import MONITOR, hexdump

log = logging.getLogger("arauto.sc501")

CHARSET = "ISO-8859-1"
TERM = b"\x00"
# Captura do TC Server original com Busca Preço G2: keep-alive a cada ~10 s.
INTERVALO_LIVE = 10.0
# O original envia literalmente `#macaddr?9` (10 bytes). O "9" não está no
# manual, mas o terminal G2 responde a ele; sem isso o handshake diverge.
CMD_MAC_Q_G2 = "#macaddr?9"
CMD_UPDCONFIG_Q = "#updconfig?"

# Identificação enviada pelo terminal ao conectar -> nome comercial
TERMINAL_IDS = {
    "#tc406": "TC-406",
    "#tc406e": "TC-406 E",
    "#tc300": "TC-300",
    "#tc502": "TC-502",
    "#tc505": "TC-505",
    "#tc507": "TC-507",
    "#tc506s": "TC-506 S",
    "#tc506e": "TC-506 E",
    "#bpg2e": "Busca Preço G2 E",
}

CMD_OK = "#ok"
CMD_LIVE_Q = "#live?"
CMD_LIVE = "#live"
CMD_NOT_FOUND = "#nfound"
CMD_MSG_PREFIX = "#Ms:"
CMD_CHECK_LIVE = "#checklive"
CMD_CHECK_LIVE_OK = "#checklive_ok"
CMD_ALWAYS_LIVE = "#alwayslive"
CMD_ALWAYS_LIVE_OK = "#alwayslive_ok"
CMD_MAC_Q = "#macaddr?"
CMD_QUERY_FAILURE = "#queryprocessfailure"

# Comandos que o terminal envia e que apenas confirmamos.
ACK_ONLY = {CMD_CHECK_LIVE: CMD_CHECK_LIVE_OK, CMD_ALWAYS_LIVE: CMD_ALWAYS_LIVE_OK}

KNOWN_PREFIXES = tuple(TERMINAL_IDS) + (
    CMD_LIVE, CMD_OK, CMD_CHECK_LIVE, CMD_ALWAYS_LIVE, "#macaddr", "#fullmacaddr",
    "#config02", "#extconfig", "#paramconfig", "#wlanconfig", "#audioconfig",
    "#updconfig", "#getlistmedias", "#getmediasconf", "#sendmedia", "#removemedia",
    "#removeallmedias", "#savemediasconf", "#img", "#gif", "#restartsoft",
    "#sleep", "#update", "#fw2533", "#finishupdatefirmware", CMD_QUERY_FAILURE,
)


def encode(command: str, *, com_nul: bool = False) -> bytes:
    """Codifica comando SC501.

    A captura do TC Server original com Busca Preço G2 mostra que o *servidor*
    envia frames **sem** NUL final (`#ok`, `#live?`, `#nome|preço`). O terminal
    costuma terminar os dele com NUL. Por padrão não acrescentamos NUL na
    saída; use `com_nul=True` só se algum firmware exigir.
    """
    bruto = command.encode(CHARSET, errors="replace")
    return bruto + TERM if com_nul else bruto


def _preco_simples(texto: str) -> str:
    """Normaliza preço para o formato da captura: `3,50` (sem R$)."""
    if not texto:
        return ""
    t = str(texto).strip()
    for simb in ("R$", "US$", "$", "€", "£"):
        t = t.replace(simb, "")
    return t.strip()


def build_product_response(description: str, label1: str, price1: str,
                           label2: str = "", price2: str = "",
                           *, estilo: str = "ms") -> str:
    """Monta a resposta de produto.

    `estilo="ms"` — formato `#Ms:` do JAR (TC-406 e afins).
    `estilo="simples"` — captura real do G2 / manual 2.1.1.21:
        `#descrição|3,50 0,00`  (sem NUL; sem símbolo de moeda).
    """
    if estilo == "simples":
        desc = (description or "")[:80]
        p1 = _preco_simples(price1)
        p2 = _preco_simples(price2) or "0,00"
        if p1:
            return f"#{desc}|{p1} {p2}"
        return f"#{desc}"

    parts = [f"{CMD_MSG_PREFIX}{description}"]
    if price1:
        parts.append(f"|L:{label1} V:{price1}")
    if price2:
        parts.append(f"|L:{label2} V:{price2}")
    return "".join(parts)


class Sc501Connection(threading.Thread):
    def __init__(self, sock: socket.socket, address: tuple[str, int],
                 service: QueryService, server: "Sc501Server") -> None:
        super().__init__(name=f"sc501-{address[0]}:{address[1]}", daemon=True)
        self.sock = sock
        self.address = address
        self.service = service
        self.server = server
        self.peer = f"{address[0]}:{address[1]}"
        self.buffer = bytearray()
        self.terminal = service.terminal_connected(self.peer)
        self._identificado = False
        self._ultimo_live = 0.0

    # ------------------------------------------------------------------ io
    def send(self, command: str) -> None:
        if getattr(self.server, "passivo", False):
            log.info("[passivo] não enviando para %s: %s", self.peer, command)
            MONITOR.nota("SC501", self.peer, f"modo passivo: envio de {command} suprimido")
            return
        quadro = encode(command)
        try:
            self.sock.sendall(quadro)
            MONITOR.enviado("SC501", self.peer, quadro, command)
            log.info("ENVIADO -> %s  %s\n%s", self.peer, command, hexdump(quadro))
        except OSError as exc:
            log.debug("Falha ao escrever para %s: %s", self.peer, exc)

    def run(self) -> None:
        """Handshake conforme captura do TC Server original + Busca Preço G2:

            servidor:  #ok
            terminal:  #tc406|4.0\\0
            servidor:  #macaddr?9
            servidor:  #updconfig?
            terminal:  #macaddr...
            servidor:  #live?
            terminal:  #updconfig... / #live
            depois:    #live? a cada ~10 s
        """
        log.info("Terminal conectado: %s", self.peer)
        MONITOR.nota("SC501", self.peer, "conectado")

        # 1) #ok imediatamente — sem isso o G2 não completa a sessão.
        self.send(CMD_OK)

        # Timeout curto para poder disparar #live? a cada INTERVALO_LIVE.
        self.sock.settimeout(1.0)
        self._ultimo_live = time.time()
        try:
            while not self.server.stopping:
                try:
                    chunk = self.sock.recv(4096)
                except socket.timeout:
                    self._talvez_live()
                    continue
                if not chunk:
                    break
                MONITOR.recebido("SC501", self.peer, chunk)
                log.info("RECEBIDO <- %s  %d bytes:\n%s",
                         self.peer, len(chunk), hexdump(chunk))
                self.buffer.extend(chunk)
                self._drain()
                self._talvez_live()
        except OSError as exc:
            log.debug("Conexão %s encerrada: %s", self.peer, exc)
        finally:
            self.close()

    def _talvez_live(self) -> None:
        """Envia `#live?` a cada INTERVALO_LIVE após o handshake."""
        if not self._identificado:
            return
        agora = time.time()
        if agora - self._ultimo_live >= INTERVALO_LIVE:
            self.send(CMD_LIVE_Q)
            self._ultimo_live = agora

    def _drain(self) -> None:
        """Extrai mensagens do buffer.

        O terminal mistura frames com NUL (`#tc406|4.0\\0`, `#código\\0`) e
        frames sem NUL (`#live`). Processamos os dois formatos.
        """
        while True:
            if TERM in self.buffer:
                raw, _, rest = bytes(self.buffer).partition(TERM)
                self.buffer = bytearray(rest)
                payload = raw.decode(CHARSET, errors="replace").strip()
                if payload:
                    self.handle(payload)
                continue

            # Sem NUL: tenta comandos curtos conhecidos no início do buffer.
            texto = bytes(self.buffer).decode(CHARSET, errors="replace")
            if not texto:
                return
            baixos = texto.lower()
            consumiu = 0
            for cmd in (CMD_LIVE, CMD_QUERY_FAILURE, "#img_ok", "#img_error"):
                if baixos.startswith(cmd.lower()):
                    # Consome só o comando (pode vir colado em outro depois).
                    fim = len(cmd)
                    # Se vier `#img_ok00`, leva os dígitos extras do índice.
                    if cmd.startswith("#img"):
                        while fim < len(texto) and texto[fim] not in "#\x00":
                            fim += 1
                    payload = texto[:fim].strip()
                    consumiu = fim
                    if payload:
                        self.handle(payload)
                    break
            if consumiu:
                self.buffer = bytearray(self.buffer[consumiu:])
                continue
            return

    # ------------------------------------------------------------- comandos
    def handle(self, payload: str) -> None:
        log.debug("<- %s %s", self.peer, payload)
        self.terminal.last_seen = time.time()
        lower = payload.lower()

        # Identificação: `#tc406|4.0`, `#bpg2e`, etc.
        # O #ok já foi enviado na conexão; aqui seguimos o restante do handshake.
        id_chave = lower.split("|", 1)[0]
        model = TERMINAL_IDS.get(id_chave) or TERMINAL_IDS.get(lower)
        if model or id_chave in {k.lower() for k in TERMINAL_IDS}:
            nome = model or TERMINAL_IDS.get(id_chave, id_chave)
            if "|" in payload:
                nome = f"{nome} v{payload.split('|', 1)[1].strip()}"
            self.terminal.model = nome
            log.info("Terminal %s identificado como %s", self.peer, nome)
            if not self._identificado:
                self._identificado = True
                # Captura: após #tc406 o original pede MAC e updconfig, depois live.
                self.send(CMD_MAC_Q_G2)
                self.send(CMD_UPDCONFIG_Q)
                self.send(CMD_LIVE_Q)
                self._ultimo_live = time.time()
            return

        # Resposta ao #macaddr?9 → `#macaddr0A00:1D:...`
        if lower.startswith("#macaddr") and not lower.startswith("#macaddr?"):
            log.info("MAC de %s: %s", self.peer, payload)
            return

        # Resposta ao #updconfig? → `#updconfig<ip;...;nome;...`
        if lower.startswith("#updconfig") and not lower.endswith("?"):
            log.info("Config de %s: %s", self.peer, payload)
            return

        # Keep-alive do terminal: só registra, não ecoa (captura não ecoa).
        if lower == CMD_LIVE or lower.startswith(CMD_LIVE + "|"):
            return

        for cmd, reply in ACK_ONLY.items():
            if lower.startswith(cmd):
                self.send(reply)
                return

        if lower == CMD_QUERY_FAILURE:
            log.warning("Terminal %s reportou falha no processamento da consulta", self.peer)
            return

        if lower.startswith("#img_ok") or lower.startswith("#img_error"):
            log.info("Resposta #img de %s: %s", self.peer, payload)
            return

        # Prefixos conhecidos que não são código de barras (evita tratar
        # `#macaddr?` reverso etc. como produto).
        if lower.startswith(KNOWN_PREFIXES) or lower.startswith("#updconfig"):
            log.info("Comando não tratado de %s: %s", self.peer, payload)
            return

        self.handle_barcode(payload)

    def handle_barcode(self, barcode: str) -> None:
        code = barcode.lstrip("#").strip()
        if not code:
            return
        self.terminal.queries += 1
        self.terminal.last_barcode = code
        result = self.service.query(code, origin=self.address[0], channel="terminal")
        if not result.found:
            self.send(CMD_NOT_FOUND)
            return

        # Só texto na consulta. No Busca Preço G2 / TC-406 a imagem (#img)
        # serve para propaganda em idle, não para resposta de preço — a captura
        # do servidor original confirma: apenas `#desc|preço`.
        self.send(build_product_response(
            description=result.description,
            label1=result.label1,
            price1=result.price1,
            label2=result.label2,
            price2=result.price2,
            estilo="simples",
        ))

    def close(self) -> None:
        self.service.terminal_disconnected(self.peer)
        try:
            self.sock.close()
        except OSError:
            pass
        MONITOR.nota("SC501", self.peer, "desconectado")
        log.info("Terminal desconectado: %s", self.peer)


class Sc501Server(threading.Thread):
    def __init__(self, service: QueryService, host: str = "0.0.0.0", port: int = 6500,
                 passivo: bool = False) -> None:
        super().__init__(name="sc501-server", daemon=True)
        self.service = service
        self.host = host
        self.port = port
        self.passivo = passivo
        self.stopping = False
        self._sock: socket.socket | None = None

    def run(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind((self.host, self.port))
        except OSError as exc:
            log.error("Não foi possível abrir a porta SC501 %s: %s", self.port, exc)
            if getattr(exc, "winerror", None) == 10013:
                log.error(
                    "No Windows esse erro costuma ser porta reservada pelo "
                    "sistema (Hyper-V/WSL), não firewall. Confira com: "
                    "netsh interface ipv4 show excludedportrange protocol=tcp — "
                    "e escolha uma porta fora das faixas listadas."
                )
            return
        self._sock.listen(64)
        log.info("Servidor SC501 escutando em %s:%s%s", self.host, self.port,
                 ", MODO PASSIVO" if self.passivo else "")
        while not self.stopping:
            try:
                client, address = self._sock.accept()
            except OSError:
                break
            Sc501Connection(client, address, self.service, self).start()

    def stop(self) -> None:
        self.stopping = True
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass


