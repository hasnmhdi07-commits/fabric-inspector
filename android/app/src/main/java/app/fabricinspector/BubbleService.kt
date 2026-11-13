package app.fabricinspector

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Rect
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.DisplayMetrics
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowManager
import android.webkit.WebView
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * The floating bubble.
 *  tap bubble -> dimmed screen with a selection rectangle -> "Analyse area" -> the selected part of the screen
 *  is sent to the analysis server -> the result slides up as a sheet over the current app.
 * Android rules: drawing over other apps needs the overlay permission; reading the screen needs the user's
 * consent each session and a foreground service with a visible notification.
 */
class BubbleService : Service() {
    private val wm by lazy { getSystemService(Context.WINDOW_SERVICE) as WindowManager }
    private val prefs by lazy { getSharedPreferences("settings", Context.MODE_PRIVATE) }
    private val main = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()

    private var projection: MediaProjection? = null
    private var reader: ImageReader? = null
    private var display: VirtualDisplay? = null
    private var screenW = 0
    private var screenH = 0

    private var bubble: BubbleView? = null
    private lateinit var bubbleLp: WindowManager.LayoutParams
    private var selection: View? = null
    private var sheet: View? = null
    private var sheetWeb: WebView? = null
    private var sheetWait: View? = null
    private var request = 0                      // ignores answers of a check the user already closed

    override fun onBind(intent: Intent?): IBinder? = null

    // ------------------------------------------------------------------ start / stop
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) { stopSelf(); return START_NOT_STICKY }
        if (intent?.action != ACTION_START || projection != null) return START_NOT_STICKY

        val note = notification()
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, note, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        else startForeground(1, note)

        val code = intent.getIntExtra(EXTRA_CODE, 0)
        @Suppress("DEPRECATION") val data = intent.getParcelableExtra<Intent>(EXTRA_DATA)
        val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val mp = try { if (data != null) mpm.getMediaProjection(code, data) else null } catch (e: Exception) { null }
        if (mp == null) { stopSelf(); return START_NOT_STICKY }
        projection = mp
        mp.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() { stopSelf() }         // the user ended screen sharing from the system UI
        }, main)
        try { setupCapture() } catch (e: Exception) { stopSelf(); return START_NOT_STICKY }
        showBubble()
        running = true
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        running = false
        request++
        main.removeCallbacksAndMessages(null)
        for (v in listOf(bubble, selection, sheet)) if (v != null) try { wm.removeView(v) } catch (_: Exception) {}
        bubble = null; selection = null; sheet = null
        sheetWeb?.destroy(); sheetWeb = null
        try { display?.release() } catch (_: Exception) {}
        try { reader?.close() } catch (_: Exception) {}
        try { projection?.stop() } catch (_: Exception) {}
        io.shutdownNow()
        super.onDestroy()
    }

    private fun notification(): Notification {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(NotificationChannel("bubble", getString(R.string.notif_channel), NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, BubbleService::class.java).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE)
        return Notification.Builder(this, "bubble")
            .setSmallIcon(R.drawable.ic_stat_bubble)
            .setContentTitle(getString(R.string.notif_title))
            .setContentText(getString(R.string.notif_text))
            .setContentIntent(open)
            .addAction(Notification.Action.Builder(null, getString(R.string.stop), stop).build())
            .setOngoing(true)
            .build()
    }

    // ------------------------------------------------------------------ screen capture
    private fun realMetrics(): DisplayMetrics {
        val m = DisplayMetrics()
        @Suppress("DEPRECATION") wm.defaultDisplay.getRealMetrics(m)
        return m
    }

    @SuppressLint("WrongConstant")
    private fun setupCapture() {
        val m = realMetrics()
        screenW = m.widthPixels; screenH = m.heightPixels
        val r = ImageReader.newInstance(screenW, screenH, PixelFormat.RGBA_8888, 2)
        reader = r
        display = projection!!.createVirtualDisplay("fabric-inspector", screenW, screenH, m.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, r.surface, null, main)
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        val m = realMetrics()
        if (m.widthPixels == screenW && m.heightPixels == screenH) return
        // the phone was rotated: capture at the new size, drop a half-made selection, keep the bubble on screen
        screenW = m.widthPixels; screenH = m.heightPixels
        val old = reader
        val r = ImageReader.newInstance(screenW, screenH, PixelFormat.RGBA_8888, 2)
        reader = r
        try { display?.resize(screenW, screenH, m.densityDpi); display?.surface = r.surface } catch (_: Exception) {}
        old?.close()
        cancelSelection()
        bubble?.let { snapBubble() }
    }

    /** The newest screen picture, or null if Android has none ready yet. */
    private fun grab(): Bitmap? {
        val img = try { reader?.acquireLatestImage() } catch (e: Exception) { null } ?: return null
        try {
            val plane = img.planes[0]
            val padded = Bitmap.createBitmap(plane.rowStride / plane.pixelStride, img.height, Bitmap.Config.ARGB_8888)
            padded.copyPixelsFromBuffer(plane.buffer)
            return if (padded.width == img.width) padded else Bitmap.createBitmap(padded, 0, 0, img.width, img.height)
        } finally { img.close() }
    }

    // ------------------------------------------------------------------ bubble
    private fun overlayParams(w: Int, h: Int, extraFlags: Int = 0) = WindowManager.LayoutParams(
        w, h, WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or extraFlags, PixelFormat.TRANSLUCENT
    ).apply { gravity = Gravity.TOP or Gravity.START }

    @SuppressLint("ClickableViewAccessibility")
    private fun showBubble() {
        val size = dp(58f)
        val b = BubbleView(this)
        bubbleLp = overlayParams(size, size).apply {
            x = prefs.getInt("bx", screenW - size - dp(6f)); y = prefs.getInt("by", (screenH * 0.42f).toInt())
        }
        var downX = 0f; var downY = 0f; var startX = 0; var startY = 0; var moved = false
        b.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { downX = e.rawX; downY = e.rawY; startX = bubbleLp.x; startY = bubbleLp.y; moved = false }
                MotionEvent.ACTION_MOVE -> {
                    if (abs(e.rawX - downX) > dp(8f) || abs(e.rawY - downY) > dp(8f)) moved = true
                    if (moved) { bubbleLp.x = startX + (e.rawX - downX).toInt(); bubbleLp.y = startY + (e.rawY - downY).toInt(); wm.updateViewLayout(b, bubbleLp) }
                }
                MotionEvent.ACTION_UP -> if (moved) snapBubble() else startSelection()
            }
            true
        }
        bubble = b
        wm.addView(b, bubbleLp)
        snapBubble()
    }

    /** The bubble rests on the nearest left/right screen edge. */
    private fun snapBubble() {
        val b = bubble ?: return
        val size = bubbleLp.width
        bubbleLp.x = if (bubbleLp.x + size / 2 < screenW / 2) dp(6f) else screenW - size - dp(6f)
        bubbleLp.y = min(max(bubbleLp.y, dp(30f)), screenH - size - dp(50f))
        try { wm.updateViewLayout(b, bubbleLp) } catch (_: Exception) {}
        prefs.edit().putInt("bx", bubbleLp.x).putInt("by", bubbleLp.y).apply()
    }

    // ------------------------------------------------------------------ select area
    private fun startSelection() {
        if (selection != null) return
        closeSheet()
        val root = FrameLayout(this)
        val crop = CropView(this)
        root.addView(crop, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        root.addView(TextView(this).apply {
            setText(R.string.select_hint); setTextColor(Color.WHITE); textSize = 14f; typeface = Typeface.DEFAULT_BOLD
            background = pill(Color.argb(130, 0, 0, 0), 8f); setPadding(dp(12f), dp(7f), dp(12f), dp(7f))
        }, FrameLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT, Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply { topMargin = dp(64f) })

        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        row.addView(button(R.string.cancel, Color.argb(160, 0, 0, 0), Color.WHITE) { cancelSelection() },
            LinearLayout.LayoutParams(WRAP_CONTENT, dp(46f)).apply { marginEnd = dp(10f) })
        row.addView(button(R.string.analyse, Fern.FERN, Color.WHITE) {
            val loc = IntArray(2); crop.getLocationOnScreen(loc)
            val r = Rect((crop.rect.left + loc[0]).toInt(), (crop.rect.top + loc[1]).toInt(),
                         (crop.rect.right + loc[0]).toInt(), (crop.rect.bottom + loc[1]).toInt())
            removeSelection()                                   // nothing of ours may be in the picture
            main.postDelayed({ captureAndAnalyse(r, 0) }, 300)
        }, LinearLayout.LayoutParams(WRAP_CONTENT, dp(46f)))
        root.addView(row, FrameLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT, Gravity.BOTTOM).apply { bottomMargin = dp(72f) })

        val lp = overlayParams(MATCH_PARENT, MATCH_PARENT,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS)
        if (Build.VERSION.SDK_INT >= 28) lp.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
        bubble?.visibility = View.GONE
        selection = root
        wm.addView(root, lp)
    }

    private fun removeSelection() {
        selection?.let { try { wm.removeView(it) } catch (_: Exception) {} }
        selection = null
    }

    private fun cancelSelection() { removeSelection(); bubble?.visibility = View.VISIBLE }

    // ------------------------------------------------------------------ capture -> server -> result
    private fun captureAndAnalyse(area: Rect, attempt: Int) {
        val shot = grab()
        if (shot == null) {
            if (attempt < 6) { main.postDelayed({ captureAndAnalyse(area, attempt + 1) }, 150); return }
            bubble?.visibility = View.VISIBLE
            showSheet(); showMessage(getString(R.string.err_capture)); return
        }
        bubble?.visibility = View.VISIBLE
        val r = Rect(max(0, area.left), max(0, area.top), min(shot.width, area.right), min(shot.height, area.bottom))
        if (r.width() < 64 || r.height() < 64) { showSheet(); showMessage(getString(R.string.err_small)); return }
        var part = Bitmap.createBitmap(shot, r.left, r.top, r.width(), r.height())
        val longest = max(part.width, part.height)
        if (longest > 1600) part = Bitmap.createScaledBitmap(part, part.width * 1600 / longest, part.height * 1600 / longest, true)

        showSheet()
        val mine = ++request
        val url = BuildConfig.API_URL + "?format=html" +
            (if (prefs.getBoolean("shade", false)) "&shade=1" else "") + (if (prefs.getBoolean("skew", false)) "&skew=1" else "")
        io.execute {
            val jpeg = ByteArrayOutputStream().also { part.compress(Bitmap.CompressFormat.JPEG, 88, it) }.toByteArray()
            var html: String? = null
            var verdict = ""
            try {
                val c = URL(url).openConnection() as HttpURLConnection
                c.requestMethod = "POST"; c.doOutput = true; c.connectTimeout = 15000; c.readTimeout = 60000
                c.setRequestProperty("Content-Type", "image/jpeg")
                c.setFixedLengthStreamingMode(jpeg.size)
                c.outputStream.use { it.write(jpeg) }
                val stream = if (c.responseCode in 200..299) c.inputStream else c.errorStream   // errors are readable pages too
                html = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }
                verdict = c.getHeaderField("X-Fabric-Verdict") ?: ""
                c.disconnect()
            } catch (e: Exception) { html = null }
            main.post {
                if (mine != request) return@post
                if (html.isNullOrEmpty() || !html.contains("<html")) { showMessage(getString(R.string.err_network)); return@post }
                val (state, severity) = (verdict.split("|") + listOf("", "")).let { it[0] to it[1] }
                bubble?.badge = Fern.SEVERITY[severity] ?: if (state == "cannot") Fern.INK2 else null
                sheetWait?.visibility = View.GONE
                sheetWeb?.apply { visibility = View.VISIBLE; loadDataWithBaseURL(null, html, "text/html", "utf-8", null) }
            }
        }
    }

    // ------------------------------------------------------------------ result sheet (slides over the current app)
    private fun showSheet() {
        closeSheet()
        val root = FrameLayout(this).apply { setBackgroundColor(Color.argb(110, 10, 12, 30)); setOnClickListener { closeSheet() } }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; isClickable = true
            background = GradientDrawable().apply {
                setColor(Fern.SURFACE); val r = dp(20f).toFloat(); cornerRadii = floatArrayOf(r, r, r, r, 0f, 0f, 0f, 0f)
            }
        }
        panel.addView(View(this).apply { background = pill(Fern.LINE, 2f) },
            LinearLayout.LayoutParams(dp(38f), dp(4f)).apply { gravity = Gravity.CENTER_HORIZONTAL; topMargin = dp(8f) })
        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(14f), dp(4f), dp(8f), dp(4f)) }
        head.addView(TextView(this).apply { setText(R.string.app_name); setTextColor(Fern.INK); textSize = 15f; typeface = Typeface.DEFAULT_BOLD },
            LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
        head.addView(button(R.string.close, Fern.PAPER, Fern.INK) { closeSheet() }, LinearLayout.LayoutParams(WRAP_CONTENT, dp(38f)))
        panel.addView(head)

        val body = FrameLayout(this)
        val wait = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER; setPadding(dp(24f), dp(24f), dp(24f), dp(24f)) }
        wait.addView(ProgressBar(this), LinearLayout.LayoutParams(dp(36f), dp(36f)))
        wait.addView(TextView(this).apply { setText(R.string.analysing); setTextColor(Fern.INK2); textSize = 15f; gravity = Gravity.CENTER; setPadding(0, dp(12f), 0, 0) })
        body.addView(wait, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        val web = WebView(this).apply { visibility = View.GONE; setBackgroundColor(Fern.SURFACE); settings.javaScriptEnabled = false }
        body.addView(web, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        panel.addView(body, LinearLayout.LayoutParams(MATCH_PARENT, 0, 1f))

        root.addView(panel, FrameLayout.LayoutParams(MATCH_PARENT, (screenH * 0.78f).toInt(), Gravity.BOTTOM))
        sheet = root; sheetWeb = web; sheetWait = wait
        wm.addView(root, overlayParams(MATCH_PARENT, MATCH_PARENT))
    }

    /** A plain message in the sheet (errors): what happened and what to do. */
    private fun showMessage(text: String) {
        val wait = sheetWait as? LinearLayout ?: return
        wait.getChildAt(0).visibility = View.GONE
        (wait.getChildAt(1) as TextView).apply { this.text = text; setTextColor(Fern.INK) }
    }

    private fun closeSheet() {
        request++
        sheet?.let { try { wm.removeView(it) } catch (_: Exception) {} }
        sheetWeb?.destroy()
        sheet = null; sheetWeb = null; sheetWait = null
    }

    // ------------------------------------------------------------------ small helpers
    private fun pill(color: Int, radiusDp: Float) = GradientDrawable().apply { setColor(color); cornerRadius = dp(radiusDp).toFloat() }

    private fun button(textRes: Int, bg: Int, fg: Int, onClick: () -> Unit) = Button(this).apply {
        setText(textRes); isAllCaps = false; textSize = 15f; setTextColor(fg); typeface = Typeface.DEFAULT_BOLD
        background = GradientDrawable().apply { setColor(bg); cornerRadius = dp(23f).toFloat(); if (bg == Fern.PAPER) setStroke(dp(1f), Fern.LINE) }
        setPadding(dp(20f), 0, dp(20f), 0); minHeight = 0; minimumHeight = 0; stateListAnimator = null
        setOnClickListener { onClick() }
    }

    companion object {
        const val ACTION_START = "app.fabricinspector.START"
        const val ACTION_STOP = "app.fabricinspector.STOP"
        const val EXTRA_CODE = "code"
        const val EXTRA_DATA = "data"
        @Volatile var running = false
    }
}
