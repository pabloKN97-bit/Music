package com.pablo.glassplayer

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.widget.RemoteViews

class GlassWidget : AppWidgetProvider() {
    override fun onUpdate(ctx: Context, m: AppWidgetManager, ids: IntArray) {
        render(ctx, "GlassPlayer", "Toca para abrir", null, false)
    }

    companion object {
        private fun svc(ctx: Context, action: String) = PendingIntent.getService(
            ctx, action.hashCode(), Intent(ctx, PlaybackService::class.java).setAction(action),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

        fun render(ctx: Context, title: String, artist: String, coverPath: String?, playing: Boolean) {
            val v = RemoteViews(ctx.packageName, R.layout.widget_glass)
            v.setTextViewText(R.id.w_title, title)
            v.setTextViewText(R.id.w_artist, artist)
            val bmp = coverPath?.let { BitmapFactory.decodeFile(it, BitmapFactory.Options().apply { inSampleSize = 4 }) }
            if (bmp != null) {
                v.setImageViewBitmap(R.id.w_cover, bmp)
                v.setImageViewBitmap(R.id.w_bg, blurred(bmp))
            } else {
                v.setImageViewResource(R.id.w_cover, android.R.drawable.ic_media_play)
                v.setImageViewBitmap(R.id.w_bg, null)
            }
            v.setImageViewResource(R.id.w_prev, android.R.drawable.ic_media_previous)
            v.setImageViewResource(R.id.w_play, if (playing) android.R.drawable.ic_media_pause else android.R.drawable.ic_media_play)
            v.setImageViewResource(R.id.w_next, android.R.drawable.ic_media_next)
            v.setOnClickPendingIntent(R.id.w_prev, svc(ctx, "PREV"))
            v.setOnClickPendingIntent(R.id.w_play, svc(ctx, "PLAY_PAUSE"))
            v.setOnClickPendingIntent(R.id.w_next, svc(ctx, "NEXT"))
            v.setOnClickPendingIntent(R.id.w_root, PendingIntent.getActivity(ctx, 0,
                Intent(ctx, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE))
            AppWidgetManager.getInstance(ctx).updateAppWidget(ComponentName(ctx, GlassWidget::class.java), v)
        }
    }
}
