package br.com.iptv.app.ui

import android.app.Activity
import android.content.pm.ActivityInfo
import android.media.AudioManager
import android.view.WindowManager
import android.widget.FrameLayout
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Cast
import androidx.compose.material.icons.filled.CastConnected
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Fullscreen
import androidx.compose.material.icons.filled.FullscreenExit
import androidx.compose.material.icons.filled.PlaylistAdd
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.VolumeOff
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.material.icons.filled.WifiTethering
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.mediarouter.app.MediaRouteButton
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import br.com.iptv.app.IptvViewModel
import br.com.iptv.app.UiState
import br.com.iptv.app.data.Channel
import br.com.iptv.app.data.ChannelFilter
import br.com.iptv.app.data.ChannelHealth
import com.google.android.gms.cast.framework.CastButtonFactory
import kotlinx.coroutines.delay

private val Bg = Color(0xFF020617)
private val Panel = Color(0xFF0F172A)
private val Lime = Color(0xFFA3E635)
private val MuteColor = Color(0xFF94A3B8)

@Composable
fun IptvAppScreen(vm: IptvViewModel, onImportClick: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val snack = remember { SnackbarHostState() }
    val activity = LocalContext.current as Activity

    LaunchedEffect(state.message) {
        val msg = state.message ?: return@LaunchedEffect
        snack.showSnackbar(msg)
        vm.clearMessage()
    }
    LaunchedEffect(state.fullscreen) {
        activity.requestedOrientation = if (state.fullscreen) {
            ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        } else {
            ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        }
        if (state.fullscreen) {
            activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }
    BackHandler(enabled = state.fullscreen) { vm.setFullscreen(false) }

    Scaffold(containerColor = Bg, snackbarHost = { SnackbarHost(snack) }) { padding ->
        if (state.fullscreen) {
            FullscreenPlayer(state, vm, Modifier.fillMaxSize().padding(padding))
        } else {
            PortraitLayout(state, vm, onImportClick, Modifier.fillMaxSize().padding(padding))
        }
    }
}

@Composable
private fun PortraitLayout(
    state: UiState,
    vm: IptvViewModel,
    onImportClick: () -> Unit,
    modifier: Modifier,
) {
    Column(modifier = modifier.background(Bg)) {
        TopBar(state, vm, onImportClick)
        PlayerBox(state, vm, Modifier.fillMaxWidth().height(220.dp))
        ControlsRow(state, vm)
        PlaylistBlock(state, vm)
        FilterRow(state, vm)
        SearchRow(state, vm)
        ChannelList(state, vm, Modifier.fillMaxWidth().weight(1f))
    }
}

@Composable
private fun TopBar(state: UiState, vm: IptvViewModel, onImportClick: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(modifier = Modifier.weight(1f)) {
            Column {
                Text("IPTV", color = Lime, fontWeight = FontWeight.Bold, fontSize = 20.sp)
                val sub = if (state.casting) {
                    "Espelhando: ${state.castDevice ?: "TV"}"
                } else {
                    "${state.channels.size} canais"
                }
                Text(sub, color = MuteColor, fontSize = 12.sp)
            }
        }
        CastRouteButton()
        IconButton(onClick = onImportClick) {
            Icon(Icons.Default.PlaylistAdd, contentDescription = "Importar M3U", tint = Lime)
        }
        IconButton(onClick = vm::reloadLists) {
            Icon(Icons.Default.Refresh, contentDescription = "Recarregar", tint = Color.White)
        }
    }
}

@Composable
private fun CastRouteButton() {
    AndroidView(
        factory = { ctx ->
            MediaRouteButton(ctx).also {
                CastButtonFactory.setUpMediaRouteButton(ctx.applicationContext, it)
            }
        },
        modifier = Modifier.size(40.dp),
    )
}

@Composable
private fun ControlsRow(state: UiState, vm: IptvViewModel) {
    val chipColors = AssistChipDefaults.assistChipColors(
        containerColor = Panel,
        labelColor = Color.White,
        leadingIconContentColor = Lime,
    )
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 8.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        AssistChip(
            onClick = { if (state.casting) vm.stopCast() else vm.castSelected() },
            label = { Text(if (state.casting) "Parar TV" else "Espelhar TV") },
            leadingIcon = {
                Icon(if (state.casting) Icons.Default.CastConnected else Icons.Default.Cast, null, Modifier.size(16.dp))
            },
            colors = chipColors.copy(labelColor = Lime),
        )
        AssistChip(
            onClick = { vm.setFullscreen(true) },
            label = { Text("Tela cheia") },
            leadingIcon = { Icon(Icons.Default.Fullscreen, null, Modifier.size(16.dp)) },
            colors = chipColors,
        )
        AssistChip(
            onClick = vm::toggleMute,
            label = { Text(if (state.muted) "Som" else "Mudo") },
            leadingIcon = {
                Icon(if (state.muted) Icons.Default.VolumeOff else Icons.Default.VolumeUp, null, Modifier.size(16.dp))
            },
            colors = chipColors,
        )
        AssistChip(
            onClick = vm::probeChannels,
            label = { Text(if (state.probing) "Testando..." else "Testar sinal") },
            leadingIcon = { Icon(Icons.Default.WifiTethering, null, Modifier.size(16.dp)) },
            colors = chipColors,
        )
    }
}

@Composable
private fun PlaylistBlock(state: UiState, vm: IptvViewModel) {
    Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp)) {
        Text("Playlists", color = MuteColor, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        Spacer(modifier = Modifier.height(4.dp))
        if (state.playlists.isEmpty()) {
            Text("Nenhuma lista. Toque em + para importar M3U do aparelho.", color = MuteColor, fontSize = 12.sp)
        } else {
            state.playlists.forEach { p ->
                val selected = p.id == state.selectedPlaylistId
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 3.dp)
                        .background(if (selected) Color(0xFF14532D) else Panel, RoundedCornerShape(10.dp))
                        .border(1.dp, if (selected) Lime else Color(0xFF1E293B), RoundedCornerShape(10.dp))
                        .clickable { vm.selectPlaylist(p.id) }
                        .padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(p.name, color = Color.White, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text("${p.channelCount} canais", color = MuteColor, fontSize = 11.sp)
                    }
                    IconButton(onClick = { vm.removePlaylist(p.id) }) {
                        Icon(Icons.Default.Delete, contentDescription = "Remover", tint = Color(0xFFFB7185))
                    }
                }
            }
        }
    }
}

@Composable
private fun FilterRow(state: UiState, vm: IptvViewModel) {
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        listOf(
            ChannelFilter.ALL to "Todos",
            ChannelFilter.HIDE_DEAD to "Esconder mortos",
            ChannelFilter.DEAD_ONLY to "Mortos",
            ChannelFilter.FAVORITES to "Favoritos",
            ChannelFilter.MOST_WATCHED to "Mais assistidos",
        ).forEach { (filter, label) ->
            FilterChip(
                selected = state.filter == filter,
                onClick = { vm.setFilter(filter) },
                label = { Text(label, fontSize = 12.sp) },
                colors = FilterChipDefaults.filterChipColors(
                    selectedContainerColor = Lime,
                    selectedLabelColor = Bg,
                    containerColor = Panel,
                    labelColor = Color.White,
                ),
            )
        }
    }
}

@Composable
private fun SearchRow(state: UiState, vm: IptvViewModel) {
    OutlinedTextField(
        value = state.query,
        onValueChange = vm::setQuery,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
        singleLine = true,
        leadingIcon = { Icon(Icons.Default.Search, null, tint = MuteColor) },
        placeholder = { Text("Buscar canal") },
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = Lime,
            unfocusedBorderColor = Color(0xFF334155),
            focusedTextColor = Color.White,
            unfocusedTextColor = Color.White,
            cursorColor = Lime,
            focusedContainerColor = Panel,
            unfocusedContainerColor = Panel,
        ),
    )
}

@Composable
private fun ChannelList(state: UiState, vm: IptvViewModel, modifier: Modifier) {
    Box(modifier = modifier) {
        if (state.loading) {
            CircularProgressIndicator(modifier = Modifier.align(Alignment.Center), color = Lime)
        }
        LazyColumn(contentPadding = PaddingValues(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            items(state.channels, key = { it.id }) { ch ->
                ChannelRow(
                    channel = ch,
                    selected = state.selected?.id == ch.id,
                    favorite = state.favorites.contains(ch.id),
                    onClick = { vm.selectChannel(ch) },
                    onFav = { vm.toggleFavorite(ch) },
                )
            }
        }
    }
}

@Composable
private fun ChannelRow(
    channel: Channel,
    selected: Boolean,
    favorite: Boolean,
    onClick: () -> Unit,
    onFav: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(if (selected) Color(0xFF1E3A8A) else Panel, RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onFav, modifier = Modifier.size(28.dp)) {
            Icon(
                if (favorite) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                null,
                tint = if (favorite) Color(0xFFFBBF24) else MuteColor,
                modifier = Modifier.size(18.dp),
            )
        }
        Column(modifier = Modifier.weight(1f)) {
            Text(
                channel.name,
                color = if (channel.health == ChannelHealth.DEAD) MuteColor else Color.White,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
            )
            val meta = listOfNotNull(channel.group.ifBlank { null }, healthLabel(channel.health)).joinToString(" · ")
            Text(meta, color = MuteColor, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Text(healthBadge(channel.health), color = healthColor(channel.health), fontSize = 11.sp, fontWeight = FontWeight.Bold)
    }
}

private fun healthLabel(h: ChannelHealth) = when (h) {
    ChannelHealth.OK -> "ok"
    ChannelHealth.DOUBT -> "duvida"
    ChannelHealth.DEAD -> "morto"
    ChannelHealth.UNKNOWN -> "?"
}

private fun healthBadge(h: ChannelHealth) = when (h) {
    ChannelHealth.OK -> "OK"
    ChannelHealth.DOUBT -> "?"
    ChannelHealth.DEAD -> "X"
    ChannelHealth.UNKNOWN -> " "
}

private fun healthColor(h: ChannelHealth) = when (h) {
    ChannelHealth.OK -> Lime
    ChannelHealth.DOUBT -> Color(0xFFFACC15)
    ChannelHealth.DEAD -> Color(0xFFFB7185)
    ChannelHealth.UNKNOWN -> MuteColor
}

@Composable
private fun PlayerBox(state: UiState, vm: IptvViewModel, modifier: Modifier) {
    val context = LocalContext.current
    val audio = remember { context.getSystemService(AudioManager::class.java) }
    var gestureHint by remember { mutableStateOf<String?>(null) }
    var brightness by remember { mutableFloatStateOf(0.55f) }
    val exo = remember {
        ExoPlayer.Builder(context).build().apply {
            repeatMode = Player.REPEAT_MODE_OFF
            playWhenReady = true
        }
    }
    DisposableEffect(Unit) { onDispose { exo.release() } }
    LaunchedEffect(state.selected?.id) {
        val ch = state.selected ?: return@LaunchedEffect
        exo.setMediaItem(MediaItem.fromUri(ch.url))
        exo.prepare()
        exo.play()
    }
    LaunchedEffect(state.muted) { exo.volume = if (state.muted) 0f else 1f }

    Box(modifier = modifier.background(Color.Black).padding(horizontal = 8.dp)) {
        AndroidView(
            factory = { ctx ->
                PlayerView(ctx).apply {
                    player = exo
                    useController = true
                    layoutParams = FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.MATCH_PARENT,
                    )
                }
            },
            update = { it.player = exo },
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            modifier = Modifier
                .fillMaxHeight()
                .fillMaxWidth(0.28f)
                .align(Alignment.CenterStart)
                .pointerInput(Unit) {
                    detectVerticalDragGestures { _, dragAmount ->
                        audio.adjustStreamVolume(
                            AudioManager.STREAM_MUSIC,
                            if (dragAmount < 0) AudioManager.ADJUST_RAISE else AudioManager.ADJUST_LOWER,
                            0,
                        )
                        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
                        val cur = audio.getStreamVolume(AudioManager.STREAM_MUSIC)
                        gestureHint = "Volume ${cur * 100 / max}%"
                    }
                },
        )
        Box(
            modifier = Modifier
                .fillMaxHeight()
                .fillMaxWidth(0.28f)
                .align(Alignment.CenterEnd)
                .pointerInput(Unit) {
                    detectVerticalDragGestures { _, dragAmount ->
                        val delta = -dragAmount / size.height
                        brightness = (brightness + delta).coerceIn(0.05f, 1f)
                        (context as? Activity)?.window?.let { w ->
                            val lp = w.attributes
                            lp.screenBrightness = brightness
                            w.attributes = lp
                        }
                        gestureHint = "Brilho ${(brightness * 100).toInt()}%"
                    }
                },
        )
        gestureHint?.let { hint ->
            Text(
                hint,
                color = Color.White,
                modifier = Modifier
                    .align(Alignment.Center)
                    .background(Color(0xAA000000), RoundedCornerShape(8.dp))
                    .padding(horizontal = 12.dp, vertical = 8.dp),
            )
            LaunchedEffect(hint) {
                delay(700)
                if (gestureHint == hint) gestureHint = null
            }
        }
        if (state.selected == null) {
            Text("Selecione um canal", color = MuteColor, modifier = Modifier.align(Alignment.Center))
        }
    }
}

@Composable
private fun FullscreenPlayer(state: UiState, vm: IptvViewModel, modifier: Modifier) {
    Box(modifier = modifier.background(Color.Black)) {
        PlayerBox(state, vm, Modifier.fillMaxSize())
        Row(
            modifier = Modifier.align(Alignment.TopEnd).padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            CastRouteButton()
            IconButton(onClick = { if (state.casting) vm.stopCast() else vm.castSelected() }) {
                Icon(if (state.casting) Icons.Default.CastConnected else Icons.Default.Cast, "Cast", tint = Lime)
            }
            IconButton(onClick = vm::toggleMute) {
                Icon(if (state.muted) Icons.Default.VolumeOff else Icons.Default.VolumeUp, "Mudo", tint = Color.White)
            }
            IconButton(onClick = { vm.setFullscreen(false) }) {
                Icon(Icons.Default.FullscreenExit, "Sair", tint = Color.White)
            }
        }
        Text(
            state.selected?.name.orEmpty(),
            color = Color.White,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.align(Alignment.BottomStart).padding(16.dp),
        )
    }
}
