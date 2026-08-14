package br.com.iptv.standalone.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

class PrefsStore(context: Context) {
    private val sp = context.getSharedPreferences("iptv_android", Context.MODE_PRIVATE)

    var hideDeadDefault: Boolean
        get() = sp.getBoolean("hide_dead", true)
        set(v) = sp.edit().putBoolean("hide_dead", v).apply()

    var selectedPlaylistId: String?
        get() = sp.getString("selected_playlist", null)
        set(v) = sp.edit().putString("selected_playlist", v).apply()

    fun favoriteIds(): MutableSet<String> =
        sp.getStringSet("favorites", emptySet())?.toMutableSet() ?: mutableSetOf()

    fun toggleFavorite(channelId: String): Boolean {
        val set = favoriteIds()
        val nowFav = if (set.contains(channelId)) {
            set.remove(channelId)
            false
        } else {
            set.add(channelId)
            true
        }
        sp.edit().putStringSet("favorites", set).apply()
        return nowFav
    }

    fun isFavorite(channelId: String): Boolean = favoriteIds().contains(channelId)

    fun bumpWatch(channelId: String) {
        val map = watchCounts()
        map[channelId] = (map[channelId] ?: 0) + 1
        saveWatchCounts(map)
    }

    fun watchCounts(): MutableMap<String, Int> {
        val raw = sp.getString("watch_counts", "{}") ?: "{}"
        val obj = JSONObject(raw)
        val out = mutableMapOf<String, Int>()
        obj.keys().forEach { key -> out[key] = obj.optInt(key, 0) }
        return out
    }

    private fun saveWatchCounts(map: Map<String, Int>) {
        val obj = JSONObject()
        map.forEach { (k, v) -> obj.put(k, v) }
        sp.edit().putString("watch_counts", obj.toString()).apply()
    }

    fun savePlaylistsMeta(list: List<Playlist>) {
        val arr = JSONArray()
        list.forEach { p ->
            arr.put(
                JSONObject()
                    .put("id", p.id)
                    .put("name", p.name)
                    .put("sourceUri", p.sourceUri)
                    .put("channelCount", p.channelCount),
            )
        }
        sp.edit().putString("playlists_meta", arr.toString()).apply()
    }

    fun loadPlaylistsMeta(): List<Playlist> {
        val raw = sp.getString("playlists_meta", "[]") ?: "[]"
        val arr = JSONArray(raw)
        val out = mutableListOf<Playlist>()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            out += Playlist(
                id = o.getString("id"),
                name = o.getString("name"),
                sourceUri = o.getString("sourceUri"),
                channelCount = o.optInt("channelCount"),
            )
        }
        return out
    }

    fun saveHealth(map: Map<String, ChannelHealth>) {
        val obj = JSONObject()
        map.forEach { (k, v) -> obj.put(k, v.name) }
        sp.edit().putString("health_map", obj.toString()).apply()
    }

    fun loadHealth(): Map<String, ChannelHealth> {
        val raw = sp.getString("health_map", "{}") ?: "{}"
        val obj = JSONObject(raw)
        val out = mutableMapOf<String, ChannelHealth>()
        obj.keys().forEach { key ->
            out[key] = runCatching { ChannelHealth.valueOf(obj.getString(key)) }
                .getOrDefault(ChannelHealth.UNKNOWN)
        }
        return out
    }
}
