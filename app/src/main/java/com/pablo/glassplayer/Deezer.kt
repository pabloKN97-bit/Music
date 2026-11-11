package com.pablo.glassplayer

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

data class DzTrack(val title: String, val artist: String, val preview: String, val coverSmall: String, val coverBig: String)

/** API pública de Deezer: solo búsqueda, portadas y previews de 30 s. No devuelve anuncios. */
object Deezer {
    private fun get(url: String): ByteArray? {
        val c = URL(url).openConnection() as HttpURLConnection
        return try {
            c.connectTimeout = 8000; c.readTimeout = 10000
            if (c.responseCode == 200) c.inputStream.use { it.readBytes() } else null
        } finally { c.disconnect() }
    }

    fun download(url: String): ByteArray? = runCatching { get(url) }.getOrNull()

    fun search(q: String): List<DzTrack> {
        val body = get("https://api.deezer.com/search?limit=15&q=" + URLEncoder.encode(q, "UTF-8")) ?: throw IOException("HTTP")
        val arr = JSONObject(String(body)).optJSONArray("data") ?: return emptyList()
        return List(arr.length()) { i ->
            val o = arr.getJSONObject(i); val al = o.getJSONObject("album")
            DzTrack(o.getString("title"), o.getJSONObject("artist").getString("name"), o.optString("preview"),
                al.optString("cover_medium"), al.optString("cover_xl").ifEmpty { al.optString("cover_big") })
        }
    }
}
