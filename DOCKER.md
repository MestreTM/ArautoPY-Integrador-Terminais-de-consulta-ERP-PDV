# ArautoPY no Docker

Dois caminhos. O primeiro é o que o operador usa no dia a dia.

## 1. Um comando (imagem pronta)

Com Docker instalado:

```bash
docker run -d --name arauto --restart unless-stopped \
  -p 6689:6689 -p 5589:5589 -p 6500:6500 -p 16510:16510 \
  -v arauto-data:/data \
  --add-host host.docker.internal:host-gateway \
  ghcr.io/mestretm/arautopy:latest
```

Painel: http://localhost:6689/painel  
Consulta: http://localhost:6689/  
Setup na primeira subida: http://localhost:6689/setup

Atualizar:

```bash
docker pull ghcr.io/mestretm/arautopy:latest
docker rm -f arauto
# rode de novo o mesmo docker run
```

## 2. Pelo repositório (compose)

```bash
git clone https://github.com/MestreTM/ArautoPY-Integrador-Terminais-de-consulta-ERP-PDV.git
cd ArautoPY-Integrador-Terminais-de-consulta-ERP-PDV
docker compose up -d
```

Se a imagem no GHCR ainda não existir, o Compose constrói na hora.

Parar: `docker compose down`  
Ver log: `docker compose logs -f arauto`

## O que fica salvo

Tudo que na instalação local vai em `~/.arauto` aqui vai no volume `/data`:

- `config.properties`
- bases SQLite
- imagens de produto
- plugins instalados
- layouts

Apagar o container **não** apaga o volume. Para zerar a instalação:

```bash
docker compose down -v
```

## Terminais Gertec

Aponte o terminal para o **IP da máquina que roda o Docker**, portas 6500 (SC501) e 16510 (SC504). As portas TCP estão publicadas no host.

## Banco SQL no computador anfitrião

No assistente / Configurar URL use o host `host.docker.internal` no lugar de `localhost`.

Exemplo PostgreSQL:

```
postgresql+psycopg2://usuario:senha@host.docker.internal:5432/loja
```

O Firebird no Windows do host também entra assim (`host.docker.internal`).

## Variáveis

| Variável | Padrão | Função |
|---|---|---|
| `ARAUTO_HOME` | `/data` | pasta persistente |
| `ARAUTO_DOCKER` | `1` | desliga autostart do SO dentro do container |

Portas e demais opções continuam no `config.properties` do volume, iguais à versão desktop.
