package br.com.iptv.app

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.com.iptv.app.cast.CastController
import br.com.iptv.app.data.Channel
import br.com.iptv.app.data.ChannelFilter
import br.com.iptv.app.data.Playlist
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class UiState(
    val playlists: List<Playlist> = emptyList(),
    val selectedPlaylistId: String? = null,
    val channels: List<Channel> = emptyList(),
    val selected: Channel? = null,
    val filter: ChannelFilter = ChannelFilter.HIDE_DEAD,
    val query: String = "",
    val favorites: Set<String> = emptySet(),
    val fullscreen: Boolean = false,
    val muted: Boolean = false,
    val loading: Boolean = false,
    val probing: Boolean = false,
    val message: String? = null,
    val castAvailable: Boolean = true,
    val casting: Boolean = false,
    val castDevice: String? = null,
)

class IptvViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = (app as IptvApp).repository
    private val cast = CastController(app)

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state.asStateFlow()

    private var observeJob: Job? = null

    init {
        cast.init()
        cast.refreshAvailability()
        val initialPlaylist = repo.selectedPlaylistId() ?: repo.playlists.value.firstOrNull()?.id
        _state.update {
            it.copy(
                playlists = repo.playlists.value,
                selectedPlaylistId = initialPlaylist,
                favorites = repo.favorites(),
                castAvailable = cast.available.value,
                casting = cast.casting.value,
                castDevice = cast.deviceName.value,
            )
        }
        refreshChannels()
        observeJob = viewModelScope.launch {
            launch {
                repo.playlists.collect { list ->
                    _state.update { s -> s.copy(playlists = list) }
                    refreshChannels()
                }
            }
            launch {
                repo.channels.collect {
                    refreshChannels()
                }
            }
            launch {
                cast.casting.collect { c ->
                    _state.update { it.copy(casting = c, castDevice = cast.deviceName.value) }
                }
            }
            launch {
                cast.deviceName.collect { name ->
                    _state.update { it.copy(castDevice = name) }
                }
            }
        }
    }

    private fun refreshChannels() {
        val s = _state.value
        val list = repo.filteredChannels(s.selectedPlaylistId, s.filter, s.query)
        val selected = s.selected?.let { sel -> list.find { it.id == sel.id } ?: sel }
        _state.update {
            it.copy(
                channels = list,
                selected = selected,
                favorites = repo.favorites(),
            )
        }
    }

    fun selectPlaylist(id: String?) {
        repo.setSelectedPlaylistId(id)
        _state.update { it.copy(selectedPlaylistId = id) }
        refreshChannels()
    }

    fun setFilter(value: ChannelFilter) {
        _state.update { it.copy(filter = value) }
        refreshChannels()
    }

    fun setQuery(value: String) {
        _state.update { it.copy(query = value) }
        refreshChannels()
    }

    fun selectChannel(channel: Channel) {
        repo.markWatched(channel.id)
        _state.update { it.copy(selected = channel, favorites = repo.favorites()) }
    }

    fun toggleFavorite(channel: Channel) {
        repo.toggleFavorite(channel.id)
        _state.update { it.copy(favorites = repo.favorites()) }
        refreshChannels()
    }

    fun setFullscreen(value: Boolean) {
        _state.update { it.copy(fullscreen = value) }
    }

    fun toggleMute() {
        _state.update { it.copy(muted = !it.muted) }
    }

    fun clearMessage() {
        _state.update { it.copy(message = null) }
    }

    fun importM3u(uri: Uri) {
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            runCatching {
                val p = repo.importM3uFromUri(uri)
                _state.update {
                    it.copy(
                        selectedPlaylistId = p.id,
                        message = "Lista importada: ${p.name} (${p.channelCount} canais)",
                    )
                }
                refreshChannels()
            }.onFailure { e ->
                _state.update { it.copy(message = "Falha ao importar: ${e.message}") }
            }
            _state.update { it.copy(loading = false) }
        }
    }

    fun removePlaylist(id: String) {
        repo.removePlaylist(id)
        val next = repo.playlists.value.firstOrNull()?.id
        _state.update {
            it.copy(
                selectedPlaylistId = if (it.selectedPlaylistId == id) next else it.selectedPlaylistId,
                message = "Lista removida",
            )
        }
        refreshChannels()
    }

    fun reloadLists() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            repo.reloadCurrentLists()
            _state.update { it.copy(loading = false, message = "Listas recarregadas") }
            refreshChannels()
        }
    }

    fun probeChannels() {
        viewModelScope.launch {
            _state.update { it.copy(probing = true) }
            repo.probeVisible(_state.value.channels, limit = 60)
            _state.update { it.copy(probing = false, message = "Sinal atualizado") }
            refreshChannels()
        }
    }

    fun castSelected() {
        val ch = _state.value.selected
        if (ch == null) {
            _state.update { it.copy(message = "Selecione um canal antes de espelhar") }
            return
        }
        cast.refreshAvailability()
        val result = cast.castUrl(ch.url, ch.name, ch.logo)
        _state.update {
            it.copy(
                message = result.fold(
                    onSuccess = { "Espelhando: ${cast.deviceName.value ?: "TV"}" },
                    onFailure = { err -> err.message },
                ),
                casting = cast.casting.value,
                castDevice = cast.deviceName.value,
            )
        }
    }

    fun stopCast() {
        cast.stop()
        _state.update { it.copy(casting = false, castDevice = null, message = "Cast encerrado") }
    }

    override fun onCleared() {
        observeJob?.cancel()
        super.onCleared()
    }
}
