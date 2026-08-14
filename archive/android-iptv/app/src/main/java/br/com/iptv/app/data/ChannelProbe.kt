package br.com.iptv.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

object ChannelProbe {
    private val client = OkHttpClient.Builder()
        .connectTimeout(4, TimeUnit.SECONDS)
        .readTimeout(6, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    suspend fun probe(url: String): Pair<ChannelHealth, Long?> = withContext(Dispatchers.IO) {
        val started = System.currentTimeMillis()
        try {
            val req = Request.Builder()
                .url(url)
                .header("User-Agent", "IPTV-Android/1.0")
                .get()
                .build()
            client.newCall(req).execute().use { resp ->
                val ms = System.currentTimeMillis() - started
                val code = resp.code
                val bodyOk = (resp.body?.contentLength() ?: 1) != 0L
                val health = when {
                    code in 200..299 && bodyOk && ms < 3500 -> ChannelHealth.OK
                    code in 200..299 -> ChannelHealth.DOUBT
                    code in 400..499 -> ChannelHealth.DEAD
                    else -> ChannelHealth.DOUBT
                }
                health to ms
            }
        } catch (_: Exception) {
            ChannelHealth.DEAD to null
        }
    }

    suspend fun probeBatch(
        channels: List<Channel>,
        limit: Int = 40,
        parallelism: Int = 6,
    ): Map<String, Pair<ChannelHealth, Long?>> = coroutineScope {
        channels.take(limit).chunked(parallelism).flatMap { chunk ->
            chunk.map { ch ->
                async {
                    val result = probe(ch.url)
                    ch.id to result
                }
            }.awaitAll()
        }.toMap()
    }
}
