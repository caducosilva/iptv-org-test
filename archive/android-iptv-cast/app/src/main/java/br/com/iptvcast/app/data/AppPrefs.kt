package br.com.iptvcast.app.data

import android.content.Context
import br.com.iptvcast.app.BuildConfig

class AppPrefs(context: Context) {
    private val sp = context.getSharedPreferences("iptv_cast", Context.MODE_PRIVATE)

    var apiBaseUrl: String
        get() = sp.getString(KEY_API, BuildConfig.DEFAULT_API_BASE)?.trim().orEmpty()
            .ifBlank { BuildConfig.DEFAULT_API_BASE }
            .trimEnd('/')
        set(value) {
            sp.edit().putString(KEY_API, value.trim().trimEnd('/')).apply()
        }

    companion object {
        private const val KEY_API = "api_base_url"
    }
}
