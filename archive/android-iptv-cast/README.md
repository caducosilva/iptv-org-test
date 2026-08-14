## IPTV Cast Android

Backend Android (Kotlin) + WebView para o front.

### Celulares alvo
- Samsung S25 Ultra
- Redmi Note 12 Pro
- minSdk 26 / targetSdk 35

### O que ja existe
- Cliente HTTP do companion (`CompanionRepository`)
- Bridge JS `window.IptvNative`
- Injecao `window.IPTV_API_BASE`
- Tela de configuracao do IP do PC
- Placeholder em `app/src/main/assets/www/`

### Entregar o front
1. Build do front web (dist)
2. Copiar arquivos para `app/src/main/assets/www/` (substituir o placeholder)
3. No JS do front, use `window.IPTV_API_BASE` em vez de `http://127.0.0.1:8769`
4. Rodar `build-apk.bat`

### Build
```bat
build-apk.bat
```

APK debug sai em:
`app\build\outputs\apk\debug\app-debug.apk`
