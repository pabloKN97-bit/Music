package com.pablo.glassplayer

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { MaterialTheme(colorScheme = darkColorScheme(primary = Color(0xFFFF9800))) { PlayerScreen() } }
    }
}

fun fmt(ms: Long) = "%d:%02d".format(ms / 60000, ms / 1000 % 60)

@Composable
fun PlayerScreen() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val tracks = remember { mutableStateListOf<Track>().apply { addAll(Store.load(ctx)) } }
    var ctrl by remember { mutableStateOf<MediaController?>(null) }
    var idx by remember { mutableIntStateOf(0) }
    var playing by remember { mutableStateOf(false) }
    var pos by remember { mutableLongStateOf(0L) }
    var coverFor by remember { mutableIntStateOf(-1) }
    var coverMenu by remember { mutableIntStateOf(-1) }
    var dz by remember { mutableStateOf<Int?>(null) } // null=cerrado, -1=buscar canciones, >=0=portada de esa pista

    val notif = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(Unit) { if (Build.VERSION.SDK_INT >= 33) notif.launch(Manifest.permission.POST_NOTIFICATIONS) }

    DisposableEffect(Unit) {
        val f = MediaController.Builder(ctx, SessionToken(ctx, ComponentName(ctx, PlaybackService::class.java))).buildAsync()
        f.addListener({
            val c = f.get(); ctrl = c
            if (c.mediaItemCount != tracks.size) { c.setMediaItems(tracks.map { mediaItem(it) }); c.prepare() }
            idx = c.currentMediaItemIndex; playing = c.isPlaying
            c.addListener(object : Player.Listener {
                override fun onEvents(p: Player, e: Player.Events) { idx = p.currentMediaItemIndex; playing = p.isPlaying }
            })
        }, ContextCompat.getMainExecutor(ctx))
        onDispose { MediaController.releaseFuture(f) }
    }
    LaunchedEffect(ctrl) { while (true) { pos = ctrl?.currentPosition ?: 0L; delay(500) } }

    val addPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        scope.launch {
            val new = withContext(Dispatchers.IO) {
                uris.filter { u -> tracks.none { it.uri == u.toString() } }.map { u ->
                    runCatching { ctx.contentResolver.takePersistableUriPermission(u, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
                    readTrack(ctx, u)
                }
            }
            new.forEach { tracks.add(it); ctrl?.addMediaItem(mediaItem(it)) }
            Store.save(ctx, tracks)
        }
    }
    fun applyCover(i: Int, bytes: ByteArray) {
        if (i !in tracks.indices) return
        val path = saveCover(ctx, bytes) ?: return
        tracks[i].cover?.let { File(it).delete() }
        val nt = tracks[i].copy(cover = path); tracks[i] = nt
        Store.save(ctx, tracks)
        ctrl?.let { c ->
            val p = c.currentPosition; val isCur = c.currentMediaItemIndex == i
            c.replaceMediaItem(i, mediaItem(nt)); if (isCur) c.seekTo(i, p)
        }
    }
    val coverPicker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { u ->
        if (u != null) ctx.contentResolver.openInputStream(u)?.use { it.readBytes() }?.let { applyCover(coverFor, it) }
    }
    fun pickCover(i: Int) { coverMenu = i }
    fun remove(i: Int) { tracks.removeAt(i).cover?.let { File(it).delete() }; ctrl?.removeMediaItem(i); Store.save(ctx, tracks) }

    if (coverMenu >= 0) AlertDialog(onDismissRequest = { coverMenu = -1 }, title = { Text("Elegir portada") },
        confirmButton = { TextButton({
            coverFor = coverMenu; coverMenu = -1
            coverPicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
        }) { Text("Galería") } },
        dismissButton = { TextButton({ dz = coverMenu; coverMenu = -1 }) { Text("Deezer") } })
    dz?.let { target ->
        val q = if (target >= 0) tracks.getOrNull(target)?.let { t ->
            if (t.artist.startsWith("Artista")) t.title else "${t.title} ${t.artist.substringBefore(" · ")}"
        } ?: "" else ""
        DeezerDialog(q, target >= 0, onDismiss = { dz = null }) { d ->
            dz = null
            scope.launch {
                val bytes = withContext(Dispatchers.IO) { Deezer.download(d.coverBig) }
                if (target >= 0) { if (bytes != null) applyCover(target, bytes) }
                else if (d.preview.isNotEmpty()) {
                    val t = Track(d.preview, d.title, d.artist + " · Deezer (preview 30 s)", 30000L, bytes?.let { saveCover(ctx, it) })
                    tracks.add(t); ctrl?.addMediaItem(mediaItem(t))
                }
            }
        }
    }

    val cur = tracks.getOrNull(idx)
    val curBmp by produceState<Bitmap?>(null, cur?.cover) {
        value = withContext(Dispatchers.IO) { cur?.cover?.let { BitmapFactory.decodeFile(it) } }
    }
    val bg = remember(curBmp) { curBmp?.let { blurred(it) } }

    Box(Modifier.fillMaxSize().background(Color(0xFF121212))) {
        bg?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop, alpha = .6f) }
        Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = .45f)))
        Column(Modifier.fillMaxSize().systemBarsPadding()) {
            Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("GlassPlayer", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                IconButton({ dz = -1 }) { Icon(Icons.Default.Search, "Buscar en Deezer", tint = Color.White) }
                IconButton({ addPicker.launch(arrayOf("audio/mpeg", "audio/*")) }) { Icon(Icons.Default.Add, "Añadir MP3", tint = MaterialTheme.colorScheme.primary) }
            }
            if (tracks.isEmpty()) Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                Text("Pulsa + para añadir tus MP3", color = Color.White.copy(.6f))
            } else LazyColumn(Modifier.weight(1f)) {
                itemsIndexed(tracks, key = { _, t -> t.uri }) { i, t ->
                    val sel = i == idx
                    Row(Modifier.fillMaxWidth().clickable { ctrl?.let { it.seekTo(i, 0); it.play() } }
                        .background(if (sel) Color.White.copy(.10f) else Color.Transparent)
                        .padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("${i + 1}", color = Color.White.copy(.5f), modifier = Modifier.width(28.dp))
                        Thumb(t.cover, 44.dp) { pickCover(i) }
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text(t.title, color = if (sel) MaterialTheme.colorScheme.primary else Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(t.artist, color = Color.White.copy(.6f), fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        Text(fmt(t.durationMs), color = Color.White.copy(.6f), fontSize = 12.sp)
                        IconButton({ remove(i) }) { Icon(Icons.Default.Close, "Quitar", tint = Color.White.copy(.5f)) }
                    }
                }
            }
            if (cur != null) GlassPlayer(cur, bg, playing, pos, ctrl) { pickCover(idx) }
        }
    }
}

@Composable
fun Thumb(path: String?, size: Dp, onClick: () -> Unit) {
    val bmp by produceState<Bitmap?>(null, path) {
        value = withContext(Dispatchers.IO) {
            path?.let { BitmapFactory.decodeFile(it, BitmapFactory.Options().apply { inSampleSize = 4 }) }
        }
    }
    Box(Modifier.size(size).clip(RoundedCornerShape(10.dp)).background(Color.White.copy(.12f)).clickable(onClick = onClick),
        contentAlignment = Alignment.Center) {
        bmp?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
            ?: Icon(Icons.Default.Image, "Elegir portada", tint = Color.White.copy(.5f))
    }
}

@Composable
fun GlassPlayer(t: Track, bg: Bitmap?, playing: Boolean, pos: Long, c: MediaController?, onCover: () -> Unit) {
    val shape = RoundedCornerShape(28.dp)
    val dur = t.durationMs.coerceAtLeast(1L).toFloat()
    Box(Modifier.padding(12.dp).fillMaxWidth().clip(shape).border(1.dp, Color.White.copy(.35f), shape)) {
        bg?.let { Image(it.asImageBitmap(), null, Modifier.matchParentSize(), contentScale = ContentScale.Crop) }
        Box(Modifier.matchParentSize().background(Brush.verticalGradient(listOf(Color.White.copy(.28f), Color.White.copy(.08f)))))
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Thumb(t.cover, 64.dp, onCover)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(t.title, color = Color.White, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(t.artist, color = Color.White.copy(.7f), fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            Slider(value = pos.toFloat().coerceIn(0f, dur), onValueChange = { c?.seekTo(it.toLong()) }, valueRange = 0f..dur,
                colors = SliderDefaults.colors(thumbColor = Color.White, activeTrackColor = Color.White, inactiveTrackColor = Color.White.copy(.3f)))
            Row(Modifier.fillMaxWidth()) {
                Text(fmt(pos), color = Color.White.copy(.7f), fontSize = 12.sp, modifier = Modifier.weight(1f))
                Text(fmt(t.durationMs), color = Color.White.copy(.7f), fontSize = 12.sp)
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.CenterVertically) {
                IconButton({ c?.seekToPrevious() }) { Icon(Icons.Default.SkipPrevious, "Anterior", tint = Color.White, modifier = Modifier.size(36.dp)) }
                IconButton({ c?.let { if (it.isPlaying) it.pause() else it.play() } }, modifier = Modifier.size(64.dp)) {
                    Icon(if (playing) Icons.Default.Pause else Icons.Default.PlayArrow, "Play/Pausa", tint = Color.White, modifier = Modifier.size(48.dp))
                }
                IconButton({ c?.seekToNext() }) { Icon(Icons.Default.SkipNext, "Siguiente", tint = Color.White, modifier = Modifier.size(36.dp)) }
            }
        }
    }
}

@Composable
fun UrlThumb(url: String, size: Dp) {
    val bmp by produceState<Bitmap?>(null, url) {
        value = withContext(Dispatchers.IO) { Deezer.download(url)?.let { BitmapFactory.decodeByteArray(it, 0, it.size) } }
    }
    Box(Modifier.size(size).clip(RoundedCornerShape(8.dp)).background(Color.White.copy(.12f))) {
        bmp?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
    }
}

@Composable
fun DeezerDialog(initial: String, forCover: Boolean, onDismiss: () -> Unit, onPick: (DzTrack) -> Unit) {
    var q by remember { mutableStateOf(initial) }
    var results by remember { mutableStateOf<List<DzTrack>>(emptyList()) }
    var status by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    fun search() {
        if (q.isBlank()) return
        scope.launch {
            status = "Buscando…"
            val r = withContext(Dispatchers.IO) { runCatching { Deezer.search(q) }.getOrNull() }
            if (r == null) status = "Sin conexión o error de Deezer"
            else { results = r; status = if (r.isEmpty()) "Sin resultados" else "" }
        }
    }
    LaunchedEffect(Unit) { if (initial.isNotBlank()) search() }
    AlertDialog(onDismissRequest = onDismiss,
        confirmButton = { TextButton(onDismiss) { Text("Cerrar") } },
        title = { Text(if (forCover) "Portada desde Deezer" else "Buscar en Deezer") },
        text = {
            Column {
                OutlinedTextField(q, { q = it }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { search() }))
                if (status.isNotEmpty()) Text(status, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
                if (!forCover) Text("Deezer solo permite previews de 30 s", fontSize = 11.sp, modifier = Modifier.padding(top = 4.dp))
                LazyColumn(Modifier.heightIn(max = 360.dp)) {
                    items(results) { d ->
                        Row(Modifier.fillMaxWidth().clickable { onPick(d) }.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            UrlThumb(d.coverSmall, 48.dp)
                            Spacer(Modifier.width(10.dp))
                            Column {
                                Text(d.title, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(d.artist, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                        }
                    }
                }
            }
        })
}
