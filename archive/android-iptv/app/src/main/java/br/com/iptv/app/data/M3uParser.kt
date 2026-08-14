package br.com.iptv.app.data

import java.io.BufferedReader
import java.io.InputStream
import java.io.InputStreamReader
import java.security.MessageDigest
import java.util.UUID

object M3uParser {
    fun parse(
        input: InputStream,
        playlistId: String,
        playlistName: String = playlistId,
    ): Pair<Playlist, List<Channel>> {
        val channels = mutableListOf<Channel>()
        var name = "Canal"
        var group = ""
        var logo: String? = null

        BufferedReader(InputStreamReader(input, Charsets.UTF_8)).useLines { lines ->
            for (raw in lines) {
                val line = raw.trim()
                if (line.isEmpty()) continue
                if (line.startsWith("#EXTINF", ignoreCase = true)) {
                    group = extractAttr(line, "group-title").orEmpty()
                    logo = extractAttr(line, "tvg-logo")
                    name = line.substringAfterLast(',').trim().ifBlank { "Canal" }
                } else if (!line.startsWith("#")) {
                    val url = line
                    val id = sha1("$playlistId|$name|$url").take(16)
                    channels += Channel(
                        id = id,
                        name = name,
                        url = url,
                        group = group,
                        playlistId = playlistId,
                        logo = logo,
                    )
                    name = "Canal"
                    group = ""
                    logo = null
                }
            }
        }

        val playlist = Playlist(
            id = playlistId,
            name = playlistName,
            sourceUri = playlistId,
            channelCount = channels.size,
        )
        return playlist to channels
    }

    fun newPlaylistId(): String = UUID.randomUUID().toString().take(8)

    private fun extractAttr(line: String, key: String): String? {
        val regex = Regex("""$key="([^"]*)"""", RegexOption.IGNORE_CASE)
        return regex.find(line)?.groupValues?.getOrNull(1)
    }

    private fun sha1(text: String): String {
        val md = MessageDigest.getInstance("SHA-1")
        val bytes = md.digest(text.toByteArray(Charsets.UTF_8))
        return bytes.joinToString("") { "%02x".format(it) }
    }
}
