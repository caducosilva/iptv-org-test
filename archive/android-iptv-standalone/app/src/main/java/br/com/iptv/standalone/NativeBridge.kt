package br.com.iptv.standalone

import android.webkit.JavascriptInterface
import br.com.iptv.standalone.data.IptvRepository
import br.com.iptv.standalone.player.NativePlayerController
import br.com.iptv.standalone.server.LocalApiServer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject

class NativeBridge(
    private val repo: IptvRepository,
    private val scope: CoroutineScope,
    private val player: () -> NativePlayerController?,
    private val openImportPicker: () -> Unit,
    private val evalJs: (String) -> Unit,
) {
    @JavascriptInterface
    fun getApiBase(): String = "http://127.0.0.1:${LocalApiServer.PORT}"

    @JavascriptInterface
    fun isStandalone(): Boolean = true

    @JavascriptInterface
    fun playNative(url: String, title: String) {
        scope.launch(Dispatchers.Main) {
            player()?.play(url, title)
        }
    }

    @JavascriptInterface
    fun stopNative() {
        scope.launch(Dispatchers.Main) {
            player()?.stop()
        }
    }

    @JavascriptInterface
    fun setNativeVolume(percent: Int) {
        scope.launch(Dispatchers.Main) {
            player()?.setVolume(percent)
        }
    }

    @JavascriptInterface
    fun setNativeMuted(muted: Boolean) {
        scope.launch(Dispatchers.Main) {
            player()?.setMuted(muted)
        }
    }

    @JavascriptInterface
    fun importM3u() {
        openImportPicker()
    }

    @JavascriptInterface
    fun playlistCount(): Int = repo.playlists.value.size

    @JavascriptInterface
    fun channelCount(): Int = repo.channels.value.size

    @JavascriptInterface
    fun notifyImported(json: String) {
        // reserved
    }

    fun emitEvent(name: String, payload: JSONObject = JSONObject()) {
        val script =
            "window.dispatchEvent(new CustomEvent(${JSONObject.quote(name)},{detail:${payload}}));"
        evalJs(script)
    }

    fun reloadCatalogOnJs() {
        evalJs(
            """
            window.__iptvReloadCatalog && window.__iptvReloadCatalog();
            window.dispatchEvent(new CustomEvent('iptv-catalog-changed'));
            """.trimIndent(),
        )
    }
}
