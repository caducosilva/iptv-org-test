package br.com.iptvcast.app

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import br.com.iptvcast.app.backend.NativeBridge
import br.com.iptvcast.app.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private val app get() = application as IptvApp

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val web = binding.webView
        web.setBackgroundColor(Color.parseColor("#020617"))
        web.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                injectApiBase(web)
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

        web.addJavascriptInterface(
            NativeBridge(
                prefs = app.prefs,
                repository = app.repository,
                scope = lifecycleScope,
                evalJs = { script -> web.post { web.evaluateJavascript(script, null) } },
            ),
            "IptvNative",
        )

        binding.fabSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }

        // Front entregue depois: colocar o build em app/src/main/assets/www/
        web.loadUrl("file:///android_asset/www/index.html")
    }

    override fun onResume() {
        super.onResume()
        if (::binding.isInitialized) {
            injectApiBase(binding.webView)
            binding.webView.evaluateJavascript(
                "window.__iptvOnApiBaseChanged && window.__iptvOnApiBaseChanged(${org.json.JSONObject.quote(app.prefs.apiBaseUrl)})",
                null,
            )
        }
    }

    private fun injectApiBase(web: WebView) {
        val base = org.json.JSONObject.quote(app.prefs.apiBaseUrl)
        web.evaluateJavascript(
            """
            window.IPTV_API_BASE = $base;
            window.IPTV_NATIVE = true;
            """.trimIndent(),
            null,
        )
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (binding.webView.canGoBack()) {
            binding.webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }
}
