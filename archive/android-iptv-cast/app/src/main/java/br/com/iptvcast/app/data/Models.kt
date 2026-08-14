package br.com.iptvcast.app.data

data class HealthResponse(
    val ok: Boolean = false,
    val ip: String? = null,
    val devices: Int? = null,
    val pending: Boolean? = null,
)

data class Device(
    val friendlyName: String? = null,
    val host: String? = null,
    val type: String? = null,
    val manufacturer: String? = null,
)

data class DevicesResponse(
    val devices: List<Device> = emptyList(),
)

data class Playlist(
    val name: String? = null,
    val file: String? = null,
    val count: Int? = null,
)

data class PlaylistsResponse(
    val playlists: List<Playlist> = emptyList(),
    val folder: String? = null,
    val version: Int? = null,
)

data class Channel(
    val name: String? = null,
    val url: String? = null,
    val playlist: String? = null,
    val group: String? = null,
    val health: String? = null,
    val signalStrength: Int? = null,
    val score: Int? = null,
    val confirmed: Boolean? = null,
)

data class ChannelsResponse(
    val channels: List<Channel> = emptyList(),
    val total: Int? = null,
)

data class CastRequest(
    val url: String,
    val title: String,
    val device: String? = null,
    val host: String? = null,
)

data class CastResponse(
    val ok: Boolean = false,
    val pending: Boolean? = null,
    val message: String? = null,
    val error: String? = null,
)

data class CastStatusResponse(
    val ok: Boolean? = null,
    val pending: Boolean? = null,
    val phase: String? = null,
    val message: String? = null,
    val error: String? = null,
    val device: String? = null,
    val title: String? = null,
    val player: String? = null,
)

data class PreviewResponse(
    val ok: Boolean = false,
    val playUrl: String? = null,
    val error: String? = null,
)
