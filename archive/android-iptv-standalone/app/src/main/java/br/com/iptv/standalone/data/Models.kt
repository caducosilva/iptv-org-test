package br.com.iptv.standalone.data

enum class ChannelHealth {
    UNKNOWN, OK, DOUBT, DEAD
}

data class Channel(
    val id: String,
    val name: String,
    val url: String,
    val group: String = "",
    val playlistId: String,
    val logo: String? = null,
    val health: ChannelHealth = ChannelHealth.UNKNOWN,
    val latencyMs: Long? = null,
)

data class Playlist(
    val id: String,
    val name: String,
    val sourceUri: String,
    val channelCount: Int = 0,
)

enum class ChannelFilter {
    ALL,
    HIDE_DEAD,
    DEAD_ONLY,
    FAVORITES,
    MOST_WATCHED,
}
