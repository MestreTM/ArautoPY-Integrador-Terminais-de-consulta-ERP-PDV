"""Modelo de produto e utilitários de preço.

O TC Server original guarda preços como texto livre ("R$12,49", "9,99", "12.49")
porque o campo vem direto do ERP do cliente. Mantemos o texto original para
exibição fiel e derivamos um valor numérico quando possível, que é o que a
consulta por peso e a API precisam.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

_CURRENCY_RE = re.compile(r"(R\$|US\$|\$|€|£)")
_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)*")


def parse_price(text: str | None) -> Decimal | None:
    """Extrai um valor numérico de um preço em texto livre.

    Aceita "R$ 1.234,56", "1234.56", "9,99", "€10,00". Devolve None quando o
    campo está vazio ou não contém número — o TC Server trata isso como
    "produto sem preço 2", não como erro.
    """
    if not text:
        return None
    match = _NUMBER_RE.search(str(text).strip())
    if not match:
        return None
    raw = match.group(0)
    if "," in raw and "." in raw:
        # 1.234,56 (pt-BR) ou 1,234.56 (en-US) — decide pelo último separador
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".") if len(raw.split(",")[-1]) <= 2 else raw.replace(",", "")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def format_price(value: Decimal | float | None, symbol: str = "R$") -> str:
    """Formata um valor no padrão brasileiro: R$ 1.234,56."""
    if value is None:
        return ""
    try:
        dec = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return ""
    inteiro, _, centavos = f"{abs(dec):.2f}".partition(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    corpo = f"{'.'.join(grupos)},{centavos}"
    sinal = "-" if dec < 0 else ""
    return f"{sinal}{symbol} {corpo}".strip()


def has_currency_symbol(text: str | None) -> bool:
    return bool(text) and bool(_CURRENCY_RE.search(str(text)))


def display_price(text: str | None, symbol: str) -> str:
    """Devolve o preço pronto para a tela.

    Se o campo do banco já traz símbolo de moeda, respeita o que veio (regra do
    manual: não usar as duas opções ao mesmo tempo). Senão, aplica a moeda
    padrão configurada.
    """
    if not text:
        return ""
    text = str(text).strip()
    if has_currency_symbol(text):
        return text
    value = parse_price(text)
    if value is None:
        return text
    return format_price(value, symbol)


@dataclass
class Product:
    barcode: str
    description: str = ""
    price1: str = ""
    price2: str = ""
    # preenchidos pela consulta, não persistidos
    source_barcode: str | None = None
    weight: Decimal | None = None
    unit_price1: str | None = None
    unit_price2: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = {
            "codigo_barras": self.barcode,
            "descricao": self.description,
            "preco1": self.price1,
            "preco2": self.price2,
        }
        if self.source_barcode:
            data["codigo_lido"] = self.source_barcode
        if self.weight is not None:
            data["peso"] = float(self.weight)
            data["preco1_unitario"] = self.unit_price1
            data["preco2_unitario"] = self.unit_price2
        if self.extra:
            data.update(self.extra)
        return data

    @staticmethod
    def from_row(row: dict, cols: dict[str, str]) -> "Product":
        def pick(key: str) -> str:
            col = cols.get(key)
            if not col:
                return ""
            for candidate in (col, col.lower(), col.upper()):
                if candidate in row and row[candidate] is not None:
                    return str(row[candidate]).strip()
            return ""

        barcode = pick("barcode")
        codigo_alt = pick("barcode_alt")
        extra: dict = {}
        if codigo_alt:
            extra["codigo_adicional"] = codigo_alt
            extra["coluna_codigo_adicional"] = cols.get("barcode_alt") or ""
        if not barcode and codigo_alt:
            barcode = codigo_alt
            extra["origem_codigo"] = "adicional"
            extra["codigo_principal"] = ""
        else:
            extra["origem_codigo"] = "barcode"
            extra["codigo_principal"] = barcode

        return Product(
            barcode=barcode,
            description=pick("description"),
            price1=pick("price1"),
            price2=pick("price2"),
            extra=extra,
        )


