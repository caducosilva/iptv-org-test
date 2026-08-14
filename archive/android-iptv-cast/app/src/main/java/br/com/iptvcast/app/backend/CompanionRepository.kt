package br.com.iptvcast.app.backend

import br.com.iptvcast.app.data.AppPrefs
import br.com.iptvcast.app.data.CastRequest
import br.com.iptvcast.app.data.CastResponse
import br.com.iptvcast.app.data.CastStatusResponse
import br.com.iptvcast.app.data.ChannelsResponse
import br.com.iptvcast.app.data.DevicesResponse
import br.com.iptvcast.app.data.HealthResponse
import br.com.iptvcast.app.data.PlaylistsResponse
import br.com.iptvcast.app.data.PreviewResponse
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * Backend Android: cliente HTTP do IPTV Cast Companion (PC na LAN).
 * O front (WebView) consome estes metodos via bridge JS ou chama a API direto.
 */
class CompanionRepository(private val prefs: AppPrefs) {
    private val moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    private val client = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    fun baseUrl(): String = prefs.apiBaseUrl

    fun proxyMediaUrl(streamUrl: String): String {
        val encoded = java.net.URLEncoder.encode(streamUrl, Charsets.UTF_8.name())
        return "${baseUrl()}/proxy_media?url=$encoded"
    }

    suspend fun health(): HealthResponse = get("/health", HealthResponse::class.java)

    suspend fun devices(): DevicesResponse = get("/devices", DevicesResponse::class.java)

    suspend fun scan(): DevicesResponse = get("/scan", DevicesResponse::class.java, readSeconds = 45)

    suspend fun playlists(): PlaylistsResponse = get("/playlists", PlaylistsResponse::class.java, readSeconds = 120)

    suspend fun channels(
        q: String? = null,
        playlist: String? = null,
        limit: Int = 200,
        hideDead: Boolean = false,
    ): ChannelsResponse {
        val qs = buildString {
            append("limit=").append(limit)
            if (!q.isNullOrBlank()) append("&q=").append(enc(q))
            if (!playlist.isNullOrBlank() && playlist != "TODAS") {
                append("&playlist=").append(enc(playlist))
            }
            if (hideDead) append("&hide_dead=1")
        }
        return get("/channels?$qs", ChannelsResponse::class.java, readSeconds = 120)
    }

    suspend fun preview(url: String, name: String): PreviewResponse {
        val qs = "url=${enc(url)}&name=${enc(name)}"
        return get("/preview?$qs", PreviewResponse::class.java, readSeconds = 20)
    }

    suspend fun cast(body: CastRequest): CastResponse =
        post("/cast", body, CastResponse::class.java, readSeconds = 30)

    suspend fun castStatus(): CastStatusResponse =
        get("/cast_status", CastStatusResponse::class.java, readSeconds = 12)

    private fun enc(value: String): String =
        java.net.URLEncoder.encode(value, Charsets.UTF_8.name())

    private fun clientFor(readSeconds: Long): OkHttpClient {
        if (readSeconds == 60L) return client
        return client.newBuilder().readTimeout(readSeconds, TimeUnit.SECONDS).build()
    }

    private suspend fun <T> get(
        path: String,
        clazz: Class<T>,
        readSeconds: Long = 60,
    ): T = withContext(Dispatchers.IO) {
        val req = Request.Builder()
            .url(baseUrl() + path)
            .get()
            .header("Accept", "application/json")
            .build()
        clientFor(readSeconds).newCall(req).execute().use { resp ->
            val raw = resp.body?.string().orEmpty()
            if (!resp.isSuccessful && resp.code != 409) {
                throw IllegalStateException("HTTP ${resp.code}: ${raw.take(240)}")
            }
            moshi.adapter(clazz).fromJson(raw)
                ?: throw IllegalStateException("JSON vazio em $path")
        }
    }

    private suspend fun <T> post(
        path: String,
        body: Any,
        clazz: Class<T>,
        readSeconds: Long = 60,
    ): T = withContext(Dispatchers.IO) {
        val json = moshi.adapter(body.javaClass).toJson(body)
        val req = Request.Builder()
            .url(baseUrl() + path)
            .post(json.toRequestBody("application/json; charset=utf-8".toMediaType()))
            .header("Accept", "application/json")
            .build()
        clientFor(readSeconds).newCall(req).execute().use { resp ->
            val raw = resp.body?.string().orEmpty()
            if (!resp.isSuccessful && resp.code != 409) {
                throw IllegalStateException("HTTP ${resp.code}: ${raw.take(240)}")
            }
            moshi.adapter(clazz).fromJson(raw)
                ?: throw IllegalStateException("JSON vazio em $path")
        }
    }
}
