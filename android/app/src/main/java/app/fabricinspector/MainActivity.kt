package app.fabricinspector

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/** The only screen: switch the bubble on/off and walk through the two permissions Android requires. */
class MainActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var toggle: Button
    private val prefs by lazy { getSharedPreferences("settings", Context.MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val pad = dp(20f)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad, pad, pad) }

        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        head.addView(BubbleView(this), LinearLayout.LayoutParams(dp(52f), dp(52f)))
        head.addView(TextView(this).apply {
            text = getString(R.string.app_name); textSize = 24f; setTextColor(Fern.INK)
            typeface = Typeface.create("sans-serif-condensed", Typeface.BOLD); setPadding(dp(12f), 0, 0, 0)
        })
        col.addView(head)
        col.addView(text(R.string.intro, 15f, Fern.INK2, top = 14f))

        status = text(R.string.stopped, 15f, Fern.INK, top = 18f).apply { typeface = Typeface.DEFAULT_BOLD }
        col.addView(status)

        toggle = Button(this).apply {
            isAllCaps = false; textSize = 16f; setTextColor(Fern.PAPER)
            background = GradientDrawable().apply { setColor(Fern.FERN); cornerRadius = dp(10f).toFloat() }
            setOnClickListener { if (BubbleService.running) stopBubble() else startBubble() }
        }
        col.addView(toggle, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(52f)).apply { topMargin = dp(12f) })

        col.addView(text(R.string.checks, 12f, Fern.INK2, top = 26f).apply { typeface = Typeface.DEFAULT_BOLD; letterSpacing = 0.08f; isAllCaps = true })
        col.addView(check(R.string.shade, "shade"))
        col.addView(check(R.string.skew, "skew"))
        col.addView(text(R.string.checks_hint, 13f, Fern.INK2, top = 2f))
        col.addView(text(R.string.privacy, 13f, Fern.INK2, top = 22f))

        setContentView(ScrollView(this).apply { addView(col) })
    }

    private fun text(res: Int, size: Float, color: Int, top: Float) = TextView(this).apply {
        setText(res); textSize = size; setTextColor(color); setPadding(0, dp(top), 0, 0); setLineSpacing(0f, 1.15f)
    }

    private fun check(res: Int, key: String) = CheckBox(this).apply {
        setText(res); textSize = 15f; setTextColor(Fern.INK); buttonTintList = ColorStateList.valueOf(Fern.FERN)
        isChecked = prefs.getBoolean(key, false)
        setOnCheckedChangeListener { _, on -> prefs.edit().putBoolean(key, on).apply() }
    }

    override fun onResume() { super.onResume(); refresh() }

    private fun refresh(message: Int? = null) {
        toggle.setText(if (BubbleService.running) R.string.stop else R.string.start)
        status.setText(message ?: if (BubbleService.running) R.string.running else R.string.stopped)
    }

    // ---- start: permission 1 (draw over other apps) -> notification permission -> permission 2 (screen capture)
    private fun startBubble() {
        if (!Settings.canDrawOverlays(this)) {
            refresh(R.string.step_overlay)
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
            return
        }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIFY)
            return
        }
        askCapture()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_NOTIFY) askCapture()        // the bubble works with or without the notification
    }

    private fun askCapture() {
        refresh(R.string.step_capture)
        val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        @Suppress("DEPRECATION")
        startActivityForResult(mpm.createScreenCaptureIntent(), REQ_CAPTURE)
    }

    @Deprecated("platform API without AndroidX")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ_CAPTURE) return
        if (resultCode != RESULT_OK || data == null) { refresh(R.string.capture_denied); return }
        val i = Intent(this, BubbleService::class.java).setAction(BubbleService.ACTION_START)
            .putExtra(BubbleService.EXTRA_CODE, resultCode).putExtra(BubbleService.EXTRA_DATA, data)
        startForegroundService(i)
        BubbleService.running = true
        refresh()
    }

    private fun stopBubble() {
        stopService(Intent(this, BubbleService::class.java))
        BubbleService.running = false
        refresh()
    }

    companion object {
        private const val REQ_CAPTURE = 1
        private const val REQ_NOTIFY = 2
    }
}
