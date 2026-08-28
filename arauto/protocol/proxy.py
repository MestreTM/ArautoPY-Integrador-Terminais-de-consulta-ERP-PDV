"""Intermediador entre o terminal e o TC Server original.

    terminal  →  :16510  [ intermediador ]  →  127.0.0.1:1597  (JAR original)

Repassa os bytes nos dois sentidos sem alterar nada e grava tudo em disco. Como
o servidor original funciona, a captura vira a resposta definitiva sobre o
protocolo — em vez de inferir do bytecode, lemos a conversa real.

Uso:

    # 1. configure o JAR original para escutar em 1597
    # 2. aponte o terminal para esta máquina, porta 16510
    python run.py --proxy 16510 --destino 127.0.0.1:1597

Cada sessão gera três arquivos em `~/.arauto/capturas/`:

    sessao-<carimbo>-terminal.bin    só o que o terminal enviou
    sessao-<carimbo>-servidor.bin    só o que o servidor original respondeu
    sessao-<carimbo>.jsonl           tudo, com hora, sentido e hexadecimal

Depois:

    python run.py --analisar sessao-<carimbo>.jsonl
"""

from __future__ import annotations

import json
import signal
import socket
import struct
import threading
import time
from datetime import datetime
from pathlib import Path

from .monitor import MONITOR, hexdump

# Nomes dos identificadores conhecidos, para rotular a conversa ao vivo.
from .sc504 import CORES, MODELOS, NOMES

def diga(*args) -> None:
    """print com flush.

    Sem isso, redirecionar a saída para arquivo faz o Python bufferizar em
    blocos de 4 KB — uma ferramenta de diagnóstico que só mostra o que houve
    depois de 4 KB de tráfego não serve para nada.
    """
    print(*args, flush=True)


CABECALHO = 7          # STX(1) + ID(2 LE) + TAMANHO(4 LE)
STX = 2

TERMINAL = "terminal"
SERVIDOR = "servidor"

# Pasta de capturas ao lado do run.py, não escondida em ~/.arauto:
# quem está depurando quer achar o arquivo sem procurar.
PASTA_CAPTURAS = Path(__file__).resolve().parents[2] / "capturas"

# Sessões abertas, para conseguir encerrá-las no Ctrl+C.
_sessoes_ativas: set = set()
_trava_sessoes = threading.Lock()

SETA = {TERMINAL: "→", SERVIDOR: "←"}
COR_NOME = {v: k for k, v in CORES.items()}


# --------------------------------------------------------------- decodificação
def nome_comando(identificador: int) -> str:
    if identificador in NOMES:
        return NOMES[identificador]
    if identificador - 1 in NOMES:
        return "R_" + NOMES[identificador - 1]
    return f"id{identificador}"


def detalhar(identificador: int, dados: bytes) -> str:
    """Traduz os payloads que interessam para a depuração do display."""
    try:
        if identificador == 20 and len(dados) >= 6:          # RIDwGetIdentify
            tipo, versao = struct.unpack("<HI", dados[:6])
            modelo = MODELOS.get(tipo, ("desconhecido", 0, 0))[0]
            return f"termType={tipo} ({modelo}) termVersion=0x{versao:X}"

        if identificador == 89 and len(dados) >= 2:          # IDbReadScanner
            n = struct.unpack("<H", dados[:2])[0]
            return f"codeLen={n} code={dados[2:2 + n].decode('latin-1')!r}"

        if identificador == 35 and len(dados) >= 170:        # IDvShowText
            x, y = struct.unpack("<hh", dados[:4])
            texto = dados[4:132].split(b"\x00")[0].decode("latin-1")
            fonte = dados[132:164].split(b"\x00")[0].decode("latin-1")
            tam, cor, fundo = struct.unpack("<hhh", dados[164:170])
            return (f"pos=({x},{y}) fonte={fonte!r} tam={tam} "
                    f"cor={COR_NOME.get(cor, cor)} fundo={COR_NOME.get(fundo, fundo)} "
                    f"texto={texto!r}")

        if identificador == 33 and len(dados) == 2:          # IDvDispClear
            valor = struct.unpack("<h", dados)[0]
            return f"cor={COR_NOME.get(valor, valor)}"

        if len(dados) == 4:                                  # DwordCommand
            return f"dword={struct.unpack('<i', dados)[0]}"
        if len(dados) == 2:                                  # WordCommand
            return f"word={struct.unpack('<h', dados)[0]}"
    except Exception:
        pass
    return ""


class Decodificador:
    """Acumula bytes de um sentido e emite quadros completos."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.dessincronizado = False

    def alimentar(self, dados: bytes) -> list[tuple[int, bytes]]:
        self.buffer.extend(dados)
        quadros = []
        while len(self.buffer) >= CABECALHO:
            stx, identificador, tamanho = struct.unpack(
                "<BHI", bytes(self.buffer[:CABECALHO]))
            if stx != STX or tamanho > 1 << 20:
                self.dessincronizado = True
                self.buffer.clear()
                return quadros
            if len(self.buffer) < CABECALHO + tamanho:
                return quadros
            quadros.append((identificador,
                            bytes(self.buffer[CABECALHO:CABECALHO + tamanho])))
            del self.buffer[:CABECALHO + tamanho]
        return quadros


# -------------------------------------------------------------------- gravação
class Gravacao:
    """Os três arquivos de uma sessão, gravados sem buffer.

    Sem `flush` a cada escrita, uma queda de conexão levaria junto os últimos
    bytes — justamente os que interessam quando algo dá errado.
    """

    def __init__(self, destino: Path, peer: str) -> None:
        carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
        rotulo = peer.replace(":", "_")
        destino.mkdir(parents=True, exist_ok=True)
        self.base = destino / f"sessao-{carimbo}-{rotulo}"
        self._lock = threading.Lock()
        self.arquivos = {
            TERMINAL: open(f"{self.base}-terminal.bin", "wb"),
            SERVIDOR: open(f"{self.base}-servidor.bin", "wb"),
        }
        self.jsonl = open(f"{self.base}.jsonl", "w", encoding="utf-8")
        self.total = {TERMINAL: 0, SERVIDOR: 0}
        self.inicio = time.time()

    def escrever(self, sentido: str, dados: bytes) -> None:
        with self._lock:
            self.arquivos[sentido].write(dados)
            self.arquivos[sentido].flush()
            self.jsonl.write(json.dumps({
                "t": round(time.time() - self.inicio, 4),
                "hora": datetime.now().isoformat(timespec="milliseconds"),
                "de": sentido,
                "bytes": len(dados),
                "hex": dados.hex(),
            }) + "\n")
            self.jsonl.flush()
            self.total[sentido] += len(dados)

    def nota(self, texto: str) -> None:
        with self._lock:
            self.jsonl.write(json.dumps({
                "t": round(time.time() - self.inicio, 4),
                "de": "nota", "texto": texto,
            }) + "\n")
            self.jsonl.flush()

    fechada = False

    def fechar(self) -> None:
        with self._lock:
            if self.fechada:
                return
            self.fechada = True
            for f in self.arquivos.values():
                f.close()
            self.jsonl.close()


# -------------------------------------------------------------------- sessão
class Sessao(threading.Thread):
    def __init__(self, cliente: socket.socket, endereco, destino_host: str,
                 destino_porta: int, pasta: Path, silencioso: bool) -> None:
        super().__init__(name=f"proxy-{endereco[1]}", daemon=True)
        self.cliente = cliente
        self.peer = f"{endereco[0]}:{endereco[1]}"
        self.destino_host = destino_host
        self.destino_porta = destino_porta
        self.pasta = pasta
        self.silencioso = silencioso
        self.servidor: socket.socket | None = None
        self.gravacao: Gravacao | None = None
        self.decod = {TERMINAL: Decodificador(), SERVIDOR: Decodificador()}
        self.parar = threading.Event()

    def encerrar_pedido(self) -> None:
        """Pedido externo de parada (Ctrl+C). Fecha os sockets para destravar
        os `recv` e deixar as threads de bombeamento saírem."""
        self.parar.set()
        for s in (self.cliente, self.servidor):
            if s:
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    s.close()
                except OSError:
                    pass

    def run(self) -> None:
        with _trava_sessoes:
            _sessoes_ativas.add(self)
        diga(f"\n{'=' * 74}\n>>> Terminal conectado: {self.peer}")
        self.gravacao = Gravacao(self.pasta, self.peer)
        diga(f"    gravando em {self.gravacao.base}-*\n")
        MONITOR.nota("PROXY", self.peer, "sessão iniciada")

        try:
            self.servidor = socket.create_connection(
                (self.destino_host, self.destino_porta), timeout=10)
        except OSError as exc:
            diga(f"!!! Não consegui falar com o servidor original em "
                  f"{self.destino_host}:{self.destino_porta}: {exc}")
            diga("    Verifique se o JAR está no ar e escutando nessa porta.\n")
            self.gravacao.nota(f"falha ao conectar no destino: {exc}")
            self.encerrar()
            return

        diga(f"    ligado ao servidor original em "
              f"{self.destino_host}:{self.destino_porta}\n")

        t1 = threading.Thread(target=self.bombear,
                              args=(self.cliente, self.servidor, TERMINAL),
                              daemon=True)
        t2 = threading.Thread(target=self.bombear,
                              args=(self.servidor, self.cliente, SERVIDOR),
                              daemon=True)
        t1.start(); t2.start()
        t1.join(); t2.join()
        self.encerrar()

    def bombear(self, origem: socket.socket, destino: socket.socket,
                sentido: str) -> None:
        """Repassa bytes de um lado para o outro, gravando pelo caminho."""
        origem.settimeout(1.0)
        try:
            while not self.parar.is_set():
                try:
                    dados = origem.recv(8192)
                except socket.timeout:
                    continue
                if not dados:
                    break
                # repassa primeiro: o terminal é sensível a atraso
                destino.sendall(dados)
                self.gravacao.escrever(sentido, dados)
                MONITOR.registrar("PROXY", self.peer,
                                  "recebido" if sentido == TERMINAL else "enviado",
                                  dados)
                if not self.silencioso:
                    self.mostrar(sentido, dados)
        except OSError:
            pass
        finally:
            self.parar.set()

    def mostrar(self, sentido: str, dados: bytes) -> None:
        agora = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        rotulo = "TERMINAL → servidor" if sentido == TERMINAL else "servidor → TERMINAL"
        diga(f"[{agora}] {SETA[sentido]} {rotulo}  {len(dados)} bytes")

        quadros = self.decod[sentido].alimentar(dados)
        if self.decod[sentido].dessincronizado:
            diga("    (não casou com o enquadramento SC504; veja o hexdump)")
            self.decod[sentido].dessincronizado = False
        for identificador, corpo in quadros:
            detalhe = detalhar(identificador, corpo)
            diga(f"    ⟨{identificador:>3}⟩ {nome_comando(identificador):<22} "
                  f"{len(corpo):>4}b  {detalhe}")
        diga(hexdump(dados[:256]))
        if len(dados) > 256:
            diga(f"    … (mais {len(dados) - 256} bytes)")
        diga()

    def encerrar(self) -> None:
        with _trava_sessoes:
            _sessoes_ativas.discard(self)
        for s in (self.cliente, self.servidor):
            if s:
                try:
                    s.close()
                except OSError:
                    pass
        if self.gravacao and not self.gravacao.fechada:
            t = self.gravacao.total
            diga(f"<<< Sessão {self.peer} encerrada — "
                  f"terminal {t[TERMINAL]}b, servidor {t[SERVIDOR]}b")
            diga(f"    arquivos: {self.gravacao.base}-*\n")
            self.gravacao.nota("sessão encerrada")
            self.gravacao.fechar()
        MONITOR.nota("PROXY", self.peer, "sessão encerrada")


# ------------------------------------------------------------------- servidor
def rodar(porta: int, destino: str, host: str = "0.0.0.0",
          pasta: Path | None = None, silencioso: bool = False) -> None:
    if ":" in destino:
        destino_host, _, porta_txt = destino.rpartition(":")
        destino_porta = int(porta_txt)
    else:
        destino_host, destino_porta = "127.0.0.1", int(destino)

    pasta = pasta or PASTA_CAPTURAS
    pasta.mkdir(parents=True, exist_ok=True)

    escuta = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    escuta.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        escuta.bind((host, porta))
    except OSError as exc:
        from arauto.core.netutil import mensagem_falha_porta
        diga(mensagem_falha_porta("proxy/sniffer", porta, exc, host=host))
        raise SystemExit(1) from exc
    escuta.listen(8)
    # Timeout curto em vez de accept() bloqueante: no Windows o Ctrl+C não
    # interrompe uma chamada de socket bloqueada, e o processo ficava preso.
    escuta.settimeout(0.5)

    parar = threading.Event()

    def pedir_parada(signum=None, quadro=None):   # noqa: ARG001
        if not parar.is_set():
            diga("\nEncerrando o intermediador…")
        parar.set()

    anteriores = {}
    for nome in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sinal = getattr(signal, nome, None)
        if sinal is None:
            continue
        try:
            anteriores[sinal] = signal.signal(sinal, pedir_parada)
        except (ValueError, OSError):
            pass   # fora da thread principal, ou sinal indisponível

    diga("=" * 74)
    diga(f"INTERMEDIADOR  {host}:{porta}  →  {destino_host}:{destino_porta}")
    diga("=" * 74)
    diga(f"Aponte o terminal para esta máquina na porta {porta}")
    diga(f"e deixe o TC Server original escutando em {destino_host}:{destino_porta}.")
    diga(f"Capturas em: {pasta}")
    diga("Ctrl+C encerra.\n")

    try:
        while not parar.is_set():
            try:
                cliente, endereco = escuta.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            Sessao(cliente, endereco, destino_host, destino_porta,
                   pasta, silencioso).start()
    except KeyboardInterrupt:
        pedir_parada()
    finally:
        parar.set()
        try:
            escuta.close()
        except OSError:
            pass

        with _trava_sessoes:
            abertas = list(_sessoes_ativas)
        if abertas:
            diga(f"Fechando {len(abertas)} sessão(ões) aberta(s)…")
            for sessao in abertas:
                sessao.encerrar_pedido()
            # Espera curta: os arquivos já foram gravados com flush a cada
            # escrita, então nada se perde se alguma thread demorar.
            for sessao in abertas:
                sessao.join(timeout=3)

        for sinal, anterior in anteriores.items():
            try:
                signal.signal(sinal, anterior)
            except (ValueError, OSError):
                pass

        capturas = sorted(pasta.glob("sessao-*.jsonl"))
        if capturas:
            diga(f"\n{len(capturas)} captura(s) em {pasta}")
            for arquivo in capturas[-5:]:
                diga(f"    {arquivo.name}")
            diga(f"\nPara reler:  python run.py --analisar "
                 f"capturas/{capturas[-1].name}")
        diga("Intermediador encerrado.\n")


# -------------------------------------------------------------------- análise
def analisar_arquivo(caminho: Path) -> str:
    """Relatório legível de uma sessão gravada."""
    eventos = []
    with caminho.open(encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                eventos.append(json.loads(linha))

    decod = {TERMINAL: Decodificador(), SERVIDOR: Decodificador()}
    saida = [
        "=" * 74,
        f"CONVERSA — {caminho.name}",
        "=" * 74,
        "",
    ]
    totais = {TERMINAL: 0, SERVIDOR: 0}
    contagem: dict[str, int] = {}

    for evento in eventos:
        if evento.get("de") == "nota":
            saida.append(f"  · {evento['texto']}")
            continue
        sentido = evento["de"]
        dados = bytes.fromhex(evento["hex"])
        totais[sentido] += len(dados)
        for identificador, corpo in decod[sentido].alimentar(dados):
            nome = nome_comando(identificador)
            contagem[nome] = contagem.get(nome, 0) + 1
            detalhe = detalhar(identificador, corpo)
            saida.append(
                f"  {evento['t']:>8.3f}s {SETA[sentido]} ⟨{identificador:>3}⟩ "
                f"{nome:<22} {len(corpo):>4}b  {detalhe}"
            )
        if decod[sentido].dessincronizado:
            saida.append(f"  {evento['t']:>8.3f}s {SETA[sentido]} "
                         f"[{len(dados)} bytes fora do enquadramento SC504]")
            saida.append(hexdump(dados[:128], "        "))
            decod[sentido].dessincronizado = False

    saida += [
        "",
        "-" * 74,
        f"terminal → servidor: {totais[TERMINAL]} bytes",
        f"servidor → terminal: {totais[SERVIDOR]} bytes",
        "",
        "Comandos vistos:",
    ]
    for nome, n in sorted(contagem.items(), key=lambda kv: -kv[1]):
        saida.append(f"    {n:>4}x  {nome}")
    saida.append("-" * 74)
    return "\n".join(saida)


