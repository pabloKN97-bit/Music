package com.pablo.glassplayer

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.provider.OpenableColumns
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

data class Track(val uri: String, val title: String, val artist: String, val durationMs: Long, val cover: String? = null)

object Store {
    private fun prefs(c: Context) = c.getSharedPreferences("glass", Context.MODE_PRIVATE)
    fun load(c: Context): MutableList<Track> {
        val a = JSONArray(prefs(c).getString("tracks", "[]"))
        return MutableList(a.length()) { i ->
            a.getJSONObject(i).let {
                Track(it.getString("u"), it.getString("t"), it.getString("a"), it.getLong("d"),
                    it.optString("c").takeIf { s -> s.isNotEmpty() })
            }
        }
    }
    fun save(c: Context, l: List<Track>) {
        val a = JSONArray()
        l.filter { !it.uri.startsWith("http") }.forEach { a.put(JSONObject().put("u", it.uri).put("t", it.title).put("a", it.artist).put("d", it.durationMs).put("c", it.cover ?: "")) }
        prefs(c).edit().putString("tracks", a.toString()).apply()
    }
}

fun mediaItem(t: Track): MediaItem = MediaItem.Builder().setUri(t.uri).setMediaId(t.uri)
    .setMediaMetadata(MediaMetadata.Builder().setTitle(t.title).setArtist(t.artist)
        .setArtworkUri(t.cover?.let { Uri.fromFile(File(it)) }).build()).build()

fun displayName(c: Context, u: Uri): String =
    c.contentResolver.query(u, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
        ?.use { if (it.moveToFirst()) it.getString(0) else null }?.substringBeforeLast('.') ?: "Audio"

fun readTrack(c: Context, u: Uri): Track {
    val r = MediaMetadataRetriever()
    return try {
        r.setDataSource(c, u)
        val title = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE)?.takeIf { it.isNotBlank() } ?: displayName(c, u)
        val artist = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)?.takeIf { it.isNotBlank() } ?: "Artista desconocido"
        val dur = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
        Track(u.toString(), title, artist, dur, r.embeddedPicture?.let { saveCover(c, it) })
    } catch (e: Exception) {
        Track(u.toString(), displayName(c, u), "Artista desconocido", 0L)
    } finally { r.release() }
}

private fun decodeSampled(b: ByteArray, target: Int): Bitmap? {
    val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(b, 0, b.size, o)
    var s = 1
    while (o.outWidth / (s * 2) >= target && o.outHeight / (s * 2) >= target) s *= 2
    return BitmapFactory.decodeByteArray(b, 0, b.size, BitmapFactory.Options().apply { inSampleSize = s })
}

/** Guarda la portada recortada en cuadrado (800px) dentro de la app. Devuelve la ruta. */
fun saveCover(c: Context, bytes: ByteArray): String? {
    val b = decodeSampled(bytes, 800) ?: return null
    val s = minOf(b.width, b.height)
    val sq = Bitmap.createBitmap(b, (b.width - s) / 2, (b.height - s) / 2, s, s)
    val f = File(c.filesDir, "cover_${System.nanoTime()}.jpg")
    f.outputStream().use { sq.compress(Bitmap.CompressFormat.JPEG, 90, it) }
    return f.path
}

/** Efecto "cristal": reducir y reescalar con filtro = desenfoque barato y compatible con todas las versiones. */
fun blurred(b: Bitmap): Bitmap =
    Bitmap.createScaledBitmap(Bitmap.createScaledBitmap(b, 16, 16, true), 256, 256, true)
