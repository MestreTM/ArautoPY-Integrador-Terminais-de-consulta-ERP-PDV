# Notas da engenharia reversa

O que foi levantado do `tc-server_jar-2_7_1.jar` (Gertec TC Server 2.7.1), das
capturas de tráfego com hardware real e do *Manual de Desenvolvimento —
Protocolo TC506-Mídia V.1.0.1 R00.22*.

---

## Método

Sem descompilador. Foi feito um extrator de *constant pool* das classes `.class`
mais um desmontador de bytecode simples, o que revela identificadores, formatos
e valores literais — mas não o fluxo completo. Daí a regra que valeu o projeto
inteiro: **o que veio do JAR é indício; o que veio de captura é fato.**

Ferramentas construídas ao longo do caminho, todas no próprio programa:

| Ferramenta | Para quê |
|---|---|
| `--proxy` | Fica entre o terminal e o TC Server original e grava a conversa dos dois lados |
| `--sniffer` | Escuta uma porta e testa oito hipóteses de enquadramento |
| `/monitor` | Tráfego cru, sempre gravado, sem depender de sinalizador |
| `--analisar` | Relê uma sessão gravada e imprime a conversa decodificada |

O intermediador foi o que destravou o projeto: em vez de deduzir o protocolo,
lemos o servidor que já funcionava.

---

## Confirmado pelo manual oficial

O manual do TC506-Mídia validou o que tinha sido inferido:

| Item | Manual | Implementação |
|---|---|---|
| Quadro | `STX` 1 byte (0x02) · `ID` 2 bytes · `Tam Arg` 4 bytes | `B-H-I-LE`, cabeçalho 7 bytes |
| Ordem dos bytes | LITTLE ENDIAN | confere |
| Porta | 16510 | confere |
| `IDwGetIdentify` | resposta `3101FAxx` | captura real: `3101fa50` |
| `IDContinue` | argumento 1 aceita, 0 recusa | confere |
| `IDRestart` | argumento `0x5A33A5CC` | `RESTART_PASSWORD = 1513334220` |
| Desconexão | "mais de 1 minuto sem receber comandos" | explica as sessões de 61 s do campo |

Uma correção que o manual trouxe: **as cores não são a paleta `NamedColor` do
JAR.** O manual diz que a cor é "uma posição na paleta de cores usada pelo
terminal (0 a 255) **ou** uma cor padrão usada no terminal". Os valores
observados na captura — `263` no texto, `-1` sem fundo, `260` no `DispClear` —
estão fora de 0–255, então são as tais "cores padrão", constantes próprias do
firmware. A tabela existe no manual, mas como imagem, e não saiu na extração de
texto. **Replicamos os valores observados sem decifrá-los.**

---

## Sequência de conexão

```
0.013s ← ID_W_GET_IDENTIFY (19)      sem dados
0.303s → R_ID_W_GET_IDENTIFY (20)    4 bytes: 31 01 fa 50
0.316s ← ID_CONTINUE (21)            dword 1        ← conclui o handshake
0.500s → R_ID_CONTINUE (22)
0.503s ← ID_V_GET_UID (27)
1.011s → R_ID_V_GET_UID (28)         MAC(6) + nome(32) = "TC506-Media"
1.018s ← ID_V_LIVE (17)              e a cada 10 s daí em diante
```

`IDContinue` é obrigatório: sem ele o terminal responde a consultas mas segue
exibindo **desconectado**.

### RIDwGetIdentify — 4 bytes

`getData` no bytecode: `put(49)`, `putShort(termType, BIG_ENDIAN)`, `put(...)`.

```
31 | 01 fa | 50
│    │       └ versão em dígitos hex lidos como decimal (hexToDec)
│    └ termType BIG-ENDIAN = 0x01FA = 506 = TC-506 Mídia
└ marcador fixo 0x31
```

Ler little-endian a partir do byte 0 dava 305 e nunca casava — era o "tipo 49"
que aparecia no log (0x31 = 49).

### O modelo exato vem do UID

`R_ID_V_GET_UID` = 6 bytes de MAC + 32 bytes com o nome:

```
00 1d 5b 02 05 be | "TC506-Media" + zeros
```

É daí que o servidor original tira o nome que exibe, não do `termType`.

---

## Consulta de preço

`IDbReadScanner` (89) → `ArgSerialData`: `codeLen` (short LE) + `code` num
buffer de 256 bytes.

```
02 59 00 02 01 00 00 | 0d 00 | 37 38 39 ... | 00 …
│  │     │             │       │              └ lixo (memória não inicializada)
│  │     │             │       └ "7891150037342" (13 bytes)
│  │     │             └ codeLen = 13
│  │     └ TAMANHO = 258 = 2 + CODE_MAX_LENGTH(256)  → 7 + 258 = 265 ✓
│  └ ID = 89
└ STX = 2
```

O bug que custou mais tempo: a implementação decodificava o buffer inteiro como
texto e cortava no primeiro NUL. Como o primeiro byte é o comprimento (`0x0d`)
e o segundo é `0x00`, o resultado era string vazia — o servidor mandava só o ACK
e nunca o texto do display. O terminal esperava, batia o timeout de 61 s e
desconectava.

### ArgDisplayText

```
posX (short) | posY (short) | text (128 bytes) | font (32 bytes)
| fontSize (short) | fontColor (short) | backgroundColor (short)
```

Fontes são **arquivos TrueType do aparelho** (`DejaVuSans.ttf`,
`DejaVuSans-Bold.ttf`). Pedir `"Arial"` — que não existe nele — faz o terminal
não desenhar nada: foi a causa da tela preta.

---

## Imagens no terminal

O manual documenta dois caminhos, e cada família de terminal usa o seu. Ambos
estão implementados em `core/product_image.py` e nos módulos de protocolo.

### SC504 — `IDvShowImg` (37), bitmap indexado

O manual é explícito:

> Como argumento o terminal deve enviar a paleta de cores contendo 768 bytes,
> 3 bytes por cor (RGB) e 256 cores: `R0,G0,B0,R1,G1,B1, ... R255,G255,B255`.
> Seguidos dos bytes indicando a cor usada em cada pixel da imagem.
> A imagem possui 480 × 272 pixels, totalizando no máximo 130.560 bytes.

Ou seja, um bitmap de **8 bits com paleta embutida** — sem compressão, sem
cabeçalho de formato:

```
┌──────────────────────┬────────────────────────────────┐
│ paleta 768 bytes     │ índices 130.560 bytes          │
│ 256 cores × RGB      │ 1 byte por pixel, 480×272      │
└──────────────────────┴────────────────────────────────┘
                 argumento total: 131.328 bytes
```

Conferido na implementação: `montar_payload_imagem()` produz exatamente
131.328 bytes, com paleta de 768 e 130.560 índices.

**Pipeline.** A foto vem de uma URL montada a partir de `PRODUCT_IMAGE_URL`
(com `{barcode}` substituído), é baixada com timeout curto, redimensionada e
quantizada para 256 cores com *median cut* do Pillow. O resultado fica em cache
por código, porque quantizar 130 mil pixels a cada consulta seria desperdício.

**A imagem é sempre de tela cheia** — o terminal não tem noção de "colar num
retângulo". Para colocar a foto numa região e deixar o resto livre para o texto,
o servidor monta um canvas 480×272 na cor de fundo, encaixa a foto dentro da
caixa definida no elemento `imagem` do layout, e envia o conjunto. O recorte é
nosso, não do aparelho.

**Ordem de envio:** `IDvDispClear` → `IDvShowImg` → os `IDvShowText`. O texto é
desenhado por cima da imagem, e por isso o `backgroundColor = -1` (sem fundo)
importa: com fundo opaco, cada linha de texto apagaria um retângulo da foto.

**Pillow é opcional.** Sem ele, o módulo registra um aviso e a consulta segue só
com texto, em vez de derrubar o atendimento.

### SC501 — `#img`, JPEG comprimido

O Busca Preço G2 E não usa bitmap indexado; recebe o arquivo JPEG ou BMP direto,
com um cabeçalho ASCII:

```
#img + índice(2) + loops(2) + tempo(2) + tamanho(6) + checksum(4) + ETB(0x17) + bytes
       ASCII hex   ASCII hex  ASCII hex  ASCII hex     "0000"
```

- **índice** `"00"` = exibição imediata
- **tempo** é o valor decimal convertido para hex e escrito como texto: 12 s →
  `0x0C` → `"0C"`
- **checksum** vai `"0000"`; o equipamento não valida

O limite é **45 KB**, porque a memória é compartilhada com o áudio. Por isso o
preparo é diferente do SC504: em vez de quantizar, o servidor recomprime o JPEG
tentando qualidades decrescentes (85 → 25) e, se ainda não couber, reduz a
resolução (320 → 120 px). Só desiste se nada couber.

O terminal responde `#img_ok` ou `#img_error`, possivelmente com dígitos de
índice colados (`#img_ok00`) — o *parser* precisa tolerar isso.

### O que ainda não foi feito

- **`IDvSendPalette` (133)** — enviar só a paleta, para quando as cores padrão
  do terminal não servirem. Não implementado; hoje cada imagem carrega a sua.
- **Vídeo e GIF** — o TC506-Mídia aceita AVI e GIF via `medias.conf`, mas isso é
  gerência de mídia (slideshow), não resposta de consulta.
- **Cores padrão** — a tabela do manual está em imagem e não foi extraída. Os
  valores `260`/`263`/`-1` funcionam por replicação, não por entendimento.

---

## `IDvPlayAudio` — áudio da consulta

A captura mostra o original enviando ~25 KB por consulta:

```
ARG_AUDIO_DATA (128 bytes: volume + nome) + bytes do MP3
nome observado: "dquery001D5B0205BE.mp3"   ← o MAC do terminal no nome
```

É a locução do preço, gerada pelo Rybená (o JAR embarca FFmpeg e MBROLA para
isso). **Não implementado** — o display funciona sem, mas o terminal fica mudo.
O manual também documenta `IDSetAudioQuery`/`IDGetAudioQuery` para ligar e
desligar esse áudio no aparelho.

---

## Modo Web — a alternativa que dispensa tudo isso

O manual descreve um segundo modo de operação em que o terminal **não** usa o
protocolo binário: ele busca `price_checker.xml` e `media_manager.xml` numa URL
e, a cada leitura, faz uma requisição HTTP trocando `<barcode>` pelo código.

```xml
<price_checker version="0.1.0">
  <urls>
    <url id="url1" value="http://servidor/preco?codigo=&lt;barcode&gt;"/>
  </urls>
</price_checker>
```

O servidor responde com HTML otimizado para 480×272. É por isso que havia um
`res/price_checker.xml` dentro do JAR original.

**Isso é relevante para o ArautoPY**: o WebViewer já entrega exatamente esse
tipo de página. Um terminal TC506-Mídia em modo Web poderia consumir o
`/consulta/{codigo}` direto, sem SC504, sem enquadramento binário e sem
quantização de imagem — ao custo de perder a tela de layout controlada pelo
servidor. Caminho não explorado, mas o mais barato para novos modelos.

Cuidados do manual para o HTML: WebKit do Qt 4.7.4 (2011), memória limitada, e
`body { margin:0; width:100%; height:100%; overflow:hidden; }` para evitar
barras de rolagem.

---

## Tabela de comandos SC504

Extraída de `Sc504CommDefs` (109 constantes). A resposta é sempre
`requisição + 1`.

**Armadilha:** a paridade não separa requisição de resposta. De 17 a 121 as
requisições são ímpares; de 166 (`ID_SHOW_LOCAL_MEDIA`) em diante são **pares**.
Uma implementação baseada em paridade ignora silenciosamente todo o bloco de
áudio, vídeo, sensores e brilho.

| Classe base | Payload |
|---|---|
| `WordCommand` | short LE (2 bytes) |
| `DwordCommand` | int LE (4 bytes) |
| `Tc504Command` | estrutura própria |

`IDvDispClear` é `WordCommand` — leva a cor de fundo, **não vem vazio**.

### TerminalType

`sc504Id` não é índice sequencial; é o número do modelo:

| sc504Id | Modelo | Tela |
|---|---|---|
| 504 | TC-504 | 320×240 |
| 506 | TC-506 Mídia | 480×272 |
| 508 | TC-508 | 480×272 |
| 600 | G-BOT | 1280×800 |
| 601 | G-BOT - 2 | 1280×800 |

Terminais SC501 têm `sc504Id` nulo e usam `sc501Id` (`#tc406`, `#tc502`…).

---

## Protocolo SC501

ASCII, ISO-8859-1. O terminal termina seus quadros com NUL; **o servidor não**
— confirmado por captura com o Busca Preço G2. O `_drain` aceita os dois
formatos porque o terminal mistura (`#tc406|4.0\0` e `#live` sem NUL).

Handshake observado no original:

```
terminal → #tc406
servidor → #ok
servidor → #macaddr?9      ← o "9" não está no manual, mas o G2 responde
servidor → #updconfig?
servidor → #live?          ← keep-alive a cada ~10 s
```

Resposta de produto: `#Ms:<descrição>|L:<rótulo> V:<preço>`.

---

## Registro de campo

**13/08/2026 — primeiro terminal SC504 real (192.168.10.20).**

- Sessões de exatos 61 segundos: timeout do terminal, não erro de dado.
- Blocos de 265 bytes a cada ~45 s.
- Com enquadramento `B-H-I-LE`, um quadro trouxe primeiro byte 49 (`0x31`).
  O tipo 49 não existe na tabela: era coincidência, não identificação.

Duas correções decorrentes, ambas sobre **honestidade do software**:

1. `identificar()` passou a **recusar** tipo fora da tabela e avisar que o
   enquadramento provavelmente está errado. Antes registrava "identificado como
   SC504 tipo 49" e seguia — um falso positivo que calava o log justamente
   quando havia problema.
2. O tráfego passou a ser gravado **incondicionalmente**. Esconder os bytes
   atrás de `PROTOCOL_DEBUG` deixava o operador sem informação exatamente no
   cenário em que ela é necessária.


