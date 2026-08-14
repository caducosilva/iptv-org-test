# Resultado dos testes iptv-org (2026-08-10)

## Fontes testadas
- https://iptv-org.github.io/iptv/countries/br.m3u (425 canais, teste completo com ffprobe)
- Amostra de https://iptv-org.github.io/iptv/index.m3u (parcial; muitos geo-blocked/mortos)

## Resultado BR
- OK: 314
- FAIL: 111

### Erros (BR)
| Status | Qtd | Causa tipica |
|--------|-----|--------------|
| TIMEOUT | 39 | servidor lento/offline |
| HTTP_404 | 29 | URL morta na lista publica |
| DNS | 17 | host inexistente |
| TLS_ERROR | 9 | certificado SSL invalido |
| HTTP_403 | 7 | geo-block / anti-leech |
| OTHER/5xx | 10 | stream quebrado |

## Correcoes aplicadas no IPTVnator
1. User-Agent padrao: `VLC/3.0.20 LibVLC/3.0.20` (muitos CDN rejeitam UA vazio)
2. Playlist `teste` (index.m3u global) trocada por `iptv-org BR` (lista do pais, bem menor)
3. Nova playlist arquivo: `BR working (filtrada)` so com canais que passaram no ffprobe

## Arquivos
- Log: Documents/iptv-org-test/results-br/probe_latest.log
- M3U boa: Documents/iptv-org-test/iptvnator-working-br.m3u
- M3U falhas: Documents/iptv-org-test/results-br/failed_latest.m3u
- Script de teste: Documents/iptv-org-test/probe_m3u.py

## Limitacao
Canais 404/DNS/timeout da iptv-org nao da para "consertar" no player: a URL publica esta morta ou bloqueada. A correção util e filtrar e usar UA + player externo (VLC) para streams sensiveis.
