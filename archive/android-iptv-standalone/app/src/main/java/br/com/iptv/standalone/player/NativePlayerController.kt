package br.com.iptv.standalone.player

import android.content.Context
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.hls.HlsMediaSource
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

@UnstableApi
class NativePlayerController(
    context: Context,
    private val playerView: PlayerView,
) {
    private val appContext = context.applicationContext
    private val okHttp = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    private val dataSourceFactory = OkHttpDataSource.Factory(okHttp)
        .setUserAgent("VLC/3.0.20 LibVLC/3.0.20")

    private var player: ExoPlayer? = null

    @Volatile
    var lastError: String? = null
        private set

    fun ensurePlayer(): ExoPlayer {
        player?.let { return it }
        val p = ExoPlayer.Builder(appContext)
            .setMediaSourceFactory(DefaultMediaSourceFactory(dataSourceFactory))
            .build()
        p.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                lastError = error.message ?: error.errorCodeName
            }
        })
        p.playWhenReady = true
        playerView.player = p
        player = p
        return p
    }

    fun play(url: String, title: String? = null) {
        lastError = null
        val p = ensurePlayer()
        playerView.visibility = android.view.View.VISIBLE
        playerView.bringToFront()
        playerView.elevation = 24f
        val mime = when {
            url.contains(".m3u8", true) -> MimeTypes.APPLICATION_M3U8
            url.contains(".mpd", true) -> MimeTypes.APPLICATION_MPD
            url.contains(".mp4", true) -> MimeTypes.VIDEO_MP4
            else -> null
        }
        val item = MediaItem.Builder()
            .setUri(url)
            .apply {
                if (mime != null) setMimeType(mime)
                if (!title.isNullOrBlank()) {
                    setMediaMetadata(
                        androidx.media3.common.MediaMetadata.Builder()
                            .setTitle(title)
                            .build(),
                    )
                }
            }
            .build()
        if (mime == MimeTypes.APPLICATION_M3U8) {
            val src = HlsMediaSource.Factory(dataSourceFactory).createMediaSource(item)
            p.setMediaSource(src)
        } else {
            p.setMediaItem(item)
        }
        p.prepare()
        p.play()
    }

    fun setVolume(percent: Int) {
        val v = (percent.coerceIn(0, 100) / 100f)
        player?.volume = v
    }

    fun setMuted(muted: Boolean) {
        player?.volume = if (muted) 0f else 1f
    }

    fun stop() {
        player?.stop()
        playerView.visibility = android.view.View.GONE
    }

    fun release() {
        playerView.player = null
        player?.release()
        player = null
    }
}
