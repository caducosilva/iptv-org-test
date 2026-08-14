package br.com.iptv.standalone.cast

import android.content.Context
import android.net.Uri
import com.google.android.gms.cast.MediaInfo
import com.google.android.gms.cast.MediaLoadRequestData
import com.google.android.gms.cast.MediaMetadata
import com.google.android.gms.cast.framework.CastContext
import com.google.android.gms.cast.framework.CastSession
import com.google.android.gms.common.images.WebImage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

class CastController(context: Context) {
    private val appContext = context.applicationContext

    private val _available = MutableStateFlow(false)
    val available: StateFlow<Boolean> = _available

    private val _casting = MutableStateFlow(false)
    val casting: StateFlow<Boolean> = _casting

    private val _deviceName = MutableStateFlow<String?>(null)
    val deviceName: StateFlow<String?> = _deviceName

    private val sessionListener = object : com.google.android.gms.cast.framework.SessionManagerListener<CastSession> {
        override fun onSessionStarting(session: CastSession) = Unit
        override fun onSessionStarted(session: CastSession, sessionId: String) {
            _casting.value = true
            _deviceName.value = session.castDevice?.friendlyName
            _available.value = true
        }

        override fun onSessionStartFailed(session: CastSession, error: Int) {
            _casting.value = false
        }

        override fun onSessionEnding(session: CastSession) = Unit
        override fun onSessionEnded(session: CastSession, error: Int) {
            _casting.value = false
            _deviceName.value = null
        }

        override fun onSessionResuming(session: CastSession, sessionId: String) = Unit
        override fun onSessionResumed(session: CastSession, wasSuspended: Boolean) {
            _casting.value = true
            _deviceName.value = session.castDevice?.friendlyName
        }

        override fun onSessionResumeFailed(session: CastSession, error: Int) {
            _casting.value = false
        }

        override fun onSessionSuspended(session: CastSession, reason: Int) = Unit
    }

    fun init() {
        runCatching {
            val castContext = CastContext.getSharedInstance(appContext)
            castContext.sessionManager.addSessionManagerListener(sessionListener, CastSession::class.java)
            refreshAvailability()
        }
    }

    fun refreshAvailability() {
        runCatching {
            val routes = CastContext.getSharedInstance(appContext)
            _available.value = true
            val session = routes.sessionManager.currentCastSession
            _casting.value = session?.isConnected == true
            _deviceName.value = session?.castDevice?.friendlyName
        }.onFailure {
            _available.value = false
        }
    }

    fun castUrl(url: String, title: String, logo: String? = null): Result<Unit> = runCatching {
        val session = CastContext.getSharedInstance(appContext).sessionManager.currentCastSession
            ?: error("Nenhuma TV conectada. Toque no icone Cast e escolha a TV.")
        val meta = MediaMetadata(MediaMetadata.MEDIA_TYPE_MOVIE).apply {
            putString(MediaMetadata.KEY_TITLE, title)
            if (!logo.isNullOrBlank()) {
                addImage(WebImage(Uri.parse(logo)))
            }
        }
        val isLive = url.contains(".m3u8", true) || url.contains(".m3u", true) ||
            url.contains("live", true) || url.contains("playlist", true)
        val contentType = when {
            url.contains(".m3u8", true) -> "application/x-mpegURL"
            url.contains(".mpd", true) -> "application/dash+xml"
            else -> "video/mp4"
        }
        val info = MediaInfo.Builder(url)
            .setStreamType(
                if (isLive) MediaInfo.STREAM_TYPE_LIVE else MediaInfo.STREAM_TYPE_BUFFERED,
            )
            .setContentType(contentType)
            .setMetadata(meta)
            .build()
        val req = MediaLoadRequestData.Builder()
            .setMediaInfo(info)
            .setAutoplay(true)
            .build()
        session.remoteMediaClient?.load(req)
            ?: error("TV conectada, mas sem controle de midia")
        _casting.value = true
        _deviceName.value = session.castDevice?.friendlyName
    }

    fun stop() {
        runCatching {
            CastContext.getSharedInstance(appContext).sessionManager.endCurrentSession(true)
        }
        _casting.value = false
    }
}
