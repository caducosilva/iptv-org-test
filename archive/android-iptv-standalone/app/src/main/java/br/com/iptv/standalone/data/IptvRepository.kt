package br.com.iptv.standalone.data

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext
import java.io.File

class IptvRepository(private val context: Context) {
    private val prefs = PrefsStore(context)
    private val listsDir = File(context.filesDir, "playlists").also { it.mkdirs() }

    private val _playlists = MutableStateFlow(prefs.loadPlaylistsMeta())
    val playlists: StateFlow<List<Playlist>> = _playlists

    private val _channels = MutableStateFlow<List<Channel>>(emptyList())
    val channels: StateFlow<List<Channel>> = _channels

    private val healthCache = prefs.loadHealth().toMutableMap()

    init {
        // carrega canais das playlists ja importadas
        reloadAllFromDisk()
    }

    fun favorites(): Set<String> = prefs.favoriteIds()
    fun watchCounts(): Map<String, Int> = prefs.watchCounts()
    fun selectedPlaylistId(): String? = prefs.selectedPlaylistId
    fun setSelectedPlaylistId(id: String?) {
        prefs.selectedPlaylistId = id
    }

    fun toggleFavorite(channelId: String): Boolean = prefs.toggleFavorite(channelId)

    fun markWatched(channelId: String) = prefs.bumpWatch(channelId)

    fun filteredChannels(
        playlistId: String?,
        filter: ChannelFilter,
        query: String,
    ): List<Channel> {
        var list = _channels.value
        if (!playlistId.isNullOrBlank()) {
            list = list.filter { it.playlistId == playlistId }
        }
        if (query.isNotBlank()) {
            val q = query.trim()
            list = list.filter {
                it.name.contains(q, true) || it.group.contains(q, true)
            }
        }
        val favs = favorites()
        val watches = watchCounts()
        list = when (filter) {
            ChannelFilter.ALL -> list
            ChannelFilter.HIDE_DEAD -> list.filter { it.health != ChannelHealth.DEAD }
            ChannelFilter.DEAD_ONLY -> list.filter { it.health == ChannelHealth.DEAD }
            ChannelFilter.FAVORITES -> list.filter { favs.contains(it.id) }
            ChannelFilter.MOST_WATCHED -> list
                .filter { (watches[it.id] ?: 0) > 0 }
                .sortedByDescending { watches[it.id] ?: 0 }
        }
        if (filter != ChannelFilter.MOST_WATCHED) {
            list = list.sortedWith(
                compareByDescending<Channel> { favs.contains(it.id) }
                    .thenByDescending {
                        when (it.health) {
                            ChannelHealth.OK -> 3
                            ChannelHealth.DOUBT -> 2
                            ChannelHealth.UNKNOWN -> 1
                            ChannelHealth.DEAD -> 0
                        }
                    }
                    .thenBy { it.name.lowercase() },
            )
        }
        return list
    }

    suspend fun importM3uFromUri(uri: Uri): Playlist = withContext(Dispatchers.IO) {
        val name = queryDisplayName(uri) ?: "lista.m3u"
        val id = M3uParser.newPlaylistId()
        val dest = File(listsDir, "$id.m3u")
        context.contentResolver.openInputStream(uri)?.use { input ->
            dest.outputStream().use { output -> input.copyTo(output) }
        } ?: error("Nao foi possivel ler o arquivo")

        dest.inputStream().use { input ->
            val (playlist, channels) = M3uParser.parse(input, id, name.removeSuffix(".m3u").removeSuffix(".m3u8"))
            val withHealth = channels.map { ch ->
                ch.copy(health = healthCache[ch.id] ?: ChannelHealth.UNKNOWN)
            }
            val meta = playlist.copy(sourceUri = uri.toString(), channelCount = withHealth.size)
            val updated = (_playlists.value.filterNot { it.id == id } + meta)
            prefs.savePlaylistsMeta(updated)
            _playlists.value = updated
            mergeChannels(id, withHealth)
            prefs.selectedPlaylistId = id
            meta
        }
    }

    suspend fun importM3uFromText(text: String, displayName: String): Playlist = withContext(Dispatchers.IO) {
        val cleanName = displayName
            .removeSuffix(".m3u")
            .removeSuffix(".m3u8")
            .ifBlank { "lista" }
        val id = M3uParser.newPlaylistId()
        val dest = File(listsDir, "$id.m3u")
        dest.writeText(text, Charsets.UTF_8)
        dest.inputStream().use { input ->
            val (playlist, channels) = M3uParser.parse(input, id, cleanName)
            val withHealth = channels.map { ch ->
                ch.copy(health = healthCache[ch.id] ?: ChannelHealth.UNKNOWN)
            }
            val meta = playlist.copy(sourceUri = "text://$cleanName", channelCount = withHealth.size)
            val updated = (_playlists.value.filterNot { it.id == id } + meta)
            prefs.savePlaylistsMeta(updated)
            _playlists.value = updated
            mergeChannels(id, withHealth)
            prefs.selectedPlaylistId = id
            meta
        }
    }

    suspend fun importM3uFromAsset(assetPath: String, displayName: String): Playlist? = withContext(Dispatchers.IO) {
        runCatching {
            val text = context.assets.open(assetPath).bufferedReader().use { it.readText() }
            if (!text.contains("#EXTM3U") && !text.contains("http")) return@runCatching null
            importM3uFromText(text, displayName)
        }.getOrNull()
    }

    suspend fun tryImportFromDownloads(): Int = withContext(Dispatchers.IO) {
        val candidates = listOf(
            android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS),
            File("/sdcard/Download"),
            File("/storage/emulated/0/Download"),
        )
        var imported = 0
        candidates.filter { it.exists() }.forEach { dir ->
            dir.listFiles()
                ?.filter { f ->
                    f.isFile && (
                        f.name.lowercase().endsWith(".m3u") ||
                            f.name.lowercase().endsWith(".m3u8") ||
                            f.name.lowercase().endsWith(".txt")
                        )
                }
                ?.take(8)
                ?.forEach { file ->
                    runCatching {
                        val text = file.readText(Charsets.UTF_8)
                        if (text.contains("#EXT") || text.contains("http://") || text.contains("https://")) {
                            importM3uFromText(text, file.nameWithoutExtension)
                            imported++
                        }
                    }
                }
        }
        imported
    }

    fun removePlaylist(id: String) {
        File(listsDir, "$id.m3u").delete()
        val updated = _playlists.value.filterNot { it.id == id }
        prefs.savePlaylistsMeta(updated)
        _playlists.value = updated
        _channels.update { it.filterNot { ch -> ch.playlistId == id } }
        if (prefs.selectedPlaylistId == id) {
            prefs.selectedPlaylistId = updated.firstOrNull()?.id
        }
    }

    fun reloadAllFromDisk() {
        val metas = prefs.loadPlaylistsMeta()
        val all = mutableListOf<Channel>()
        val validMeta = mutableListOf<Playlist>()
        metas.forEach { meta ->
            val file = File(listsDir, "${meta.id}.m3u")
            if (!file.exists()) return@forEach
            runCatching {
                file.inputStream().use { input ->
                    val (_, channels) = M3uParser.parse(input, meta.id, meta.name)
                    all += channels.map { it.copy(health = healthCache[it.id] ?: ChannelHealth.UNKNOWN) }
                    validMeta += meta.copy(channelCount = channels.size)
                }
            }
        }
        prefs.savePlaylistsMeta(validMeta)
        _playlists.value = validMeta
        _channels.value = all
    }

    suspend fun reloadCurrentLists() = withContext(Dispatchers.IO) {
        reloadAllFromDisk()
    }

    suspend fun probeVisible(channels: List<Channel>, limit: Int = 50) {
        val results = ChannelProbe.probeBatch(channels, limit = limit)
        results.forEach { (id, pair) ->
            healthCache[id] = pair.first
        }
        prefs.saveHealth(healthCache)
        _channels.update { list ->
            list.map { ch ->
                val h = healthCache[ch.id]
                if (h != null) ch.copy(health = h, latencyMs = results[ch.id]?.second) else ch
            }
        }
    }

    private fun mergeChannels(playlistId: String, channels: List<Channel>) {
        _channels.update { current ->
            current.filterNot { it.playlistId == playlistId } + channels
        }
    }

    private fun queryDisplayName(uri: Uri): String? {
        context.contentResolver.query(uri, null, null, null, null)?.use { c ->
            val idx = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (idx >= 0 && c.moveToFirst()) return c.getString(idx)
        }
        return uri.lastPathSegment
    }
}
