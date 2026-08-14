# IPTV Cast Companion

Painel local para assistir IPTV aberto no PC e jogar o canal na TV da sala, com
verificação de saúde dos streams antes de você clicar. Nasceu de um teste com as
listas públicas do iptv-org e virou uma ferramenta de uso diário.

**Licença:** [MIT](LICENSE)

---

## O problema

1. **O que é:** um backend Python que testa, organiza e transmite canais IPTV,
   com um painel React que roda no navegador em modo aplicativo.
2. **Qual necessidade ataca:** as listas públicas de IPTV têm centenas de canais,
   e boa parte deles está morta. Descobrir isso um clique por vez é insuportável.
3. **Por que existe:** os players prontos, como o IPTVnator, engasgam com lista
   grande, não avisam qual canal está fora do ar e não têm um caminho decente
   para mandar o vídeo à TV.
4. **Qual o objetivo:** abrir o painel, ver na hora quais canais estão vivos e
   escolher entre assistir no PC ou transmitir para a TV, sem tentativa e erro.

---

## Recursos

- **Verificação de saúde dos canais** com quatro estados: ok, dúvida, morto e
  confirmado, com regra explícita contra falso negativo.
- **Transmissão para a TV** por DLNA e Chromecast, com descoberta automática dos
  aparelhos da rede.
- **Organização das listas** por país, idioma, categoria e grupo, a partir das
  fontes públicas do iptv-org.
- **Player externo MPV** para os streams que o navegador se recusa a tocar.
- **Instância única**, com trava em arquivo. Fechar a janela do Chrome derruba o
  servidor e libera as portas.

---

## Instalação

### Pré-requisitos

- Python 3.10 ou superior
- Node.js 20 ou superior
- ffmpeg, para o `ffprobe` usado no teste dos canais
- MPV, opcional, para os canais que o navegador não toca

### Passos

```bash
git clone https://github.com/caducosilva/iptv-org-test.git
cd iptv-org-test
cd frontend && npm install && cd ..
```

---

## Como usar

```bash
python iniciar_iptv_app.py
```

Ou dê duplo clique em `INICIAR-IPTV.bat`.

O launcher sobe a API em `127.0.0.1:8769`, a interface em `127.0.0.1:3000` e abre
o Chrome em modo aplicativo com perfil próprio.

Testar a saúde de uma lista pela linha de comando:

```bash
python tools/probe_m3u.py lists/br.m3u
```

---

## Detalhes técnicos relevantes

### Por que um canal só morre depois de três falhas

Stream de IPTV aberto oscila. Um timeout isolado quase nunca significa canal
morto, significa CDN ocupado. Por isso o cache de saúde só marca como morto
depois de três falhas seguidas, ou de uma falha dura que não deixa dúvida, como
DNS inexistente, 404 ou conexão recusada. Timeout vira dúvida, não morte.

Canal que já transmitiu com sucesso para a TV fica marcado como confirmado e não
some mais no filtro de esconder mortos, mesmo que uma varredura futura falhe.

### O que o teste com as listas públicas mostrou

Medição sobre a lista brasileira do iptv-org, com `ffprobe` em todos os canais:

| Resultado | Quantidade |
|---|---|
| Tocaram | 314 |
| Falharam | 111 |

Distribuição das falhas:

| Causa | Quantidade |
|---|---|
| Timeout | 39 |
| HTTP 404 | 29 |
| DNS inexistente | 17 |
| Certificado TLS inválido | 9 |
| HTTP 403, geo-block ou anti-leech | 7 |
| Outros erros 5xx | 10 |

Duas correções resolveram boa parte do que parecia canal morto: mandar o
User-Agent `VLC/3.0.20 LibVLC/3.0.20`, porque vários CDN rejeitam requisição sem
UA, e trocar a lista global pela lista do país, que é muito menor e tem taxa de
acerto bem maior.

---

## Estrutura

```
iniciar_iptv_app.py       launcher, trava de instância única e Chrome em modo app
iptvnator_companion.py    API local, painel e transmissão para a TV
channel_health.py         cache de saúde dos canais
frontend/                 painel React com Vite
tools/                    varredura, organização de listas e transmissão
├── probe_m3u.py          testa uma lista inteira com ffprobe
├── build_lists.py        monta as listas por país e categoria
├── cast_worker.py        transmissão DLNA e Chromecast
└── scan_worker.py        descoberta de aparelhos na rede
lists/                    listas M3U organizadas
docs/RELATORIO.md         resultado bruto dos testes com o iptv-org
tests/                    testes de ponta a ponta e de interface
archive/                  tentativas anteriores, incluindo versões Android
```

Os arquivos de cache (`channel_health.json`, `known_tvs.json`,
`dlna_devices.json`) não são versionados, porque guardam o endereço e o nome dos
aparelhos da rede de casa.

---

## Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| Porta 8769 ou 3000 ocupada | instância anterior travada | Apague `logs/iptv_app.lock` e `logs/companion.pid` |
| Todos os canais aparecem mortos | ffprobe não encontrado | Instale o ffmpeg e coloque no PATH |
| Canal toca no VLC mas não no painel | CDN rejeitando o User-Agent | Já tratado, confira se a requisição está saindo com o UA do VLC |
| TV não aparece na lista | descoberta bloqueada pelo firewall | Libere UDP 1900 (SSDP) para a rede privada |

---

## Apoie o projeto

Se este projeto te ajudou, considere fazer uma doação via PIX:

```
f74458dc-2a36-49bd-9250-1cef4365ebb8
```

---

## Licença

[MIT](LICENSE) - Carlos Eduardo
