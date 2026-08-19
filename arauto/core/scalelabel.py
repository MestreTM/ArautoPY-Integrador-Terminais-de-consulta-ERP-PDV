"""Leitura de etiqueta de balança por máscara.

Substitui a configuração posicional do TC Server original por uma máscara, no
mesmo estilo dos softwares de retaguarda brasileiros:

    2CCCCCCTTTTTV

Cada caractere descreve uma posição do código de barras:

    C   código do produto (a chave usada na base)
    P   peso, em gramas — o preço final é peso × preço do cadastro
    T   total já calculado, em centavos — o preço vem do próprio código
    D   dígito verificador interno da balança (ignorado)
    V   dígito verificador do EAN-13 (ignorado na leitura, conferido à parte)
    0-9 literal: o código só é de balança se casar exatamente
    X   posição ignorada

O comprimento da máscara define o comprimento do código aceito.

Uma etiqueta traz **ou** `P` **ou** `T`, nunca os dois. Confundir os dois é o
erro mais caro possível aqui: ler um total de R$ 7,19 como 719 gramas faz o
terminal cobrar R$ 50,26. Por isso `validar()` recusa máscaras ambíguas e o
simulador da tela de configuração mostra a decomposição antes de salvar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .models import Product, format_price, parse_price

# Padrão: etiqueta por total, código de 6 dígitos.
# Lê 2001110007192 -> produto 001110, total R$ 7,19.
MASCARA_PADRAO = "2CCCCCCTTTTTV"

DIVISOR_PESO = Decimal(1000)    # gramas -> quilos
DIVISOR_TOTAL = Decimal(100)    # centavos -> reais

MARCADORES = "CPTDVX"

DESCRICAO_MARCADORES = [
    ("C", "Código do produto"),
    ("P", "Peso em gramas"),
    ("T", "Total em centavos"),
    ("D", "Dígito verificador da balança"),
    ("V", "Dígito verificador do EAN"),
    ("X", "Posição ignorada"),
    ("0-9", "Valor fixo que precisa casar"),
]


def _blocos(mascara: str, marcador: str) -> tuple[int, int] | None:
    """Posição inicial e final de um marcador. Exige que seja contíguo."""
    posicoes = [i for i, c in enumerate(mascara) if c == marcador]
    if not posicoes:
        return None
    return posicoes[0], posicoes[-1] + 1


@dataclass
class Mascara:
    texto: str = MASCARA_PADRAO

    def __post_init__(self) -> None:
        self.texto = (self.texto or "").strip().upper()

    # ------------------------------------------------------------- estrutura
    @property
    def comprimento(self) -> int:
        return len(self.texto)

    @property
    def codigo(self) -> tuple[int, int] | None:
        return _blocos(self.texto, "C")

    @property
    def peso(self) -> tuple[int, int] | None:
        return _blocos(self.texto, "P")

    @property
    def total(self) -> tuple[int, int] | None:
        return _blocos(self.texto, "T")

    @property
    def tamanho_codigo(self) -> int:
        faixa = self.codigo
        return faixa[1] - faixa[0] if faixa else 0

    @property
    def tipo(self) -> str:
        if self.total:
            return "total"
        if self.peso:
            return "peso"
        return "codigo"

    @property
    def descricao_tipo(self) -> str:
        return {
            "total": "por total (o preço vem no código de barras)",
            "peso": "por peso (preço = peso × valor do cadastro)",
            "codigo": "apenas código (sem peso nem total)",
        }[self.tipo]

    # ------------------------------------------------------------- validação
    def validar(self) -> list[str]:
        erros: list[str] = []
        texto = self.texto

        if not texto:
            return ["Informe a máscara da etiqueta"]

        invalidos = sorted({c for c in texto if c not in MARCADORES and not c.isdigit()})
        if invalidos:
            erros.append("Caracteres não reconhecidos na máscara: " + ", ".join(invalidos))

        if not 8 <= len(texto) <= 20:
            erros.append(f"A máscara tem {len(texto)} posições; use entre 8 e 20")

        if not self.codigo:
            erros.append("A máscara precisa de pelo menos um C (código do produto)")

        if self.peso and self.total:
            erros.append("Use P (peso) ou T (total), nunca os dois na mesma máscara")

        # blocos precisam ser contíguos: "CCTTCC" seria ambíguo na leitura
        for marcador in "CPT":
            posicoes = [i for i, c in enumerate(texto) if c == marcador]
            if posicoes and posicoes[-1] - posicoes[0] + 1 != len(posicoes):
                erros.append(f"As posições {marcador} precisam ficar juntas na máscara")

        return erros

    def resumo(self) -> dict:
        return {
            "mascara": self.texto,
            "comprimento": self.comprimento,
            "tamanho_codigo": self.tamanho_codigo,
            "tipo": self.tipo,
            "descricao_tipo": self.descricao_tipo,
            "erros": self.validar(),
        }


@dataclass
class Leitura:
    """Resultado da decomposição de um código de balança."""

    codigo_lido: str
    codigo_produto: str
    tipo: str
    peso: Decimal | None = None
    total: Decimal | None = None
    dv_confere: bool | None = None
    candidatos: list[str] = field(default_factory=list)


def digito_verificador(codigo: str) -> int | None:
    """Dígito verificador EAN-13 dos 12 primeiros dígitos."""
    if len(codigo) < 13 or not codigo.isdigit():
        return None
    soma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(codigo[:12]))
    return (10 - soma % 10) % 10


def candidatos_base(codigo_produto: str, mascara: Mascara) -> list[str]:
    """Chaves a tentar na base, em ordem.

    A primeira é o código puro, que é como as balanças brasileiras costumam
    gravar. A segunda é o formato do TC Server antigo (`2` + código + zeros à
    direita), para que instalações migradas continuem funcionando sem recadastro.
    """
    candidatos = [codigo_produto]

    prefixo = mascara.texto[0] if mascara.texto and mascara.texto[0].isdigit() else "2"
    legado = f"{prefixo}{codigo_produto}".ljust(13, "0")[:13]
    if legado not in candidatos:
        candidatos.append(legado)

    sem_zeros = codigo_produto.lstrip("0")
    if sem_zeros and sem_zeros not in candidatos:
        candidatos.append(sem_zeros)

    return candidatos


def ler(codigo: str, mascara: Mascara | None = None) -> Leitura | None:
    """Decompõe um código segundo a máscara. Devolve None se não for de balança."""
    mascara = mascara or Mascara()
    codigo = (codigo or "").strip()

    if mascara.validar():
        return None
    if len(codigo) != mascara.comprimento or not codigo.isdigit():
        return None

    # literais precisam casar, senão não é etiqueta de balança
    for posicao, marcador in enumerate(mascara.texto):
        if marcador.isdigit() and codigo[posicao] != marcador:
            return None

    faixa_codigo = mascara.codigo
    codigo_produto = codigo[faixa_codigo[0]:faixa_codigo[1]]

    leitura = Leitura(
        codigo_lido=codigo,
        codigo_produto=codigo_produto,
        tipo=mascara.tipo,
    )

    if mascara.peso:
        inicio, fim = mascara.peso
        leitura.peso = Decimal(codigo[inicio:fim]) / DIVISOR_PESO
    if mascara.total:
        inicio, fim = mascara.total
        leitura.total = Decimal(codigo[inicio:fim]) / DIVISOR_TOTAL

    esperado = digito_verificador(codigo)
    if esperado is not None:
        leitura.dv_confere = codigo[12] == str(esperado)

    leitura.candidatos = candidatos_base(codigo_produto, mascara)
    return leitura


def aplicar(produto: Product, leitura: Leitura, simbolo: str) -> Product:
    """Monta o produto final a partir do cadastro e do que veio na etiqueta.

    Por total, o preço vem do código de barras e o cadastro serve só para a
    descrição. Por peso, o preço do cadastro é multiplicado pelo peso lido.
    """
    resultado = Product(
        barcode=produto.barcode,
        description=produto.description,
        price1=produto.price1,
        price2=produto.price2,
        weight=leitura.peso,
        unit_price1=produto.price1,
        unit_price2=produto.price2,
    )

    unitario1 = parse_price(produto.price1)
    unitario2 = parse_price(produto.price2)

    if leitura.tipo == "total" and leitura.total is not None:
        resultado.price1 = format_price(leitura.total, simbolo)
        # o peso não vem na etiqueta por total; dá para deduzir pelo preço do
        # cadastro, mas só vale se o cadastro estiver com o preço do dia
        if unitario1 and unitario1 > 0:
            resultado.weight = (leitura.total / unitario1).quantize(Decimal("0.001"))
        resultado.price2 = ""  # um total já é o valor a pagar; não há segundo total
        return resultado

    if leitura.peso is not None:
        if unitario1 is not None:
            resultado.price1 = format_price(unitario1 * leitura.peso, simbolo)
        if unitario2 is not None and unitario2 > 0:
            resultado.price2 = format_price(unitario2 * leitura.peso, simbolo)
        else:
            resultado.price2 = ""

    return resultado


# ------------------------------------------------------------------ migração
def da_config_antiga(first_digit: int, init_barcode: int, end_barcode: int,
                     init_weight: int, end_weight: int,
                     comprimento: int = 13) -> str:
    """Converte a configuração posicional antiga numa máscara equivalente.

    `FIRST_DIGIT;2 INIT_BARCODE;1 END_BARCODE;7 INIT_WEIGHT;7 END_WEIGHT;12`
    vira `2CCCCCCPPPPPV`.
    """
    posicoes = ["X"] * comprimento
    posicoes[0] = str(first_digit)[:1]
    for i in range(init_barcode, min(end_barcode, comprimento)):
        posicoes[i] = "C"
    for i in range(init_weight, min(end_weight, comprimento)):
        posicoes[i] = "P"
    if comprimento == 13 and posicoes[12] == "X":
        posicoes[12] = "V"
    return "".join(posicoes)


