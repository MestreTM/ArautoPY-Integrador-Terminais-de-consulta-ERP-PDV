"""Sniffer de protocolo — descobre o enquadramento real de um terminal.

Existe porque o enquadramento do SC504 foi inferido de constantes compiladas,
sem hardware. Quando um terminal de verdade aparece e não casa, adivinhar de
novo é perda de tempo: melhor capturar os bytes crus e deixar o computador
testar as hipóteses.

Uso:

    python run.py --sniffer 16510

Conecte o terminal e faça uma consulta. O sniffer imprime tudo em hexadecimal,
grava a captura em disco e diz qual hipótese de enquadramento explica os dados.
"""

from __future__ import annotations

import logging
import signal
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger("arauto.sniffer")

LARGURA = 16


def hexdump(dados: bytes, prefixo: str = "    ") -> str:
    """Dump clássico: offset, bytes em hex, e o ASCII imprimível ao lado."""
    linhas = []
    for pos in range(0, len(dados), LARGURA):
        pedaco = dados[pos:pos + LARGURA]
        hexa = " ".join(f"{b:02x}" for b in pedaco)
        hexa = f"{hexa:<{LARGURA * 3 - 1}}"
        texto = "".join(chr(b) if 32 <= b < 127 else "." for b in pedaco)
        linhas.append(f"{prefixo}{pos:04x}  {hexa}  |{texto}|")
    return "\n".join(linhas)


# ---------------------------------------------------------------- hipóteses
@dataclass
class Hipotese:
    nome: str
    descricao: str
    tamanho_cabecalho: int
    formato: str            # struct de leitura do cabeçalho
    indice_stx: int | None  # posição do campo STX no unpack, ou None
    indice_id: int
    indice_tamanho: int
    stx_esperado: int = 2

    def ler_cabecalho(self, dados: bytes) -> tuple[int | None, int, int] | None:
        if len(dados) < self.tamanho_cabecalho:
            return None
        campos = struct.unpack(self.formato, dados[:self.tamanho_cabecalho])
        stx = campos[self.indice_stx] if self.indice_stx is not None else None
        return stx, campos[self.indice_id], campos[self.indice_tamanho]


HIPOTESES = [
    # A mais provável segundo Tc504Command: put(byte STX), putShort(id), putInt(len)
    Hipotese("B-H-I-LE", "STX 1 byte | ID 2 bytes LE | TAM 4 bytes LE",
             7, "<BHI", 0, 1, 2),
    Hipotese("B-H-I-BE", "STX 1 byte | ID 2 bytes BE | TAM 4 bytes BE",
             7, ">BHI", 0, 1, 2),
    Hipotese("B-H-H-LE", "STX 1 byte | ID 2 bytes LE | TAM 2 bytes LE",
             5, "<BHH", 0, 1, 2),
    Hipotese("B-B-H-LE", "STX 1 byte | ID 1 byte | TAM 2 bytes LE",
             4, "<BBH", 0, 1, 2),
    Hipotese("H-H-H-LE", "STX 2 bytes LE | ID 2 LE | TAM 2 LE (versão 1.0)",
             6, "<HHH", 0, 1, 2),
    Hipotese("H-H-H-BE", "STX 2 bytes BE | ID 2 BE | TAM 2 BE",
             6, ">HHH", 0, 1, 2),
    Hipotese("H-I-LE", "sem STX | ID 2 bytes LE | TAM 4 bytes LE",
             6, "<HI", None, 0, 1),
    Hipotese("B-I-LE", "sem STX | ID 1 byte | TAM 4 bytes LE",
             5, "<BI", None, 0, 1),
]


@dataclass
class Resultado:
    hipotese: Hipotese
    quadros: int = 0
    consumido: int = 0
    total: int = 0
    ids: list[int] = field(default_factory=list)
    completo: bool = False

    @property
    def pontuacao(self) -> float:
        """Fração do buffer explicada. 1.0 = a hipótese consome tudo."""
        return self.consumido / self.total if self.total else 0.0


def testar(dados: bytes, hipotese: Hipotese) -> Resultado:
    """Tenta consumir o buffer inteiro como uma sequência de quadros."""
    resultado = Resultado(hipotese=hipotese, total=len(dados))
    pos = 0
    while pos < len(dados):
        cabecalho = hipotese.ler_cabecalho(dados[pos:])
        if cabecalho is None:
            break
        stx, identificador, tamanho = cabecalho

        if stx is not None and stx != hipotese.stx_esperado:
            break
        # tamanhos absurdos denunciam a hipótese errada
        if tamanho > 1_000_000 or pos + hipotese.tamanho_cabecalho + tamanho > len(dados):
            break

        pos += hipotese.tamanho_cabecalho + tamanho
        resultado.quadros += 1
        resultado.ids.append(identificador)

    resultado.consumido = pos
    resultado.completo = pos == len(dados) and resultado.quadros > 0
    return resultado


def analisar(dados: bytes) -> list[Resultado]:
    """Ordena as hipóteses pela fração do buffer que cada uma explica."""
    resultados = [testar(dados, h) for h in HIPOTESES]
    resultados.sort(key=lambda r: (r.completo, r.pontuacao, r.quadros), reverse=True)
    return resultados


def relatorio(dados: bytes) -> str:
    """Texto pronto para colar num chamado ou mandar para quem for corrigir."""
    linhas = [
        "",
        "=" * 72,
        f"ANÁLISE DE ENQUADRAMENTO — {len(dados)} bytes capturados",
        "=" * 72,
        "",
        hexdump(dados[:512]),
    ]
    if len(dados) > 512:
        linhas.append(f"    … (mais {len(dados) - 512} bytes)")

    linhas += ["", "Hipóteses, da que melhor explica os dados para a pior:", ""]
    for r in analisar(dados):
        marca = "✓" if r.completo else ("~" if r.pontuacao > 0.5 else " ")
        ids = ", ".join(str(i) for i in r.ids[:8]) or "—"
        linhas.append(
            f"  {marca} {r.hipotese.nome:<10} {r.pontuacao * 100:5.1f}%  "
            f"{r.quadros:>3} quadro(s)  ids: {ids}"
        )
        linhas.append(f"      {r.hipotese.descricao}")

    melhor = analisar(dados)[0]
    linhas += ["", "-" * 72]
    if melhor.completo:
        linhas.append(f"CONCLUSÃO: o enquadramento é {melhor.hipotese.nome} — "
                      f"{melhor.hipotese.descricao}")
        linhas.append(f"Identificadores vistos: {melhor.ids}")
    else:
        linhas.append("CONCLUSÃO: nenhuma hipótese explica a captura por completo.")
        linhas.append("Pode ser um protocolo diferente, um cabeçalho com campo extra,")
        linhas.append("ou dados fragmentados. Mande esta captura para análise.")
    linhas += ["-" * 72, ""]
    return "\n".join(linhas)


# ------------------------------------------------------------------ servidor
class SnifferConnection(threading.Thread):
    def __init__(self, sock: socket.socket, endereco: tuple[str, int],
                 destino: Path, responder: bool) -> None:
        super().__init__(name=f"sniffer-{endereco[1]}", daemon=True)
        self.sock = sock
        self.endereco = endereco
        self.peer = f"{endereco[0]}:{endereco[1]}"
        self.destino = destino
        self.responder = responder
        self.acumulado = bytearray()

    def run(self) -> None:
        print(f"\n>>> Terminal conectado: {self.peer}\n")
        self.sock.settimeout(300)
        try:
            while True:
                try:
                    pedaco = self.sock.recv(8192)
                except socket.timeout:
                    print(f"    (sem dados de {self.peer} há 5 min)")
                    continue
                if not pedaco:
                    break

                agora = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"[{agora}] {self.peer} → {len(pedaco)} bytes")
                print(hexdump(pedaco))
                print()
                self.acumulado.extend(pedaco)

                if self.responder:
                    self.tentar_responder(pedaco)
        except OSError as exc:
            print(f"    conexão perdida: {exc}")
        finally:
            self.encerrar()

    def tentar_responder(self, pedaco: bytes) -> None:
        """Devolve um ACK segundo a melhor hipótese, para o terminal continuar.

        Sem isso muitos terminais desistem e reconectam em laço, e a captura
        nunca passa do primeiro pacote.
        """
        melhor = analisar(bytes(self.acumulado))[0]
        if not melhor.completo or not melhor.ids:
            return
        h = melhor.hipotese
        identificador = melhor.ids[-1]
        campos = []
        if h.indice_stx is not None:
            campos.append(h.stx_esperado)
        campos += [identificador + 1, 0]
        try:
            self.sock.sendall(struct.pack(h.formato, *campos))
            print(f"    ← ACK id={identificador + 1} (hipótese {h.nome})\n")
        except (OSError, struct.error):
            pass

    def encerrar(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass
        if self.acumulado:
            self.destino.parent.mkdir(parents=True, exist_ok=True)
            self.destino.write_bytes(bytes(self.acumulado))
            print(relatorio(bytes(self.acumulado)))
            print(f"Captura crua salva em: {self.destino}\n")
        print(f"<<< Terminal desconectado: {self.peer}\n")


def rodar(porta: int, host: str = "0.0.0.0", destino_dir: Path | None = None,
          responder: bool = True) -> None:
    """Escuta numa porta e despeja tudo que chegar."""
    from .proxy import PASTA_CAPTURAS
    destino_dir = destino_dir or PASTA_CAPTURAS
    destino_dir.mkdir(parents=True, exist_ok=True)

    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind((host, porta))
    servidor.listen(8)
    servidor.settimeout(0.5)   # ver comentário em proxy.rodar sobre Ctrl+C

    parar = threading.Event()

    def pedir_parada(signum=None, quadro=None):   # noqa: ARG001
        if not parar.is_set():
            print("\nEncerrando o sniffer…", flush=True)
        parar.set()

    anteriores = {}
    for nome in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sinal = getattr(signal, nome, None)
        if sinal is None:
            continue
        try:
            anteriores[sinal] = signal.signal(sinal, pedir_parada)
        except (ValueError, OSError):
            pass

    print("=" * 72, flush=True)
    print(f"SNIFFER escutando em {host}:{porta}", flush=True)
    print("=" * 72, flush=True)
    print("Aponte o terminal para esta máquina e faça uma consulta.", flush=True)
    print(f"Capturas em: {destino_dir}", flush=True)
    print("Ctrl+C encerra e imprime a análise.\n", flush=True)

    conexoes = []
    try:
        while not parar.is_set():
            try:
                cliente, endereco = servidor.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
            destino = destino_dir / f"captura-{porta}-{carimbo}.bin"
            conexao = SnifferConnection(cliente, endereco, destino, responder)
            conexoes.append(conexao)
            conexao.start()
    except KeyboardInterrupt:
        pedir_parada()
    finally:
        parar.set()
        try:
            servidor.close()
        except OSError:
            pass
        for conexao in conexoes:
            try:
                conexao.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conexao.sock.close()
            except OSError:
                pass
        for conexao in conexoes:
            conexao.join(timeout=3)
        for sinal, anterior in anteriores.items():
            try:
                signal.signal(sinal, anterior)
            except (ValueError, OSError):
                pass
        print("Sniffer encerrado.\n", flush=True)


