package br.com.iptvcast.app.backend

import android.webkit.JavascriptInterface
import br.com.iptvcast.app.data.AppPrefs
import br.com.iptvcast.app.data.CastRequest
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Bridge JS <-> Kotlin.
 * No front: window.IptvNative.getApiBase() / health() / channels(...) / cast(...)
 */
class NativeBridge(
    private val prefs: AppPrefs,
    private val repository: CompanionRepository,
    private val scope: CoroutineScope,
    private val evalJs: (String) -> Unit,
) {
    private val moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    @JavascriptInterface
    fun getApiBase(): String = repository.baseUrl()

    @JavascriptInterface
    fun setApiBase(url: String) {
        prefs.apiBaseUrl = url
    }

    @JavascriptInterface
    fun proxyMediaUrl(streamUrl: String): String = repository.proxyMediaUrl(streamUrl)

    @JavascriptInterface
    fun healthAsync(callbackId: String) {
        runAsync(callbackId) {
            toJson(repository.health())
        }
    }

    @JavascriptInterface
    fun devicesAsync(callbackId: String) {
        runAsync(callbackId) {
            toJson(repository.devices())
        }
    }

    @JavascriptInterface
    fun scanAsync(callbackId: String) {
        runAsync(callbackId) {
            toJson(repository.scan())
        }
    }

    @JavascriptInterface
    fun playlistsAsync(callbackId: String) {
        runAsync(callbackId) {
            toJson(repository.playlists())
        }
    }

    @JavascriptInterface
    fun channelsAsync(q: String?, playlist: String?, limit: Int, hideDead: Boolean, callbackId: String) {
        runAsync(callbackId) {
            toJson(
                repository.channels(
                    q = q,
                    playlist = playlist,
                    limit = limit,
                    hideDead = hideDead,
                )
            )
        }
    }

    @JavascriptInterface
    fun castAsync(url: String, title: String, host: String?, callbackId: String) {
        runAsync(callbackId) {
            toJson(
                repository.cast(
                    CastRequest(
                        url = url,
                        title = title,
                        host = host,
                        device = host,
                    )
                )
            )
        }
    }

    @JavascriptInterface
    fun castStatusAsync(callbackId: String) {
        runAsync(callbackId) {
            toJson(repository.castStatus())
        }
    }

    private fun <T> toJson(value: T): String {
        @Suppress("UNCHECKED_CAST")
        val adapter = moshi.adapter(value!!::class.java as Class<Any>)
        return adapter.toJson(value as Any)
    }

    private fun runAsync(callbackId: String, block: suspend () -> String) {
        scope.launch(Dispatchers.Main.immediate) {
            val result = try {
                val payload = withContext(Dispatchers.IO) { block() }
                JSONObject()
                    .put("ok", true)
                    .put("callbackId", callbackId)
                    .put("data", payload)
                    .toString()
            } catch (e: Exception) {
                JSONObject()
                    .put("ok", false)
                    .put("callbackId", callbackId)
                    .put("error", e.message ?: "erro")
                    .toString()
            }
            val safe = JSONObject.quote(result)
            evalJs("window.__iptvNativeCallback && window.__iptvNativeCallback($safe)")
        }
    }
}
