package com.pablo.glassplayer

import android.content.Intent
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService

class PlaybackService : MediaSessionService() {
    private var session: MediaSession? = null

    override fun onCreate() {
        super.onCreate()
        val player = ExoPlayer.Builder(this)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC).build(), true)
            .setHandleAudioBecomingNoisy(true).build()
        player.setMediaItems(Store.load(this).map { mediaItem(it) })
        player.prepare()
        player.addListener(object : Player.Listener {
            override fun onEvents(p: Player, e: Player.Events) {
                val m = p.mediaMetadata
                GlassWidget.render(this@PlaybackService, m.title?.toString() ?: "GlassPlayer",
                    m.artist?.toString() ?: "", m.artworkUri?.path, p.isPlaying)
            }
        })
        session = MediaSession.Builder(this, player).build()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val p = session?.player
        when (intent?.action) {
            "PLAY_PAUSE" -> p?.let { if (it.isPlaying) it.pause() else it.play() }
            "NEXT" -> p?.seekToNext()
            "PREV" -> p?.seekToPrevious()
        }
        return super.onStartCommand(intent, flags, startId)
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo) = session

    override fun onDestroy() {
        session?.run { player.release(); release() }
        session = null
        super.onDestroy()
    }
}
