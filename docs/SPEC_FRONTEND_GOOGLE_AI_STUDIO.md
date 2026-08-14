# SPEC - Frontend IPTV Cast Companion
Cole este arquivo inteiro no Google AI Studio.

---

## O que voce deve gerar

Um frontend web **desktop** em **um unico arquivo** `index.html` (HTML + CSS + JS), pronto para abrir no Chrome e controlar a API local.

Nao invente endpoints. Nao use emoji. UI em portugues do Brasil.

---

## Produto

Painel local para:
- listar canais de playlists `.m3u` / `.m3u8`
- ver se o canal responde (preview)
- espelhar o stream na TV Philips via Chromecast
- marcar saude do canal (ok / duvida / morto / confirmado)
- esconder mortos sem apagar nada
- atualizar sozinho quando a pasta de listas muda

Backend ja existe:
`http://127.0.0.1:8769`

---

## Layout (obrigatorio)

Tela unica, 3 colunas em desktop (>=1280px):

```
+------------------+---------------------------+--------------------+
| HEADER status    | HEADER status             | HEADER status      |
+------------------+---------------------------+--------------------+|
| FILTROS          | LISTA DE CANAIS           | PREVIEW + CAST     |
| - pasta M3U      | busca                     | canal selecionado  |
| - playlist       | checkbox esconder mortos  | status preview     |
| - saude counts   | contador                  | select TV          |
| - testar visiveis| lista scroll              | botao Espelhar     |
| - rescan TV      | badges [OK] [? ] [X]      | atalho Globo RJ    |
| - reload catalogo|                           | LOG ao vivo        |
+------------------+---------------------------+--------------------+
```

Mobile: empilhar na ordem filtros -> lista -> cast. Prioridade e desktop.

### Design
- Visual de painel tecnico de TV (controle, nao landing page)
- Fundo escuro suave (#0F1115 / #171A21), texto claro, acento verde limao para acao primaria (#A8FF3E)
- Acento laranja para estado "testando / espelhando"
- Vermelho so para erro/morto
- Tipografia: Inter ou system-ui (aqui pode system)
- Sem cards excessivos, sem glow roxo, sem glassmorphism
- Densidade media-alta, espacamento consistente 12/16px
- Lista de canais com hover e item selecionado bem visivel
- Status bar no topo sempre visivel

---

## Componentes e comportamento

### Header
- bolinha verde/vermelha: API online/offline
- texto: `API 127.0.0.1:8769 | IP {ip} | pasta {folder} | cat v{version}`
- contadores: `OK n | ? n | X n | OK* n`
- se probe rodando: `testando a/b`

Poll:
- `/health` a cada 5s
- `/catalog` a cada 2s (se version mudar, recarregar playlists + canais)
- `/probe/status` a cada 4s

### Filtros (coluna esquerda)
1. Select Playlist (`/playlists`) com opcao `TODAS`
2. Botao `Recarregar listas` -> `/catalog/reload`
3. Botao `Re-scan TVs` -> `/scan`
4. Botao `Testar visiveis` -> `/probe/batch` com ate 80 canais da lista atual
5. Resumo de saude (counts)

### Lista de canais (centro)
- Input busca (debounce 300ms)
- Checkbox `Esconder mortos`
- Contador `canais: N`
- Lista virtualmente simples (ul/div scroll), cada linha:
  - badge
  - nome
  - playlist (menor, opaco)
- Clique = seleciona + chama preview

Badges:
| health     | badge  | significado              |
|------------|--------|--------------------------|
| confirmed  | [OK*]  | cast ja funcionou        |
| ok         | [OK]   | preview/probe ok         |
| doubt      | [?]    | instavel / timeout       |
| dead       | [X]    | morto confirmado         |
| unknown    | [ ]    | ainda nao testado        |

Cores badge:
- OK/OK*: verde
- ?: amarelo
- X: vermelho
- vazio: cinza

### Preview + Cast (direita)
Ao selecionar canal:
1. mostrar nome + playlist
2. GET `/preview?url=&name=`
3. estados:
   - `Testando sinal...`
   - `Preview OK` (verde)
   - `Offline: {erro}` (vermelho) + aviso: ainda da para tentar cast

Select TV:
- carregar de `/devices` no boot
- atualizar com `/scan`
- label: `{friendlyName} @ {host}`
- guardar `host` para o cast

Botao principal:
- sem canal/TV: desabilitado
- preview ok: `Espelhar: {nome}` (verde)
- preview falhou: `Tentar mesmo assim: {nome}` (laranja)
- pending: `Espelhando... Ns` (desabilitado)

Atalho:
- botao `Globo RJ` seleciona canal fixo conhecido bom:
  - name: `TV Globo Rio de Janeiro (720p)`
  - url: `http://45.190.28.50/GLOBO_HD/index.m3u8`

### Log
Caixa monoespaçada, max ~200 linhas, auto-scroll.
Formato: `[HH:MM:SS] fase: mensagem`

---

## Fluxo de cast (implementar exatamente)

```js
POST /cast
body = {
  url,
  title: name,
  channelName: name,
  deviceName: host.toLowerCase(), // preferir IP
  host,
  deviceLabel: `${friendlyName} @ ${host}`
}

// depois:
poll GET /cast_status a cada 1s
enquanto pending === true -> atualizar "Espelhando... Xs"
quando pending === false:
  se ok -> sucesso no status + log
  senao -> erro no status + log
```

Nunca liberar o botao antes do fim do pending.

---

## Contrato da API (use so isto)

Base: `http://127.0.0.1:8769`

### GET /health
```json
{
  "ok": true,
  "ip": "192.168.0.25",
  "devices": 1,
  "cast": { "phase": "idle", "ok": null, "message": "aguardando" },
  "pending": false
}
```

### GET /playlists
```json
{
  "playlists": [{ "name": "lista", "file": "lista.m3u", "count": 100 }],
  "version": 1,
  "folder": "D:\\IPTV"
}
```

### GET /catalog
```json
{ "changed": false, "version": 1, "folder": "D:\\IPTV", "playlists": 7, "channels": 17811 }
```

### GET /catalog/reload
Mesmo formato de `/catalog` (forca releitura).

### GET /channels?q=&playlist=&limit=25000&hide_dead=0|1
```json
{
  "count": 10,
  "channels": [{
    "name": "Canal",
    "url": "http://...",
    "playlist": "lista",
    "group": "",
    "health": "ok",
    "health_fail": 0,
    "health_error": "",
    "confirmed": false
  }],
  "version": 1,
  "folder": "D:\\IPTV",
  "hide_dead": false,
  "health": { "counts": { "ok": 0, "doubt": 0, "dead": 0, "confirmed": 0, "unknown": 0 } }
}
```

### GET /preview?url=...&name=...
```json
{ "ok": true, "url": "...", "bytes": 183, "hls": true, "health": "ok", "error": null }
```
Offline: `{ "ok": false, "error": "canal OFFLINE (...)", "health": "dead" }`

### GET /devices
```json
{ "devices": [{ "friendlyName": "50PUG7907/78", "host": "192.168.0.27", "type": "chromecast" }] }
```

### GET /scan
Demora ~10s. `{ "count": 1, "devices": [ ... ] }`

### POST /cast
Body acima. Resposta: `{ "ok": true, "started": true, "pending": true }`

### GET /cast_status
```json
{
  "pending": false,
  "ok": true,
  "phase": "success",
  "message": "SUCCESS player=PLAYING ...",
  "player": "PLAYING",
  "device": "...",
  "url": "..."
}
```

### GET /probe/status
```json
{
  "stats": { "counts": { "ok": 0, "doubt": 0, "dead": 0, "confirmed": 0, "unknown": 0 } },
  "probe": { "running": false, "done": 0, "total": 0, "last_message": "" }
}
```

### POST /probe/batch
```json
{ "channels": [{ "url": "...", "name": "..." }], "workers": 6 }
```
Resposta: `{ "ok": true, "started": true, "queued": 40 }`
Se ocupado: HTTP 409.

### GET /cast_log
Opcional para hidratar log.

### GET /health_channels
Opcional (stats).

### GET /lookup?name=
Opcional.

---

## Regras que o front NAO pode quebrar

1. Nao apagar canais; so filtrar mortos na UI/API.
2. Permitir cast mesmo com preview falho.
3. Preferir IP da TV em `deviceName`.
4. Debounce na busca.
5. Tratar timeout/erro de rede com mensagem clara.
6. Se API cair, header fica vermelho e acoes mostram erro.
7. Textos em pt-BR, sem emoji.
8. Nao criar backend falso / mock obrigatorio (pode ter dados vazios se API offline).

---

## Criterios de aceite

- Abre `index.html` e fala com `127.0.0.1:8769`
- Lista playlists e canais
- Busca funciona
- Esconder mortos funciona
- Preview ao clicar
- Scan + select de TV
- Cast com polling ate sucesso/erro
- Log ao vivo
- Badges e contadores de saude
- Atualiza quando `version` do catalogo muda
- Atalho Globo RJ

---

## Entrega esperada do modelo

1. Arquivo unico `index.html` completo e funcional
2. CSS embutido
3. JS embutido com funcoes claras (`apiGet`, `apiPost`, `loadChannels`, `previewChannel`, `castNow`, `pollCast`, `scanDevices`)
4. Comentarios curtos em pt-BR onde ajudar
5. Sem dependencias externas obrigatórias (CDN de fonte ok; framework nao precisa)

Comece gerando o `index.html` agora.
