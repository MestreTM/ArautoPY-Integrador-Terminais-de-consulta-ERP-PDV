"""Monitor de tráfego cru dos terminais.

Grava **tudo** que entra e sai, sem depender de nenhum sinalizador. A versão
anterior escondia os bytes atrás de `PROTOCOL_DEBUG`, e quando o terminal
mandava algo inesperado o log simplesmente emudecia — que é o pior momento
possível para ficar sem informação.

O buffer é circular e pequeno de propósito: são poucos bytes por consulta, e um
servidor de loja fica meses ligado.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

CAPACIDADE = 400          # eventos guardados
MAX_BYTES_EVENTO = 4096   # o que passar disso é truncado na exibição
LARGURA = 16


def hexdump(dados: bytes, prefixo: str = "    ") -> str:
    linhas = []
    for pos in range(0, len(dados), LARGURA):
        pedaco = dados[pos:pos + LARGURA]
        hexa = " ".join(f"{b:02x}" for b in pedaco)
        texto = "".join(chr(b) if 32 <= b < 127 else "." for b in pedaco)
        linhas.append(f"{prefixo}{pos:04x}  {hexa:<{LARGURA * 3 - 1}}  |{texto}|")
    return "\n".join(linhas)


@dataclass
class Evento:
    id: int
    ts: float
    protocolo: str            # "SC501" | "SC504"
    peer: str
    direcao: str              # "recebido" | "enviado" | "nota"
    dados: bytes = b""
    nota: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "hora": datetime.fromtimestamp(self.ts).strftime("%H:%M:%S.%f")[:-3],
            "protocolo": self.protocolo,
            "peer": self.peer,
            "direcao": self.direcao,
            "bytes": len(self.dados),
            "hex": self.dados[:MAX_BYTES_EVENTO].hex(),
            "ascii": "".join(chr(b) if 32 <= b < 127 else "."
                             for b in self.dados[:MAX_BYTES_EVENTO]),
            "nota": self.nota,
        }


class Monitor:
    def __init__(self, capacidade: int = CAPACIDADE) -> None:
        self._eventos: deque[Evento] = deque(maxlen=capacidade)
        self._lock = threading.RLock()
        self._seq = 0
        # captura acumulada por conexão, para análise de enquadramento
        self._sessoes: dict[str, bytearray] = {}

    def registrar(self, protocolo: str, peer: str, direcao: str,
                  dados: bytes = b"", nota: str = "") -> None:
        with self._lock:
            self._seq += 1
            self._eventos.append(Evento(
                id=self._seq, ts=time.time(), protocolo=protocolo, peer=peer,
                direcao=direcao, dados=dados, nota=nota,
            ))
            if direcao == "recebido" and dados:
                sessao = self._sessoes.setdefault(peer, bytearray())
                if len(sessao) < 65536:
                    sessao.extend(dados)

    def recebido(self, protocolo: str, peer: str, dados: bytes) -> None:
        self.registrar(protocolo, peer, "recebido", dados)

    def enviado(self, protocolo: str, peer: str, dados: bytes, nota: str = "") -> None:
        self.registrar(protocolo, peer, "enviado", dados, nota)

    def nota(self, protocolo: str, peer: str, texto: str) -> None:
        self.registrar(protocolo, peer, "nota", b"", texto)

    def encerrar_sessao(self, peer: str) -> bytes:
        with self._lock:
            return bytes(self._sessoes.pop(peer, b""))

    def sessao(self, peer: str) -> bytes:
        with self._lock:
            return bytes(self._sessoes.get(peer, b""))

    def eventos(self, desde: int = 0, protocolo: str = "", peer: str = "",
                limite: int = 200) -> list[dict]:
        with self._lock:
            itens = list(self._eventos)
        saida = []
        for evento in itens:
            if evento.id <= desde:
                continue
            if protocolo and evento.protocolo != protocolo:
                continue
            if peer and evento.peer != peer:
                continue
            saida.append(evento.to_dict())
        return saida[-limite:]

    def peers(self) -> list[str]:
        with self._lock:
            return sorted({e.peer for e in self._eventos})

    def resumo(self) -> dict:
        with self._lock:
            itens = list(self._eventos)
        recebidos = sum(1 for e in itens if e.direcao == "recebido")
        return {
            "eventos": len(itens),
            "capacidade": CAPACIDADE,
            "ultimo_id": itens[-1].id if itens else 0,
            "recebidos": recebidos,
            "enviados": sum(1 for e in itens if e.direcao == "enviado"),
            "bytes_recebidos": sum(len(e.dados) for e in itens
                                   if e.direcao == "recebido"),
            "sessoes": len(self._sessoes),
        }

    def tudo_cru(self, peer: str = "") -> bytes:
        """Bytes recebidos de um terminal.

        Sem `peer`, devolve a sessão com mais bytes em vez de concatenar todas:
        juntar tráfego de terminais diferentes (ainda por cima de protocolos
        diferentes) produz uma análise de enquadramento sem sentido nenhum.
        """
        with self._lock:
            if peer:
                return bytes(self._sessoes.get(peer, b""))
            if not self._sessoes:
                return b""
            maior = max(self._sessoes.values(), key=len)
            return bytes(maior)

    def sessao_principal(self) -> str:
        """Endereço da sessão com mais bytes — a que interessa analisar."""
        with self._lock:
            if not self._sessoes:
                return ""
            return max(self._sessoes.items(), key=lambda kv: len(kv[1]))[0]

    def sessoes_resumo(self) -> list[dict]:
        with self._lock:
            return sorted(
                ({"peer": k, "bytes": len(v)} for k, v in self._sessoes.items()),
                key=lambda d: d["bytes"], reverse=True,
            )

    def limpar(self) -> None:
        with self._lock:
            self._eventos.clear()
            self._sessoes.clear()


MONITOR = Monitor()


