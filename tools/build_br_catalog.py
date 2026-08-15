#!/usr/bin/env python3
"""Monta um catalogo so do Brasil, categorizado, com secao de Mogi.

Junta as fontes publicas (iptv-org) com as listas locais grandes, mantem apenas
o que da para confirmar que e do Brasil, tira repetido pela URL, arruma o
group-title em categorias que o painel entende e marca os canais de Mogi.

Saida: uma unica lista `brasil-completo.m3u` na pasta de listas. As listas
antigas de outros paises vao para `archive/` para o catalogo ficar so do Brasil.

Uso:
    python tools/build_br_catalog.py            # usa a pasta padrao (lists/)
    python tools/build_br_catalog.py --sem-rede # so fontes locais

Codigos de saida: 0 = ok, 1 = nada gerado, 2 = pasta de listas nao encontrada.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LISTS = ROOT / "lists"
# As listas cruas ficam numa subpasta que o backend nao le (ele faz glob so no
# topo de lists/) e que este script nunca arquiva. Antes, as fontes moravam no
# topo e o proprio script as arquivava, entao a segunda execucao rodava vazia.
FONTES = LISTS / "_fontes"
ARCHIVE = ROOT / "archive" / "nao-brasil"

EXTINF_RE = re.compile(r"#EXTINF:-?\d+([^,]*),(.*)")
TVG_ID_RE = re.compile(r'tvg-id="([^"]*)"', re.I)
TVG_LOGO_RE = re.compile(r'tvg-logo="([^"]*)"', re.I)
GROUP_RE = re.compile(r'group-title="([^"]*)"', re.I)

# Fontes publicas. Sao de melhor esforco: a que falhar e so ignorada.
FONTES_REMOTAS = [
    ("https://iptv-org.github.io/iptv/countries/br.m3u", "br"),
    ("https://iptv-org.github.io/iptv/languages/por.m3u", "auto"),
]

# Listas locais grandes que ja estao no repositorio. Filtradas para o Brasil.
FONTES_LOCAIS = [
    "index.m3u",
    "M3Ulistagigante.txt",
    "geral-categoria.m3u",
    "country-br.m3u",
    "brasil.m3u",
    "br.m3u",
    "mogi-globo-tv-diario.m3u",
]

# group-title -> (chave da categoria, rotulo). O painel tambem mapeia, mas
# normalizar aqui deixa a lista limpa e a segregacao consistente.
CATEGORIAS = {
    "general": "Abertos", "public": "Abertos", "local": "Abertos",
    "aberto": "Abertos", "abertos": "Abertos", "tv aberta": "Abertos",
    "news": "Notícias", "noticias": "Notícias", "notícias": "Notícias", "jornalismo": "Notícias",
    "movies": "Filmes", "movie": "Filmes", "filmes": "Filmes", "cinema": "Filmes",
    "series": "Séries", "série": "Séries", "séries": "Séries", "novelas": "Séries",
    "kids": "Infantil", "infantil": "Infantil", "desenhos": "Infantil",
    "animation": "Animação", "anime": "Animação",
    "sports": "Esportes", "esportes": "Esportes", "futebol": "Esportes",
    "documentary": "Documentários", "documentarios": "Documentários", "documentários": "Documentários",
    "music": "Música", "musica": "Música", "música": "Música",
    "religious": "Religioso", "religioso": "Religioso", "religiosos": "Religioso",
    "entertainment": "Entretenimento", "variedades": "Entretenimento",
    "education": "Educação", "educação": "Educação",
    "legislative": "Legislativo",
    "culture": "Cultura", "science": "Ciência", "shop": "Compras",
    "outdoor": "Ar livre", "cooking": "Culinária", "auto": "Automotivo",
    "weather": "Clima", "travel": "Viagem", "family": "Família",
}

# Emissoras abertas: quando a categoria vem vazia, cai aqui como "Abertos".
ABERTOS_BR = re.compile(
    r"\b(globo|sbt|record|band|bandeirantes|redetv|rede tv|cultura|tv brasil|"
    r"gazeta|rede vida|cancao nova|canção nova|aparecida|tv camara|tv câmara|"
    r"tv senado|tv assembleia|tv justica|tv justiça|tv escola)\b",
    re.I,
)

# Marcadores tecnicos que sujam o nome para quem le.
LIXO_NOME = re.compile(
    r"\s*[\[(]\s*(\d{3,4}p|\d{3,4}i|4k|uhd|fhd|hd|sd|hq|geo[-\s]?blocked|not\s*24/?7|"
    r"offline|backup|multi[-\s]?audio)\b[^\])]*[\])]",
    re.I,
)

# So "mogi": "tv diario" solto arrastava a TV Diario de Fortaleza (Verdes
# Mares), a do Sertao (PB) e a de Macapa (AP), que nao sao de Mogi. A de Mogi
# sempre traz "Mogi das Cruzes" no nome.
MOGI_RE = re.compile(r"\bmogi\b", re.I)

# Nomes que denunciam que NAO e Brasil, para nao entrar por engano.
NAO_BR = re.compile(
    r"\b(portugal|rtp|sic|cmtv|benfica tv|angola|mo[cç]ambique|usa|u\.s\.|america\b)",
    re.I,
)


def baixar(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 catalogo-br"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def pais_do_tvg_id(tvg_id: str) -> str:
    base = (tvg_id or "").split("@", 1)[0].strip()
    if "." not in base:
        return ""
    code = base.rsplit(".", 1)[-1].strip().lower()
    return code if len(code) == 2 and code.isalpha() else ""


def limpar_nome(nome: str) -> str:
    limpo = LIXO_NOME.sub("", nome).strip()
    limpo = re.sub(r"\s{2,}", " ", limpo)
    return limpo or nome.strip()


def categoria_de(grupo: str, nome: str) -> str:
    """Primeira categoria reconhecida no group-title, com regras para o Brasil."""
    for parte in re.split(r"[;,/|]", grupo or ""):
        termo = parte.strip().lower()
        if termo in CATEGORIAS:
            return CATEGORIAS[termo]
    if ABERTOS_BR.search(nome):
        return "Abertos"
    return "Entretenimento"


class Canal:
    __slots__ = ("nome", "tvg_id", "logo", "grupo", "url")

    def __init__(self, nome, tvg_id, logo, grupo, url):
        self.nome = nome
        self.tvg_id = tvg_id
        self.logo = logo
        self.grupo = grupo
        self.url = url


def parse_m3u(texto: str) -> list[Canal]:
    canais: list[Canal] = []
    extinf: str | None = None
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("#EXTINF:"):
            extinf = linha
        elif linha.startswith("#"):
            continue
        elif extinf is not None:
            m = EXTINF_RE.match(extinf)
            nome = m.group(2).strip() if m else "Canal"
            attrs = m.group(1) if m else ""
            tvg = TVG_ID_RE.search(attrs)
            logo = TVG_LOGO_RE.search(attrs)
            grupo = GROUP_RE.search(attrs)
            canais.append(Canal(
                nome=nome,
                tvg_id=tvg.group(1) if tvg else "",
                logo=logo.group(1) if logo else "",
                grupo=grupo.group(1) if grupo else "",
                url=linha,
            ))
            extinf = None
    return canais


def eh_brasil(canal: Canal, origem_pais: str) -> bool:
    pais = pais_do_tvg_id(canal.tvg_id)
    if pais:
        return pais == "br"
    if origem_pais == "br":
        return True
    if NAO_BR.search(canal.nome) or NAO_BR.search(canal.grupo):
        return False
    # Sem tvg-id de pais e sem origem garantida: so entra se o nome for de
    # emissora brasileira conhecida, para nao arrastar canal de fora.
    return bool(ABERTOS_BR.search(canal.nome) or MOGI_RE.search(canal.nome))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-rede", action="store_true", help="usa so as listas locais")
    args = ap.parse_args()

    if not LISTS.exists():
        print(f"ERRO: pasta de listas nao encontrada: {LISTS}", file=sys.stderr)
        return 2

    brutos: list[tuple[Canal, str]] = []

    if not args.sem_rede:
        for url, origem in FONTES_REMOTAS:
            try:
                texto = baixar(url)
                canais = parse_m3u(texto)
                brutos += [(c, origem) for c in canais]
                print(f"rede  {len(canais):5d}  {url}")
            except Exception as e:  # rede e melhor esforco
                print(f"pulei (rede) {url}: {e}", file=sys.stderr)

    for nome_arq in FONTES_LOCAIS:
        caminho = FONTES / nome_arq
        if not caminho.exists():
            continue
        try:
            canais = parse_m3u(caminho.read_text(encoding="utf-8", errors="replace"))
            origem = "br" if re.search(r"\b(br|brasil)\b|mogi", nome_arq) else "auto"
            brutos += [(c, origem) for c in canais]
            print(f"local {len(canais):5d}  {nome_arq}")
        except OSError as e:
            print(f"pulei (local) {nome_arq}: {e}", file=sys.stderr)

    vistos: set[str] = set()
    finais: list[Canal] = []
    mogi = 0
    for canal, origem in brutos:
        if not canal.url or canal.url in vistos:
            continue
        if not eh_brasil(canal, origem):
            continue
        vistos.add(canal.url)
        canal.nome = limpar_nome(canal.nome)
        if MOGI_RE.search(canal.nome) or MOGI_RE.search(canal.grupo) or MOGI_RE.search(canal.tvg_id):
            canal.grupo = "Mogi"
            mogi += 1
        else:
            canal.grupo = categoria_de(canal.grupo, canal.nome)
        finais.append(canal)

    if not finais:
        print("ERRO: nenhum canal brasileiro no resultado", file=sys.stderr)
        return 1

    # Mogi primeiro, depois por categoria e nome, para a lista sair organizada
    ordem_cat = {"Mogi": 0, "Abertos": 1, "Notícias": 2, "Filmes": 3, "Séries": 4,
                 "Infantil": 5, "Esportes": 6, "Documentários": 7, "Música": 8}
    finais.sort(key=lambda c: (ordem_cat.get(c.grupo, 50), c.grupo, c.nome.lower()))

    # Nome "brasil.m3u" de proposito: o backend deduz o pais pelo nome do
    # arquivo quando o canal nao traz .br no tvg-id, e assim os ~300 canais sem
    # codigo entram como Brasil em vez de "sem pais identificado".
    destino = LISTS / "brasil.m3u"
    linhas = ["#EXTM3U"]
    for c in finais:
        linhas.append(
            f'#EXTINF:-1 tvg-id="{c.tvg_id}" tvg-logo="{c.logo}" '
            f'group-title="{c.grupo}",{c.nome}'
        )
        linhas.append(c.url)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    # Arquiva as listas que nao sao do Brasil, para o catalogo ficar so BR
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    manter = {"brasil.m3u", "cameras-casa.m3u"}
    movidos = 0
    for arq in list(LISTS.glob("*.m3u")) + list(LISTS.glob("*.m3u8")) + list(LISTS.glob("*.txt")):
        if arq.name in manter:
            continue
        try:
            arq.rename(ARCHIVE / arq.name)
            movidos += 1
        except OSError as e:
            print(f"nao movi {arq.name}: {e}", file=sys.stderr)

    porcat: dict[str, int] = {}
    for c in finais:
        porcat[c.grupo] = porcat.get(c.grupo, 0) + 1

    print(f"\nOK: {len(finais)} canais do Brasil em {destino.name} (Mogi: {mogi})")
    print(f"listas de fora do Brasil arquivadas: {movidos} -> {ARCHIVE}")
    for cat, n in sorted(porcat.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d}  {cat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
