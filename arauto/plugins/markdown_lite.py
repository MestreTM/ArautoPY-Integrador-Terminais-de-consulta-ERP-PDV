"""Conversor Markdown → HTML suficiente para a documentação de plugins."""

from __future__ import annotations

import html
import re


def para_html(texto: str) -> str:
    texto = texto.replace("\r\n", "\n")
    linhas = texto.split("\n")
    out: list[str] = []
    i = 0
    in_code = False
    code_lang = ""
    code_buf: list[str] = []
    in_ul = False
    in_ol = False
    in_table = False
    table_rows: list[list[str]] = []

    def fecha_listas() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def fecha_tabela() -> None:
        nonlocal in_table, table_rows
        if not in_table:
            return
        if table_rows:
            out.append("<table>")
            for ri, row in enumerate(table_rows):
                if ri == 1 and all(re.match(r"^:?-+:?$", c.strip()) for c in row):
                    continue  # separator
                tag = "th" if ri == 0 else "td"
                out.append("<tr>" + "".join(f"<{tag}>{inline(c.strip())}</{tag}>" for c in row) + "</tr>")
            out.append("</table>")
        in_table = False
        table_rows = []

    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    while i < len(linhas):
        line = linhas[i]
        if line.startswith("```"):
            if not in_code:
                fecha_listas()
                fecha_tabela()
                in_code = True
                code_lang = line[3:].strip()
                code_buf = []
            else:
                out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
                in_code = False
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        if "|" in line and line.strip().startswith("|"):
            fecha_listas()
            cells = [c for c in line.strip().strip("|").split("|")]
            if not in_table:
                in_table = True
                table_rows = []
            table_rows.append(cells)
            i += 1
            continue
        else:
            fecha_tabela()

        if re.match(r"^---+$", line.strip()):
            fecha_listas()
            out.append("<hr>")
            i += 1
            continue

        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            fecha_listas()
            nivel = len(m.group(1))
            out.append(f"<h{nivel}>{inline(m.group(2))}</h{nivel}>")
            i += 1
            continue

        if re.match(r"^[-*]\s+", line):
            if not in_ul:
                fecha_listas()
                out.append("<ul>")
                in_ul = True
            out.append("<li>" + inline(re.sub(r"^[-*]\s+", "", line)) + "</li>")
            i += 1
            continue

        if re.match(r"^\d+\.\s+", line):
            if not in_ol:
                fecha_listas()
                out.append("<ol>")
                in_ol = True
            out.append("<li>" + inline(re.sub(r"^\d+\.\s+", "", line)) + "</li>")
            i += 1
            continue

        if not line.strip():
            fecha_listas()
            i += 1
            continue

        fecha_listas()
        out.append("<p>" + inline(line) + "</p>")
        i += 1

    fecha_listas()
    fecha_tabela()
    if in_code:
        out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
    return "\n".join(out)


