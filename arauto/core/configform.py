"""Descrição dos campos da tela de configuração.

Separado do template porque a mesma estrutura serve para renderizar o formulário
e para validar o que volta dele. Só as chaves listadas aqui podem ser gravadas
pela web — o resto do arquivo de configuração fica fora do alcance da tela.
"""

from __future__ import annotations

from .settings import Settings

# Chaves cujo efeito depende de reiniciar o processo (portas, modo de base).
# Só o que ainda exige reiniciar o processo inteiro (sockets do Uvicorn).
# Base de produtos e terminais SC501/SC504 são reaplicados a quente.
REINICIO = {
    "BIND_HOST", "PORT_WEBVIEWER", "PORT_API", "API_CORS_ORIGINS",
}

# Aplicadas em tempo de execução via arauto.core.runtime
RECARGA_BASE = {
    "DB_MODE", "DB_URL", "DB_USER", "DB_PASSWORD",
    "DB_PRODUCT_TABLE_NAME", "DB_COL_BARCODE", "DB_COL_BARCODE_ALT",
    "DB_COL_DESCRIPITION",
    "DB_COL_PRICE1", "DB_COL_PRICE2", "DB_RELOAD_INTERVAL_MIN",
    "PATH_FILE_PRODUCT", "TXT_DB_RELOAD_INTERVAL_MIN",
}

RECARGA_TERMINAIS = {
    "LAST_PORT_501", "LAST_PORT_504", "AUTO_INIT_501", "AUTO_INIT_504",
    "SC504_FRAME", "SC504_PASSIVE", "SC501_PASSIVE", "PROTOCOL_DEBUG", "BIND_HOST",
}

MODOS_BASE = [
    ("INTERNAL", "Interna (SQLite embarcado)"),
    ("EXTERNAL_TXT", "Arquivo texto (código|descrição|preço1|preço2)"),
    ("EXTERNAL_SQL", "Banco de dados externo"),
]

# Presets de mapeamento EXTERNAL_SQL (ERP / PDV conhecidos).
# A URL pode trazer um caminho de exemplo; o usuário ajusta pasta/host/senha.
PRESETS_BASE = [
    {
        "id": "dbware",
        "nome": "DBware (Firebird)",
        "nota": (
            "O caminho do arquivo .fdb varia conforme a instalação do DBware "
            "(ex.: C:/DBVenda/DB/dbvenda.fdb). Ajuste DB_URL para o caminho real "
            "no seu computador e confira usuário/senha do Firebird. "
            "Códigos de balança (PLU) ficam em REFERENCIA quando CODIGO_BARRA está vazio. "
            "Tabela CAD_PRODUTOS, colunas CODIGO_BARRA, REFERENCIA, DESCRICAO, PRC_VENDA."
        ),
        "valores": {
            "DB_MODE": "EXTERNAL_SQL",
            "DB_URL": (
                "firebird+firebird://SYSDBA:masterkey@localhost/"
                "C:/DBVenda/DB/dbvenda.fdb?charset=WIN1252"
            ),
            "DB_PRODUCT_TABLE_NAME": "CAD_PRODUTOS",
            "DB_COL_BARCODE": "CODIGO_BARRA",
            "DB_COL_BARCODE_ALT": "REFERENCIA",
            "DB_COL_DESCRIPITION": "DESCRICAO",
            "DB_COL_PRICE1": "PRC_VENDA",
            "DB_COL_PRICE2": "PRC_VENDA",
            "DB_RELOAD_INTERVAL_MIN": "1",
        },
    },
]

FORMATOS_SC504 = [
    ("B-H-I-LE", "STX 1 | ID 2 LE | TAM 4 LE — padrão"),
    ("B-H-I-BE", "STX 1 | ID 2 BE | TAM 4 BE"),
    ("B-H-H-LE", "STX 1 | ID 2 LE | TAM 2 LE"),
    ("B-B-H-LE", "STX 1 | ID 1 | TAM 2 LE"),
    ("H-H-H-LE", "STX 2 LE | ID 2 LE | TAM 2 LE"),
    ("H-H-H-BE", "STX 2 BE | ID 2 BE | TAM 2 BE"),
]

MOEDAS = [
    ("BRL", "Real — R$"),
    ("USD", "Dólar — $"),
    ("EUR", "Euro — €"),
    ("NONE", "Sem símbolo"),
]

MASCARAS_PRONTAS = [
    ("2CCCCCCTTTTTV", "Por total — código 6 dígitos (padrão)"),
    ("2CCCCCTTTTTTV", "Por total — código 5 dígitos"),
    ("2CCCCCCPPPPPV", "Por peso — código 6 dígitos"),
    ("2CCCCCPPPPPPV", "Por peso — código 5 dígitos"),
    ("2CCCCCCTTTTTD", "Por total — com dígito da balança no fim"),
]


def _campo(chave, rotulo, tipo="texto", **extra) -> dict:
    campo = {
        "chave": chave,
        "rotulo": rotulo,
        "tipo": tipo,
        "ajuda": extra.get("ajuda", ""),
        "exemplo": extra.get("exemplo", ""),
        "opcoes": extra.get("opcoes", []),
        "minimo": extra.get("minimo", 0),
        "maximo": extra.get("maximo", 65535),
        "mono": extra.get("mono", False),
        "depende": extra.get("depende", ""),
        # campos com seção própria no template; ficam no esquema só para
        # validação e permissão de escrita, mas não são renderizados no laço
        "oculto": extra.get("oculto", False),
        "reinicio": chave in REINICIO,
    }
    return campo


def esquema() -> list[dict]:
    """Grupos e campos do formulário, sem valores."""
    return [
        {
            "titulo": "Exibição no terminal",
            "nota": "O que o cliente vê na tela de consulta.",
            "campos": [
                _campo("STORE_NAME", "Nome da loja",
                       exemplo="Supermercado Aurora",
                       ajuda="Aparece no topo do terminal. Deixe vazio para mostrar "
                             "apenas “Terminal de consulta”."),
                _campo("LABEL1", "Rótulo do preço 1", exemplo="Preço"),
                _campo("LABEL2", "Rótulo do preço 2", exemplo="Preço personalizado",
                       ajuda="Só aparece quando o produto tem um segundo preço."),
                _campo("LABEL_NOT_FOUND", "Mensagem de produto não encontrado",
                       exemplo="Produto não encontrado"),
                _campo("CURRENCY", "Moeda", tipo="select", opcoes=MOEDAS,
                       ajuda="Aplicada apenas quando o preço vindo da base não traz "
                             "símbolo. Se a base já grava “R$ 9,90”, esse valor é respeitado."),
                _campo("IDLE_RESET_SECONDS", "Voltar ao início após", tipo="numero",
                       minimo=3, maximo=300,
                       ajuda="Segundos que o resultado fica na tela antes de o terminal "
                             "voltar sozinho ao estado inicial."),
                _campo("SHOW_PRODUCT_IMAGE", "Exibir imagem do produto", tipo="bool",
                       ajuda="Só funciona no protocolo SC504 (TC-506 Mídia e afins). "
                             "Quando ligado e a URL abaixo estiver preenchida, a imagem "
                             "do produto é enviada junto com o preço via IDvShowImg."),
                _campo("PRODUCT_IMAGE_URL", "URL da imagem do produto", mono=True,
                       exemplo="https://cdn-cosmos.bluesoft.com.br/products/{barcode}",
                       ajuda="Modelo de URL. Placeholders: {barcode}, {codigo} ou {gtin} "
                             "são substituídos pelo código lido. Padrão Bluesoft Cosmos: "
                             "https://cdn-cosmos.bluesoft.com.br/products/{barcode} — "
                             "deixe vazio para não buscar imagem."),
            ],
        },
        {
            "titulo": "Base de produtos",
            "campos": [
                _campo("DB_MODE", "Modo", tipo="select", opcoes=MODOS_BASE),
                _campo("PATH_FILE_PRODUCT", "Caminho do arquivo", mono=True,
                       depende="EXTERNAL_TXT",
                       exemplo="/var/arauto/produtos.txt",
                       ajuda="Arquivo UTF-8 no formato código|descrição|preço1|preço2|"),
                _campo("TXT_DB_RELOAD_INTERVAL_MIN", "Recarregar a cada (min)",
                       tipo="numero", minimo=1, maximo=1440, depende="EXTERNAL_TXT"),
                _campo("DB_URL", "Conexão do banco", mono=True, depende="EXTERNAL_SQL",
                       exemplo="firebird+firebird://SYSDBA:masterkey@localhost/C:/produtos/dbvenda.fdb",
                       ajuda="Firebird, PostgreSQL, MySQL/MariaDB, SQL Server ou SQLite. Use Configurar."),
                _campo("DB_PRODUCT_TABLE_NAME", "Tabela", mono=True, depende="EXTERNAL_SQL"),
                _campo("DB_COL_BARCODE", "Coluna do código", mono=True, depende="EXTERNAL_SQL"),
                _campo("DB_COL_BARCODE_ALT", "Coluna de códigos adicional", mono=True,
                       depende="EXTERNAL_SQL",
                       exemplo="REFERENCIA",
                       ajuda="Exceção: usada só quando a coluna do código (código de barras) "
                             "vier vazia na linha. Deixe vazio para ignorar. "
                             "No DBware o PLU da balança costuma estar em REFERENCIA quando "
                             "CODIGO_BARRA está em branco. Plugins leem produto.codigo_adicional "
                             "e service.mapeamento_colunas()."),
                _campo("DB_COL_DESCRIPITION", "Coluna da descrição", mono=True,
                       depende="EXTERNAL_SQL"),
                _campo("DB_COL_PRICE1", "Coluna do preço 1", mono=True, depende="EXTERNAL_SQL"),
                _campo("DB_COL_PRICE2", "Coluna do preço 2", mono=True, depende="EXTERNAL_SQL"),
                _campo("DB_RELOAD_INTERVAL_MIN", "Recarregar a cada (min)", tipo="numero",
                       minimo=1, maximo=1440, depende="EXTERNAL_SQL"),
            ],
        },
        {
            "titulo": "Rede e serviços",
            "nota": "Alterações aqui só valem depois de reiniciar o servidor.",
            "campos": [
                _campo("BIND_HOST", "Endereço de escuta", mono=True,
                       ajuda="0.0.0.0 aceita conexões de qualquer máquina da rede. "
                             "127.0.0.1 restringe ao próprio computador."),
                _campo("PORT_WEBVIEWER", "Porta do WebViewer", tipo="numero",
                       minimo=1, maximo=65535),
                _campo("PORT_API", "Porta da API", tipo="numero", minimo=1, maximo=65535),
                _campo("LOCAL_HOSTNAME", "Nome local (atalho)", mono=True,
                       exemplo="arauto.localhost",
                       ajuda="Padrão: arauto.localhost. O sistema resolve *.localhost "
                             "para 127.0.0.1 sem administrador. "
                             "Painel: http://arauto.localhost:6689/painel."),
                _campo("OPEN_BROWSER_ON_START", "Abrir o painel ao iniciar", tipo="bool",
                       ajuda="Ao subir o servidor, abre o navegador em "
                             "http://arauto.localhost:6689/painel."),
                _campo("AUTO_INIT_501", "Ativar protocolo SC501", tipo="bool",
                       ajuda="TC-406, TC-502, TC-505, TC-507, Busca Preço G2. "
                             "Desligado, a porta SC501 nem é aberta."),
                _campo("LAST_PORT_501", "Porta SC501", tipo="numero",
                       minimo=1, maximo=65535),
                _campo("AUTO_INIT_504", "Ativar protocolo SC504", tipo="bool",
                       ajuda="TC-504, TC-506 Mídia, TC-508, GB-600/601. "
                             "Desligado, a porta SC504 nem é aberta."),
                _campo("LAST_PORT_504", "Porta SC504", tipo="numero",
                       minimo=1, maximo=65535),
                _campo("SC504_FRAME", "Enquadramento SC504", tipo="select",
                       opcoes=FORMATOS_SC504,
                       ajuda="Formato do cabeçalho binário na porta SC504. "
                             "É global (uma porta / um enquadramento para todos). "
                             "Só altere se o terminal não responder."),
                _campo("_div_debug_rede", "Debug de rede", tipo="divisor"),
                _campo("SC501_PASSIVE", "SC501 em modo passivo", tipo="bool",
                       ajuda="O servidor não envia #ok / #live / respostas: só escuta."),
                _campo("SC504_PASSIVE", "SC504 em modo passivo", tipo="bool",
                       ajuda="O servidor não fala primeiro: só escuta o terminal."),
                _campo("PROTOCOL_DEBUG", "Depuração de protocolo", tipo="bool",
                       ajuda="Grava em /logs os bytes trocados com os terminais "
                             "(hex). Só para diagnóstico."),
            ],

        },
        {
            "titulo": "API de integração",
            "campos": [
                _campo("API_KEY", "Chave de acesso", tipo="senha",
                       ajuda="Se preenchida, a API passa a exigir o cabeçalho X-API-Key. "
                             "Vazio deixa a API aberta na rede local."),
                _campo("API_CORS_ORIGINS", "Origens permitidas (CORS)", mono=True,
                       exemplo="*",
                       ajuda="Separadas por vírgula. Use * para liberar todas."),
            ],
        },
        {
            "titulo": "Etiqueta de balança",
            "nota": "Como o código impresso pela balança é interpretado.",
            "campos": [
                _campo("SCALE_ENABLED", "Ler etiquetas de balança", tipo="bool",
                       oculto=True),
                _campo("SCALE_MASK", "Máscara da etiqueta", mono=True, oculto=True),
            ],
        },
        {
            "titulo": "Registro",
            "campos": [
                _campo("LOG_QUERIES", "Registrar consultas", tipo="bool",
                       ajuda="Desligue apenas se o volume for muito alto. Sem isso, o "
                             "relatório de códigos não encontrados deixa de funcionar."),
                _campo("EXPORT_CSV_ENABLED", "Exportar CSV diariamente", tipo="bool"),
                _campo("EXPORT_CSV_ERASE_DAYS", "Apagar registros após (dias)",
                       tipo="numero", minimo=1, maximo=3650),
            ],
        }
    ]


def com_valores(settings: Settings) -> list[dict]:
    """Esquema preenchido com o que está valendo agora."""
    grupos = esquema()
    for grupo in grupos:
        for campo in grupo["campos"]:
            if campo.get("tipo") == "divisor":
                campo["valor"] = ""
                continue
            campo["valor"] = settings.get(campo["chave"])
    return grupos


CHAVES_IMAGEM = {"PRODUCT_IMAGE_PACK_URL", "SHOW_PRODUCT_IMAGE", "PRODUCT_IMAGE_URL"}
CHAVES_EXTRA = CHAVES_IMAGEM | {"AUTOSTART_ENABLED"}

# Nomes genéricos que ainda não foram mapeados pelo usuário/preset.
_TABELAS_GENERICAS = {"", "PRODUCTS", "products", "PRODUTOS"}


def preset_por_id(pid: str) -> dict | None:
    for p in PRESETS_BASE:
        if p.get("id") == pid:
            return p
    return None


def completar_mapeamento_sql(url: str, table: str, cols: dict | None = None, preset_id: str = "") -> tuple[str, dict]:
    """Completa tabela/colunas com o preset (DBware → CAD_PRODUTOS, etc.)."""
    cols = dict(cols or {})
    table = (table or "").strip()
    url = (url or "").strip()
    preset = preset_por_id(preset_id) if preset_id else None
    if preset is None:
        for p in PRESETS_BASE:
            vals = p.get("valores") or {}
            purl = str(vals.get("DB_URL") or "")
            if not purl:
                continue
            scheme = purl.split("://", 1)[0]
            if scheme and scheme in url:
                preset = p
                break
    if preset:
        vals = preset.get("valores") or {}
        if table in _TABELAS_GENERICAS:
            table = str(vals.get("DB_PRODUCT_TABLE_NAME") or table)
        pares = (
            ("barcode", "DB_COL_BARCODE"),
            ("description", "DB_COL_DESCRIPITION"),
            ("price1", "DB_COL_PRICE1"),
            ("price2", "DB_COL_PRICE2"),
            ("barcode_alt", "DB_COL_BARCODE_ALT"),
        )
        for dest, origem in pares:
            if not (cols.get(dest) or "").strip():
                cols[dest] = str(vals.get(origem) or "")
    return table, cols


def chaves_permitidas() -> set[str]:
    return {c["chave"] for g in esquema() for c in g["campos"]} | CHAVES_EXTRA


def validar(chave: str, valor: str) -> str:
    """Devolve uma mensagem de erro, ou string vazia se estiver tudo bem."""
    campos = {c["chave"]: c for g in esquema() for c in g["campos"]}
    if chave.startswith("_"):
        return ""
    campo = campos.get(chave)
    if campo is None:
        # Chaves extras da UI (ex.: PRODUCT_IMAGE_PACK_URL) não estão no
        # esquema de grupos, mas são permitidas e aceitas como texto livre.
        if chave in CHAVES_EXTRA or chave in chaves_permitidas():
            return ""
        return f"Chave desconhecida: {chave}"

    if campo["tipo"] == "numero":
        try:
            numero = int(float(valor))
        except (TypeError, ValueError):
            return f"{campo['rotulo']}: informe um número"
        if not (campo["minimo"] <= numero <= campo["maximo"]):
            return (f"{campo['rotulo']}: use um valor entre "
                    f"{campo['minimo']} e {campo['maximo']}")

    if campo["tipo"] == "select":
        aceitos = [v for v, _ in campo["opcoes"]]
        if valor not in aceitos:
            return f"{campo['rotulo']}: valor inválido"

    if campo["tipo"] == "bool" and valor.lower() not in ("true", "false"):
        return f"{campo['rotulo']}: valor inválido"

    return ""


def validar_conjunto(dados: dict[str, str]) -> list[str]:
    """Valida campo a campo e também as combinações que só fazem sentido juntas."""
    erros = [erro for chave, valor in dados.items()
             if (erro := validar(chave, valor))]

    mascara = dados.get("SCALE_MASK")
    if mascara is not None and dados.get("SCALE_ENABLED", "true").lower() != "false":
        from .scalelabel import Mascara
        erros.extend(Mascara(mascara).validar())

    modo = dados.get("DB_MODE", "")
    if modo == "EXTERNAL_TXT" and not dados.get("PATH_FILE_PRODUCT", "").strip():
        erros.append("Modo arquivo texto exige o caminho do arquivo de produtos")
    if modo == "EXTERNAL_SQL" and not dados.get("DB_URL", "").strip():
        erros.append("Modo banco externo exige a URL de conexão")

    portas = {
        "PORT_WEBVIEWER": dados.get("PORT_WEBVIEWER"),
        "PORT_API": dados.get("PORT_API"),
        "LAST_PORT_501": dados.get("LAST_PORT_501"),
        "LAST_PORT_504": dados.get("LAST_PORT_504"),
    }
    usadas = [p for p in portas.values() if p]
    if len(usadas) != len(set(usadas)):
        erros.append("As portas do WebViewer, da API e dos terminais precisam ser diferentes")

    return erros


def precisa_reiniciar(alterados: set[str]) -> bool:
    return bool(alterados & REINICIO)

def precisa_recarregar_base(alterados: set[str]) -> bool:
    return bool(alterados & RECARGA_BASE)

def precisa_recarregar_terminais(alterados: set[str]) -> bool:
    return bool(alterados & RECARGA_TERMINAIS)


