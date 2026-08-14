package br.com.iptv.standalone

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.util.UnstableApi
import br.com.iptv.standalone.databinding.ActivityMainBinding
import br.com.iptv.standalone.player.NativePlayerController
import br.com.iptv.standalone.server.LocalApiServer
import com.google.android.gms.cast.framework.CastButtonFactory
import com.google.android.gms.cast.framework.CastContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@OptIn(UnstableApi::class)
class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private val app get() = application as IptvApp
    private var nativePlayer: NativePlayerController? = null
    private var bridge: NativeBridge? = null

    private val importLauncher = registerForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri: Uri? ->
        if (uri == null) return@registerForActivityResult
        contentResolver.takePersistableUriPermission(
            uri,
            Intent.FLAG_GRANT_READ_URI_PERMISSION,
        )
        lifecycleScope.launch {
            runCatching {
                runCatching {
                    contentResolver.takePersistableUriPermission(
                        uri,
                        Intent.FLAG_GRANT_READ_URI_PERMISSION,
                    )
                }
                withContext(Dispatchers.IO) { app.repository.importM3uFromUri(uri) }
            }.onSuccess { pl ->
                app.apiServer?.bumpCatalog()
                Toast.makeText(this@MainActivity, "Importado: ${pl.name} (${pl.channelCount})", Toast.LENGTH_LONG).show()
                bridge?.reloadCatalogOnJs()
                binding.webView.evaluateJavascript(
                    "window.__iptvOnApiBaseChanged && window.__iptvOnApiBaseChanged('http://127.0.0.1:${LocalApiServer.PORT}')",
                    null,
                )
            }.onFailure {
                Toast.makeText(this@MainActivity, "Falha ao importar: ${it.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        runCatching { CastContext.getSharedInstance(this) }

        nativePlayer = NativePlayerController(this, binding.playerView)
        binding.playerView.visibility = View.GONE

        val mediaRoute = binding.mediaRouteButton
        CastButtonFactory.setUpMediaRouteButton(applicationContext, mediaRoute)

        val web = binding.webView
        web.setBackgroundColor(Color.parseColor("#020617"))
        web.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                injectShell(web)
            }
        }
        web.webChromeClient = WebChromeClient()

        val settings = web.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        settings.cacheMode = WebSettings.LOAD_DEFAULT
        settings.allowFileAccess = true
        settings.allowContentAccess = true

        bridge = NativeBridge(
            repo = app.repository,
            scope = lifecycleScope,
            player = { nativePlayer },
            openImportPicker = {
                importLauncher.launch(
                    arrayOf(
                        "audio/x-mpegurl",
                        "application/vnd.apple.mpegurl",
                        "application/x-mpegURL",
                        "text/plain",
                        "*/*",
                    ),
                )
            },
            evalJs = { script -> web.post { web.evaluateJavascript(script, null) } },
        )
        web.addJavascriptInterface(bridge!!, "IptvNative")

        binding.fabImport.setOnClickListener {
            importLauncher.launch(arrayOf("*/*"))
        }

        lifecycleScope.launch {
            // garante API local antes de carregar o front
            withContext(Dispatchers.IO) {
                app.startLocalApi()
                var tries = 0
                while (app.apiServer == null && tries < 20) {
                    delay(100)
                    app.startLocalApi()
                    tries++
                }
            }
            web.loadUrl("file:///android_asset/www/index.html")
        }
    }

    private fun injectShell(web: WebView) {
        val base = "http://127.0.0.1:${LocalApiServer.PORT}"
        web.evaluateJavascript(
            """
            window.IPTV_API_BASE = ${org.json.JSONObject.quote(base)};
            window.IPTV_NATIVE = true;
            window.IPTV_STANDALONE = true;
            if (window.__iptvOnApiBaseChanged) window.__iptvOnApiBaseChanged(${org.json.JSONObject.quote(base)});
            """.trimIndent(),
            null,
        )
    }

    override fun onResume() {
        super.onResume()
        if (::binding.isInitialized) injectShell(binding.webView)
        app.castController.refreshAvailability()
    }

    override fun onDestroy() {
        nativePlayer?.release()
        nativePlayer = null
        super.onDestroy()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (binding.playerView.visibility == View.VISIBLE) {
            nativePlayer?.stop()
            return
        }
        if (binding.webView.canGoBack()) {
            binding.webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }
}
