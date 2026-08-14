#!/usr/bin/env python3
"""Monta listas M3U limpas a partir da API publica do iptv-org.

- mantem apenas Brasil, Japao e Estados Unidos
- testa cada stream e guarda so os que respondem
- um arquivo por pais (vira o "pais" no app) e group-title por categoria
  em portugues (vira o "grupo" no app)

Uso:  python tools/build_lists.py [pasta_destino] [--sem-teste]
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

API = "https://iptv-org.github.io/api"
UA = "VLC/3.0.20 LibVLC/3.0.20"
PAISES = {"BR": ("brasil", "Brasil"), "JP": ("japao", "Japão"), "US": ("estados-unidos", "Estados Unidos")}
WORKERS = 60
TIMEOUT = 7.0

# categorias do iptv-org -> grupos em portugues (o resto vira Variedades)
CATEGORIAS = {
    "movies": "Filmes",
    "series": "Séries",
    "news": "Notícias",
    "animation": "Desenhos",
    "kids": "Infantil",
    "sports": "Esportes",
    "documentary": "Documentários",
    "music": "Música",
    "comedy": "Humor",
    "entertainment": "Entretenimento",
    "family": "Família",
    "religious": "Religiosos",
    "education": "Educação",
    "science": "Ciência",
    "culture": "Cultura",
    "business": "Negócios",
    "general": "Abertos e Gerais",
    "public": "Abertos e Gerais",
    "legislative": "Legislativo",
    "cooking": "Culinária",
    "travel": "Viagem",
    "lifestyle": "Estilo de Vida",
    "outdoor": "Natureza",
    "auto": "Automotivo",
    "classic": "Clássicos",
    "weather": "Clima",
    "shop": "Compras",
}
# ordem de preferencia quando o canal tem varias categorias
PRIORIDADE = [
    "news", "movies", "series", "animation", "kids", "sports", "documentary",
    "music", "comedy", "religious", "legislative", "business", "education",
    "science", "culture", "cooking", "travel", "lifestyle", "outdoor", "auto",
    "classic", "weather", "shop", "family", "entertainment", "general", "public",
]

# feeds explicitamente paulistas + emissoras do estado de Sao Paulo
SP_PADRAO = re.compile(
    r"s[aã]o\s*paulo|\bsp\b|paulist|tv\s*cultura|tve\s*cultura|tv\s*gazeta|alesp",
    re.I,
)
# "Cultura Para/Pará" e do Para, nao de SP
SP_EXCECAO = re.compile(r"cultura\s*par[aá]|par[aá]\b", re.I)

# ordem de qualidade para escolher o melhor stream quando o canal se repete
ORDEM_QUALIDADE = {"1080p": 0, "%s" % "1080i": 1, "720p": 2, "576p": 3, "480p": 4, "360p": 5, "240p": 6}


def rank_qualidade(q: str) -> int:
    return ORDEM_QUALIDADE.get((q or "").strip().lower(), 9)


def chave_canal(nome: str) -> str:
    """Normaliza o nome para detectar o mesmo canal repetido."""
    n = nome.lower()
    n = re.sub(r"\((?:\d{3,4}[pi]|[a-z]{2,3})\)", " ", n)  # tira (720p), (br)
    n = re.sub(r"\b\d{3,4}[pi]\b", " ", n)
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return " ".join(n.split())


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def baixar(nome: str) -> list:
    url = f"{API}/{nome}.json"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def escolher_grupo(canal: dict) -> str:
    cats = canal.get("categories") or []
    for chave in PRIORIDADE:
        if chave in cats:
            return CATEGORIAS.get(chave, "Variedades")
    return "Variedades"


def testar(url: str) -> tuple[bool, str]:
    """True se o stream responde e parece midia."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = getattr(resp, "status", 200)
            if status >= 400:
                return False, f"HTTP {status}"
            bruto = resp.read(2048)
            ctype = (resp.headers.get("Content-Type") or "").lower()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:60]

    texto = bruto.decode("utf-8", "replace")
    if "#EXTM3U" in texto or "mpegurl" in ctype or "video" in ctype or "octet-stream" in ctype:
        return True, "ok"
    if len(bruto) >= 512:
        return True, "ok-binario"
    return False, "resposta vazia"


def main() -> int:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else Path("D:/IPTV")
    sem_teste = "--sem-teste" in sys.argv
    destino.mkdir(parents=True, exist_ok=True)

    log("baixando catalogo do iptv-org...")
    canais = {c["id"]: c for c in baixar("channels")}
    streams = baixar("streams")
    log(f"  {len(canais)} canais, {len(streams)} streams")

    # junta stream + metadados do canal, so BR/JP/US, sem adulto, sem duplicado
    candidatos: list[dict] = []
    vistos: set[str] = set()
    for s in streams:
        cid = s.get("channel")
        if not cid or cid not in canais:
            continue
        canal = canais[cid]
        pais = canal.get("country")
        if pais not in PAISES or canal.get("is_nsfw"):
            continue
        url = (s.get("url") or "").strip()
        if not url or url in vistos:
            continue
        vistos.add(url)
        nome = (s.get("title") or canal.get("name") or "").strip()
        if not nome:
            continue
        qualidade = (s.get("quality") or "").strip()
        grupo = escolher_grupo(canal)
        if pais == "BR" and SP_PADRAO.search(nome) and not SP_EXCECAO.search(nome):
            grupo = "São Paulo"
        candidatos.append(
            {
                "pais": pais,
                "nome": nome,
                "url": url,
                "grupo": grupo,
                "qualidade": qualidade,
                "chave": f"{pais}|{chave_canal(nome)}",
            }
        )

    log(f"candidatos apos filtro BR/JP/US: {len(candidatos)}")
    for p in PAISES:
        log(f"  {p}: {sum(1 for c in candidatos if c['pais'] == p)}")

    # testa quais realmente respondem
    if sem_teste:
        vivos = candidatos
        log("pulando teste de streams (--sem-teste)")
    else:
        log(f"testando {len(candidatos)} streams com {WORKERS} conexoes simultaneas...")
        vivos = []
        inicio = time.time()
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futuros = {pool.submit(testar, c["url"]): c for c in candidatos}
            feitos = 0
            for fut in as_completed(futuros):
                c = futuros[fut]
                feitos += 1
                try:
                    ok, _motivo = fut.result()
                except Exception:  # noqa: BLE001
                    ok = False
                if ok:
                    vivos.append(c)
                if feitos % 300 == 0:
                    log(f"  {feitos}/{len(candidatos)} testados, {len(vivos)} vivos "
                        f"({time.time() - inicio:.0f}s)")
        log(f"teste concluido em {time.time() - inicio:.0f}s: {len(vivos)} vivos de {len(candidatos)}")

    # o mesmo canal costuma ter varias URLs; fica so a de melhor qualidade
    antes = len(vivos)
    melhor: dict[str, dict] = {}
    for c in vivos:
        atual = melhor.get(c["chave"])
        if atual is None or rank_qualidade(c["qualidade"]) < rank_qualidade(atual["qualidade"]):
            melhor[c["chave"]] = c
    vivos = list(melhor.values())
    log(f"deduplicado por canal: {antes} -> {len(vivos)} (removidas {antes - len(vivos)} repeticoes)")

    # escreve um arquivo por pais
    resumo = {}
    for cod, (arquivo, rotulo) in PAISES.items():
        itens = [c for c in vivos if c["pais"] == cod]
        itens.sort(key=lambda c: (c["grupo"].lower(), c["nome"].lower()))
        caminho = destino / f"{arquivo}.m3u"
        linhas = ["#EXTM3U"]
        for c in itens:
            nome = c["nome"] + (f" ({c['qualidade']})" if c["qualidade"] else "")
            linhas.append(f'#EXTINF:-1 group-title="{c["grupo"]}",{nome}')
            linhas.append(c["url"])
        caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        grupos = {}
        for c in itens:
            grupos[c["grupo"]] = grupos.get(c["grupo"], 0) + 1
        resumo[rotulo] = {"arquivo": caminho.name, "canais": len(itens), "grupos": grupos}
        log(f"gravado {caminho.name}: {len(itens)} canais, {len(grupos)} grupos")

    (destino / "_resumo_listas.json").write_text(
        json.dumps({"gerado_em": datetime.now().isoformat(), "paises": resumo}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print()
    log("RESUMO")
    for rotulo, info in resumo.items():
        log(f"  {rotulo}: {info['canais']} canais")
        for g, n in sorted(info["grupos"].items(), key=lambda x: -x[1]):
            log(f"      {g}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
