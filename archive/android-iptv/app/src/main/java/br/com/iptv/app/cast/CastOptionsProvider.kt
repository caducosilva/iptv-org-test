package br.com.iptv.app.cast

import android.content.Context
import com.google.android.gms.cast.framework.CastOptions
import com.google.android.gms.cast.framework.OptionsProvider
import com.google.android.gms.cast.framework.SessionProvider
import com.google.android.gms.cast.framework.media.CastMediaOptions
import com.google.android.gms.cast.framework.media.NotificationOptions

class CastOptionsProvider : OptionsProvider {
    override fun getCastOptions(context: Context): CastOptions {
        val mediaOptions = CastMediaOptions.Builder()
            .setNotificationOptions(
                NotificationOptions.Builder()
                    .setTargetActivityClassName("br.com.iptv.app.MainActivity")
                    .build(),
            )
            .build()
        return CastOptions.Builder()
            .setReceiverApplicationId(DEFAULT_RECEIVER)
            .setCastMediaOptions(mediaOptions)
            .build()
    }

    override fun getAdditionalSessionProviders(context: Context): List<SessionProvider>? = null

    companion object {
        // receptor padrao do Google Cast (suporta HLS na maioria das TVs)
        const val DEFAULT_RECEIVER = "CC1AD845"
    }
}
