package br.com.iptv.standalone.server

import android.content.Context
import android.os.Handler
import android.os.Looper
import br.com.iptv.standalone.cast.CastController
import br.com.iptv.standalone.data.Channel
import br.com.iptv.standalone.data.ChannelFilter
import br.com.iptv.standalone.data.ChannelHealth
import br.com.iptv.standalone.data.ChannelProbe
import br.com.iptv.standalone.data.IptvRepository
import fi.iki.elonen.NanoHTTPD
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * API local no aparelho (127.0.0.1:8769), mesma forma do companion do PC.
 * O app Android nao depende do computador.
 */
class LocalApiServer(
    private val context: Context,
    private val repo: IptvRepository,
    private val cast: CastController,
    private val scope: CoroutineScope,
    port: Int = PORT,
) : NanoHTTPD(port) {

    private val http = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    private val catalogVersion = AtomicInteger(1)
    private val probeRunning = AtomicBoolean(false)
    private val probeDone = AtomicInteger(0)
    private val probeTotal = AtomicInteger(0)
    private val probeOk = AtomicInteger(0)
    private val probeDoubt = AtomicInteger(0)
    private val probeDead = AtomicInteger(0)
    private val mainHandler = Handler(Looper.getMainLooper())

    @Volatile
    private var castPending = false

    @Volatile
    private var lastCast: JSONObject = JSONObject()
        .put("phase", "idle")
        .put("ok", false)
        .put("message", "")
        .put("device", JSONObject.NULL)
        .put("url", JSONObject.NULL)
        .put("title", JSONObject.NULL)
        .put("updatedAt", JSONObject.NULL)

    private val castLogs = mutableListOf<String>()

    fun bumpCatalog() {
        catalogVersion.incrementAndGet()
    }

    override fun serve(session: IHTTPSession): Response {
        val uri = session.uri.substringBefore('?')
        val method = session.method
        return try {
            if (method == Method.OPTIONS) {
                return cors(newFixedLengthResponse(Response.Status.NO_CONTENT, MIME_PLAINTEXT, ""))
            }
            when {
                uri == "/health" && method == Method.GET -> json(healthJson())
                uri == "/devices" && method == Method.GET -> json(devicesJson())
                uri == "/scan" && method == Method.GET -> json(scanJson())
                uri == "/playlists" && method == Method.GET -> json(playlistsJson())
                uri == "/catalog" && method == Method.GET -> json(catalogJson(force = false))
                uri == "/catalog/reload" && method == Method.GET -> json(catalogJson(force = true))
                uri == "/channels" && method == Method.GET -> json(channelsJson(session))
                uri == "/preview" && method == Method.GET -> json(previewJson(session))
                uri == "/proxy_media" && method == Method.GET -> proxyMedia(session)
                uri == "/probe/status" && method == Method.GET -> json(probeStatusJson())
                uri == "/probe/batch" && method == Method.POST -> {
                    val body = readBody(session)
                    json(startProbeBatch(body))
                }
                uri == "/cast" && method == Method.POST -> {
                    val body = readBody(session)
                    json(doCast(body))
                }
                uri == "/cast_status" && method == Method.GET -> json(castStatusJson())
                uri == "/cast_log" && method == Method.GET -> json(
                    JSONObject()
                        .put("logs", JSONArray(castLogs.takeLast(80)))
                        .put("state", lastCast)
                        .put("pending", castPending),
                )
                uri == "/play" && method == Method.POST -> {
                    // no mobile, /play e so eco: o front/nativo ja toca no aparelho
                    val body = readBody(session)
                    val o = JSONObject(body.ifBlank { "{}" })
                    json(
                        JSONObject()
                            .put("ok", true)
                            .put("player", "android")
                            .put("message", "use player nativo / video do app")
                            .put("url", o.optString("url")),
                    )
                }
                uri == "/import_text" && method == Method.POST -> {
                    val body = readBody(session)
                    json(importText(body))
                }
                else -> json(
                    JSONObject().put("error", "not found").put("path", uri),
                    Response.Status.NOT_FOUND,
                )
            }
        } catch (e: Exception) {
            json(
                JSONObject().put("ok", false).put("error", e.message ?: "erro"),
                Response.Status.INTERNAL_ERROR,
            )
        }
    }

    private fun healthJson(): JSONObject {
        cast.refreshAvailability()
        return JSONObject()
            .put("ok", true)
            .put("ip", "127.0.0.1")
            .put("devices", if (cast.available.value) 1 else 0)
            .put("cast", lastCast)
            .put("pending", castPending)
            .put("standalone", true)
            .put("mode", "android-local")
    }

    private fun devicesJson(): JSONObject {
        cast.refreshAvailability()
        val devices = JSONArray()
        val name = cast.deviceName.value
        if (!name.isNullOrBlank() || cast.available.value) {
            devices.put(
                JSONObject()
                    .put("friendlyName", name ?: "Chromecast / TV")
                    .put("host", "cast-local")
                    .put("type", "chromecast")
                    .put("manufacturer", "Google Cast"),
            )
        }
        return JSONObject()
            .put("devices", devices)
            .put("last_cast", lastCast)
            .put("cast", lastCast)
            .put("pending", castPending)
    }

    private fun scanJson(): JSONObject {
        cast.refreshAvailability()
        val devices = devicesJson().getJSONArray("devices")
        logCast("scan", "scan local Cast: ${devices.length()} dispositivo(s)")
        return JSONObject().put("count", devices.length()).put("devices", devices)
    }

    private fun playlistsJson(): JSONObject {
        val items = JSONArray()
        repo.playlists.value.forEach { pl ->
            items.put(
                JSONObject()
                    .put("name", pl.name)
                    .put("file", "${pl.id}.m3u")
                    .put("count", pl.channelCount)
                    .put("mtime", System.currentTimeMillis() / 1000),
            )
        }
        return JSONObject()
            .put("playlists", items)
            .put("version", catalogVersion.get())
            .put("folder", "android-local")
    }

    private fun catalogJson(force: Boolean): JSONObject {
        if (force) {
            repo.reloadAllFromDisk()
            catalogVersion.incrementAndGet()
        }
        return JSONObject()
            .put("changed", force)
            .put("version", catalogVersion.get())
            .put("folder", "android-local")
            .put("playlists", repo.playlists.value.size)
            .put("channels", repo.channels.value.size)
    }

    private fun channelsJson(session: IHTTPSession): JSONObject {
        val q = session.parms["q"].orEmpty()
        val playlist = session.parms["playlist"].orEmpty()
        val hideDead = session.parms["hide_dead"].orEmpty().lowercase() in setOf("1", "true", "yes")
        val limit = session.parms["limit"]?.toIntOrNull() ?: 5000

        val playlistId = if (playlist.isBlank() || playlist == "TODAS") {
            null
        } else {
            repo.playlists.value.find { it.name.equals(playlist, true) || it.id == playlist }?.id
        }
        val filter = if (hideDead) ChannelFilter.HIDE_DEAD else ChannelFilter.ALL
        val hits = repo.filteredChannels(playlistId, filter, q).take(limit)

        val arr = JSONArray()
        hits.forEach { ch -> arr.put(channelToJson(ch)) }

        return JSONObject()
            .put("query", q)
            .put("playlist", playlist)
            .put("count", arr.length())
            .put("channels", arr)
            .put("version", catalogVersion.get())
            .put("folder", "android-local")
            .put("hide_dead", hideDead)
            .put("health", JSONObject().put("counts", healthCountsJson()))
    }

    private fun channelToJson(ch: Channel): JSONObject {
        val health = when (ch.health) {
            ChannelHealth.OK -> "ok"
            ChannelHealth.DOUBT -> "doubt"
            ChannelHealth.DEAD -> "dead"
            ChannelHealth.UNKNOWN -> "unknown"
        }
        val signal = when (ch.health) {
            ChannelHealth.OK -> 90
            ChannelHealth.DOUBT -> 45
            ChannelHealth.DEAD -> 0
            ChannelHealth.UNKNOWN -> 20
        }
        val plName = repo.playlists.value.find { it.id == ch.playlistId }?.name ?: ch.playlistId
        return JSONObject()
            .put("name", ch.name)
            .put("url", ch.url)
            .put("playlist", plName)
            .put("group", ch.group)
            .put("score", signal)
            .put("signalStrength", signal)
            .put("health", health)
            .put("confirmed", ch.health == ChannelHealth.OK)
            .put("codecs", JSONArray(listOf("H.264", "AAC")))
    }

    private fun healthCountsJson(): JSONObject {
        val all = repo.channels.value
        return JSONObject()
            .put("ok", all.count { it.health == ChannelHealth.OK })
            .put("doubt", all.count { it.health == ChannelHealth.DOUBT })
            .put("dead", all.count { it.health == ChannelHealth.DEAD })
            .put("confirmed", all.count { it.health == ChannelHealth.OK })
            .put("unknown", all.count { it.health == ChannelHealth.UNKNOWN })
    }

    private fun previewJson(session: IHTTPSession): JSONObject {
        val url = session.parms["url"].orEmpty().trim()
        val name = session.parms["name"].orEmpty()
        if (url.isBlank()) {
            return JSONObject().put("ok", false).put("error", "url vazia").put("fail_class", "hard")
        }
        val (health, latency) = runBlocking { ChannelProbe.probe(url) }
        val ok = health == ChannelHealth.OK || health == ChannelHealth.DOUBT
        val playUrl = "http://127.0.0.1:$PORT/proxy_media?url=" +
            java.net.URLEncoder.encode(url, Charsets.UTF_8.name())
        val status = when (health) {
            ChannelHealth.OK -> "ok"
            ChannelHealth.DOUBT -> "doubt"
            ChannelHealth.DEAD -> "dead"
            ChannelHealth.UNKNOWN -> "unknown"
        }
        // atualiza cache local
        scope.launch(Dispatchers.IO) {
            runCatching {
                val map = repo.channels.value.associate { it.id to it.health }.toMutableMap()
                val hit = repo.channels.value.find { it.url == url }
                if (hit != null) {
                    // reaproveita probeVisible parcial via mark no repo: forca reload health
                    repo.probeVisible(listOf(hit.copy(health = health)), limit = 1)
                }
            }
        }
        return JSONObject()
            .put("ok", ok)
            .put("url", url)
            .put("playUrl", playUrl)
            .put("contentType", if (url.contains(".m3u8", true)) "application/vnd.apple.mpegurl" else "video/*")
            .put("hls", url.contains(".m3u8", true) || url.contains(".m3u", true))
            .put("fail_class", if (ok) "ok" else "hard")
            .put("latency_ms", latency ?: JSONObject.NULL)
            .put("health", status)
            .put(
                "health_entry",
                JSONObject().put("status", status).put("fail_count", if (ok) 0 else 1),
            )
            .put("name", name)
            .apply {
                if (!ok) put("error", "canal OFFLINE ou sem resposta")
            }
    }

    private fun proxyMedia(session: IHTTPSession): Response {
        val url = session.parms["url"].orEmpty().trim()
        if (url.isBlank()) {
            return json(JSONObject().put("error", "url vazia"), Response.Status.BAD_REQUEST)
        }
        return try {
            val req = Request.Builder()
                .url(url)
                .header("User-Agent", "VLC/3.0.20 LibVLC/3.0.20")
                .header("Accept", "*/*")
                .get()
                .build()
            http.newCall(req).execute().use { resp ->
                val bytes = resp.body?.bytes() ?: ByteArray(0)
                var ctype = resp.header("Content-Type") ?: "application/octet-stream"
                val textHead = bytes.take(64).toByteArray().toString(Charsets.UTF_8)
                val looksM3u = textHead.contains("#EXTM3U") ||
                    ctype.contains("mpegurl", true) ||
                    url.lowercase().endsWith(".m3u8") ||
                    url.lowercase().endsWith(".m3u")
                val outBytes: ByteArray
                if (looksM3u) {
                    val rewritten = rewriteM3u(bytes.toString(Charsets.UTF_8), url)
                    outBytes = rewritten.toByteArray(Charsets.UTF_8)
                    ctype = "application/vnd.apple.mpegurl; charset=utf-8"
                } else {
                    outBytes = bytes
                }
                val r = newFixedLengthResponse(
                    Response.Status.lookup(resp.code) ?: Response.Status.OK,
                    ctype,
                    outBytes.inputStream(),
                    outBytes.size.toLong(),
                )
                cors(r)
            }
        } catch (e: Exception) {
            json(
                JSONObject().put("error", "proxy falhou: ${e.message}").put("url", url),
                Response.Status.INTERNAL_ERROR,
            )
        }
    }

    private fun rewriteM3u(text: String, baseUrl: String): String {
        val base = baseUrl.substringBeforeLast('/') + "/"
        return text.lineSequence().joinToString("\n") { line ->
            val t = line.trim()
            if (t.isEmpty() || t.startsWith("#")) {
                line
            } else {
                val abs = when {
                    t.startsWith("http://", true) || t.startsWith("https://", true) -> t
                    t.startsWith("//") -> "http:$t"
                    else -> base + t.trimStart('/')
                }
                "http://127.0.0.1:$PORT/proxy_media?url=" +
                    java.net.URLEncoder.encode(abs, Charsets.UTF_8.name())
            }
        }
    }

    private fun probeStatusJson(): JSONObject {
        return JSONObject()
            .put("stats", JSONObject().put("counts", healthCountsJson()))
            .put(
                "probe",
                JSONObject()
                    .put("running", probeRunning.get())
                    .put("paused", false)
                    .put("done", probeDone.get())
                    .put("total", probeTotal.get())
                    .put("ok", probeOk.get())
                    .put("doubt", probeDoubt.get())
                    .put("dead", probeDead.get())
                    .put("errors", 0)
                    .put("last_url", "")
                    .put("last_message", if (probeRunning.get()) "probe em andamento" else "idle")
                    .put("started_at", ""),
            )
    }

    private fun startProbeBatch(body: String): JSONObject {
        val o = JSONObject(body.ifBlank { "{}" })
        val arr = o.optJSONArray("channels") ?: JSONArray()
        val urls = mutableListOf<Channel>()
        for (i in 0 until arr.length()) {
            val item = arr.getJSONObject(i)
            val url = item.optString("url")
            val name = item.optString("name")
            val ch = repo.channels.value.find { it.url == url }
                ?: Channel(
                    id = "tmp-$i",
                    name = name.ifBlank { url },
                    url = url,
                    playlistId = "tmp",
                )
            urls += ch
        }
        if (probeRunning.getAndSet(true)) {
            return JSONObject().put("ok", true).put("started", false).put("queued", 0)
        }
        probeDone.set(0)
        probeTotal.set(urls.size)
        probeOk.set(0)
        probeDoubt.set(0)
        probeDead.set(0)
        scope.launch(Dispatchers.IO) {
            try {
                val results = ChannelProbe.probeBatch(urls, limit = urls.size.coerceAtMost(120))
                results.values.forEach { (h, _) ->
                    when (h) {
                        ChannelHealth.OK -> probeOk.incrementAndGet()
                        ChannelHealth.DOUBT -> probeDoubt.incrementAndGet()
                        ChannelHealth.DEAD -> probeDead.incrementAndGet()
                        ChannelHealth.UNKNOWN -> Unit
                    }
                    probeDone.incrementAndGet()
                }
                repo.probeVisible(urls, limit = urls.size.coerceAtMost(120))
                catalogVersion.incrementAndGet()
            } finally {
                probeRunning.set(false)
            }
        }
        return JSONObject().put("ok", true).put("started", true).put("queued", urls.size)
    }

    private fun doCast(body: String): JSONObject {
        val o = JSONObject(body.ifBlank { "{}" })
        val url = o.optString("url")
        val title = o.optString("title").ifBlank { o.optString("channelName") }.ifBlank { "IPTV" }
        if (url.isBlank()) {
            return JSONObject().put("ok", false).put("error", "url vazia")
        }
        castPending = true
        lastCast = JSONObject()
            .put("phase", "started")
            .put("ok", false)
            .put("message", "enviando para TV...")
            .put("device", cast.deviceName.value)
            .put("url", url)
            .put("title", title)
            .put("updatedAt", System.currentTimeMillis().toString())
        logCast("started", "cast $title -> ${cast.deviceName.value}")

        var result: JSONObject? = null
        val latch = java.util.concurrent.CountDownLatch(1)
        mainHandler.post {
            val r = cast.castUrl(url, title)
            result = if (r.isSuccess) {
                JSONObject()
                    .put("ok", true)
                    .put("started", true)
                    .put("pending", false)
                    .put("device", cast.deviceName.value)
                    .put("url", url)
                    .put("title", title)
                    .put("message", "Cast iniciado na TV")
            } else {
                JSONObject()
                    .put("ok", false)
                    .put("started", false)
                    .put("pending", false)
                    .put("error", r.exceptionOrNull()?.message ?: "falha no cast")
                    .put("message", "Conecte uma TV pelo botao Cast do app (mesma Wi-Fi)")
            }
            castPending = false
            lastCast = JSONObject()
                .put("phase", if (result!!.optBoolean("ok")) "success" else "error")
                .put("ok", result!!.optBoolean("ok"))
                .put("message", result!!.optString("message").ifBlank { result!!.optString("error") })
                .put("device", cast.deviceName.value)
                .put("url", url)
                .put("title", title)
                .put("updatedAt", System.currentTimeMillis().toString())
            logCast(lastCast.getString("phase"), lastCast.getString("message"))
            latch.countDown()
        }
        latch.await(8, TimeUnit.SECONDS)
        return result ?: JSONObject().put("ok", false).put("error", "timeout cast")
    }

    private fun castStatusJson(): JSONObject {
        return JSONObject()
            .put("pending", castPending)
            .put("ok", lastCast.optBoolean("ok"))
            .put("phase", lastCast.optString("phase", "idle"))
            .put("message", lastCast.optString("message"))
            .put("error", if (lastCast.optBoolean("ok")) JSONObject.NULL else lastCast.optString("message"))
            .put("device", lastCast.opt("device"))
            .put("host", "cast-local")
            .put("url", lastCast.opt("url"))
            .put("source_url", lastCast.opt("url"))
            .put("title", lastCast.opt("title"))
            .put("player", if (cast.casting.value) "PLAYING" else "IDLE")
            .put("logs", JSONArray(castLogs.takeLast(20)))
    }

    private fun importText(body: String): JSONObject {
        val o = JSONObject(body.ifBlank { "{}" })
        val text = o.optString("text")
        val name = o.optString("name", "lista-importada")
        if (text.isBlank()) {
            return JSONObject().put("ok", false).put("error", "texto vazio")
        }
        val pl = runBlocking { repo.importM3uFromText(text, name) }
        catalogVersion.incrementAndGet()
        return JSONObject()
            .put("ok", true)
            .put("playlist", pl.name)
            .put("count", pl.channelCount)
            .put("id", pl.id)
    }

    private fun logCast(phase: String, message: String) {
        synchronized(castLogs) {
            castLogs += "${System.currentTimeMillis()}|$phase|$message"
            if (castLogs.size > 200) castLogs.removeAt(0)
        }
    }

    private fun readBody(session: IHTTPSession): String {
        val map = HashMap<String, String>()
        return try {
            session.parseBody(map)
            map["postData"] ?: map["content"] ?: ""
        } catch (_: Exception) {
            ""
        }
    }

    private fun json(obj: JSONObject, status: Response.Status = Response.Status.OK): Response {
        val body = obj.toString()
        val r = newFixedLengthResponse(status, "application/json; charset=utf-8", body)
        return cors(r)
    }

    private fun cors(r: Response): Response {
        r.addHeader("Access-Control-Allow-Origin", "*")
        r.addHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        r.addHeader("Access-Control-Allow-Headers", "Content-Type, Authorization")
        r.addHeader("Access-Control-Max-Age", "86400")
        r.addHeader("Cache-Control", "no-store")
        return r
    }

    companion object {
        const val PORT = 8769
    }
}
