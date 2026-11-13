package app.fabricinspector

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.media.ExifInterface
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.provider.Settings
import android.util.Base64
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors

/**
 * The whole app in one screen: the Fabric Inspector web app (camera, photo upload, select-area, history,
 * settings - the AI runs on the phone) plus what only a native app can do: the floating bubble over other
 * apps, receiving photos shared from other apps, and the Android share sheet.
 * The page is loaded from the server once and then kept for offline use, so a newly trained model reaches
 * the phone without installing a new APK.
 */
class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var offline: View
    private val prefs by lazy { getSharedPreferences("settings", Context.MODE_PRIVATE) }
    private val io = Executors.newSingleThreadExecutor()

    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var cameraRequest: PermissionRequest? = null
    private var pageReady = false
    private var loadFailed = false
    @Volatile private var shared: String? = null          // a photo shared to the app, waiting for the page

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        web = WebView(this).apply {
            setBackgroundColor(Fern.SURFACE)
            overScrollMode = View.OVER_SCROLL_NEVER
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true               // settings + offline cache + history
            settings.mediaPlaybackRequiresUserGesture = false   // live camera preview
            settings.allowFileAccess = false
            settings.setSupportZoom(false)
            addJavascriptInterface(Bridge(), "FabricNative")
            webViewClient = Client()
            webChromeClient = Chrome()
        }
        offline = offlineView()
        setContentView(FrameLayout(this).apply {
            setBackgroundColor(Fern.SURFACE)
            addView(web, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            addView(offline, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        })
        takeIntent(intent)
        if (savedInstanceState == null || web.restoreState(savedInstanceState) == null) web.loadUrl(BuildConfig.APP_URL)
    }

    override fun onSaveInstanceState(outState: Bundle) { super.onSaveInstanceState(outState); web.saveState(outState) }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); takeIntent(intent) }
    override fun onResume() { super.onResume(); web.onResume(); tellBubble() }      // the bubble may have been stopped from its notification
    override fun onPause() { web.onPause(); super.onPause() }
    override fun onDestroy() { io.shutdownNow(); web.destroy(); super.onDestroy() }

    @Deprecated("platform API without AndroidX")
    override fun onBackPressed() {
        if (!pageReady) { @Suppress("DEPRECATION") super.onBackPressed(); return }
        web.evaluateJavascript("!!(window.fabricBack && window.fabricBack())") { handled ->
            if (handled != "true") moveTaskToBack(true)
        }
    }

    // ------------------------------------------------------------------ page <-> app
    private fun js(code: String) = runOnUiThread { if (pageReady) web.evaluateJavascript(code, null) }

    private fun tellBubble(message: String? = null) =
        js("window.fabricNative && window.fabricNative('bubble', ${BubbleService.running}, ${if (message == null) "null" else JSONObject.quote(message)})")

    /** Methods the page calls as window.FabricNative.* (they run on a WebView thread). */
    private inner class Bridge {
        @JavascriptInterface fun bubbleRunning(): Boolean = BubbleService.running
        @JavascriptInterface fun toggleBubble() = runOnUiThread { if (BubbleService.running) stopBubble() else startBubble() }
        @JavascriptInterface fun setChecks(shade: Boolean, skew: Boolean) = prefs.edit().putBoolean("shade", shade).putBoolean("skew", skew).apply()
        @JavascriptInterface fun takeShared(): String { val s = shared; shared = null; return s ?: "" }
        @JavascriptInterface fun share(imageBase64: String, text: String) = runOnUiThread { shareOut(imageBase64, text) }
    }

    private inner class Client : WebViewClient() {
        private val home = Uri.parse(BuildConfig.APP_URL).host

        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            if (request.url.host == home) return false
            try { startActivity(Intent(Intent.ACTION_VIEW, request.url)) } catch (_: Exception) {}     // other sites open in the browser
            return true
        }

        override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) { pageReady = false; loadFailed = false }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (request.isForMainFrame) { loadFailed = true; offline.visibility = View.VISIBLE }
        }

        override fun onPageFinished(view: WebView, url: String?) {
            if (loadFailed) return
            offline.visibility = View.GONE
            pageReady = true
            if (shared != null) js("window.fabricNative && window.fabricNative('shared')")
        }
    }

    private inner class Chrome : WebChromeClient() {
        // "Upload photo": the system photo picker
        override fun onShowFileChooser(view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
            fileCallback?.onReceiveValue(null)
            fileCallback = callback
            return try {
                @Suppress("DEPRECATION") startActivityForResult(params.createIntent(), REQ_FILE); true
            } catch (e: Exception) { fileCallback = null; false }
        }

        // "Open camera": the page asks for the camera, Android asks the user once
        override fun onPermissionRequest(request: PermissionRequest) = runOnUiThread {
            if (PermissionRequest.RESOURCE_VIDEO_CAPTURE !in request.resources) { request.deny(); return@runOnUiThread }
            if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                request.grant(arrayOf(PermissionRequest.RESOURCE_VIDEO_CAPTURE))
            } else {
                cameraRequest = request
                requestPermissions(arrayOf(Manifest.permission.CAMERA), REQ_CAMERA)
            }
        }
    }

    // ------------------------------------------------------------------ photos shared from other apps
    private fun takeIntent(intent: Intent?) {
        if (intent == null) return
        val uri: Uri? = when (intent.action) {
            Intent.ACTION_SEND -> @Suppress("DEPRECATION") intent.getParcelableExtra(Intent.EXTRA_STREAM)
            Intent.ACTION_VIEW -> intent.data
            else -> null
        }
        if (uri == null) return
        intent.action = null                                 // handle it once (also after a rotation)
        io.execute {
            val b64 = try { readPhoto(uri) } catch (e: Exception) { null }
            if (b64 != null) { shared = b64; js("window.fabricNative && window.fabricNative('shared')") }
        }
    }

    /** Reads a shared photo, upright (EXIF) and at most 3000 px on its longest side, as base64 JPEG. */
    private fun readPhoto(uri: Uri): String? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
        if (bounds.outWidth <= 0) return null
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= 3000) sample *= 2
        var bmp = contentResolver.openInputStream(uri)?.use {
            BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample })
        } ?: return null
        val turn = try {
            contentResolver.openInputStream(uri)?.use {
                when (ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
                    ExifInterface.ORIENTATION_ROTATE_90 -> 90f
                    ExifInterface.ORIENTATION_ROTATE_180 -> 180f
                    ExifInterface.ORIENTATION_ROTATE_270 -> 270f
                    else -> 0f
                }
            } ?: 0f
        } catch (e: Exception) { 0f }
        if (turn != 0f) bmp = Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, Matrix().apply { postRotate(turn) }, true)
        val out = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.JPEG, 93, out)
        return Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
    }

    // ------------------------------------------------------------------ share a result
    private fun shareOut(imageBase64: String, text: String) {
        val send = Intent(Intent.ACTION_SEND).putExtra(Intent.EXTRA_TEXT, text).putExtra(Intent.EXTRA_SUBJECT, "Fabric Inspector report")
        var uri: Uri? = null
        if (imageBase64.isNotEmpty() && Build.VERSION.SDK_INT >= 29) {
            try {                                            // the marked photo goes to Pictures/Fabric Inspector
                val values = ContentValues().apply {
                    put(MediaStore.Images.Media.DISPLAY_NAME, "fabric_check_${System.currentTimeMillis()}.jpg")
                    put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                    put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Fabric Inspector")
                }
                uri = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                uri?.let { u -> contentResolver.openOutputStream(u)?.use { it.write(Base64.decode(imageBase64, Base64.DEFAULT)) } }
            } catch (e: Exception) { uri = null }
        }
        if (uri != null) send.setType("image/jpeg").putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        else send.type = "text/plain"
        try { startActivity(Intent.createChooser(send, getString(R.string.share_title))) } catch (_: Exception) {}
    }

    // ------------------------------------------------------------------ the bubble
    // start: permission 1 (draw over other apps) -> notification permission -> permission 2 (screen capture)
    private fun startBubble() {
        if (!Settings.canDrawOverlays(this)) {
            tellBubble(getString(R.string.step_overlay))
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
            return
        }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIFY)
            return
        }
        askCapture()
    }

    private fun askCapture() {
        val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        @Suppress("DEPRECATION") startActivityForResult(mpm.createScreenCaptureIntent(), REQ_CAPTURE)
    }

    private fun stopBubble() {
        stopService(Intent(this, BubbleService::class.java))
        BubbleService.running = false
        tellBubble()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        when (requestCode) {
            REQ_NOTIFY -> askCapture()                       // the bubble works with or without the notification
            REQ_CAMERA -> {
                val ok = grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
                cameraRequest?.let { if (ok) it.grant(arrayOf(PermissionRequest.RESOURCE_VIDEO_CAPTURE)) else it.deny() }
                cameraRequest = null
            }
        }
    }

    @Deprecated("platform API without AndroidX")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        when (requestCode) {
            REQ_FILE -> {
                fileCallback?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data))
                fileCallback = null
            }
            REQ_CAPTURE -> {
                if (resultCode != RESULT_OK || data == null) { tellBubble(getString(R.string.capture_denied)); return }
                startForegroundService(Intent(this, BubbleService::class.java).setAction(BubbleService.ACTION_START)
                    .putExtra(BubbleService.EXTRA_CODE, resultCode).putExtra(BubbleService.EXTRA_DATA, data))
                BubbleService.running = true
                tellBubble(getString(R.string.running))
            }
        }
    }

    // ------------------------------------------------------------------ first start without internet
    private fun offlineView(): View {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER; setBackgroundColor(Fern.SURFACE)
            setPadding(dp(32f), dp(32f), dp(32f), dp(32f)); visibility = View.GONE; isClickable = true
        }
        col.addView(BubbleView(this), LinearLayout.LayoutParams(dp(84f), dp(84f)))
        col.addView(TextView(this).apply {
            setText(R.string.offline_title); textSize = 20f; setTextColor(Fern.INK); gravity = Gravity.CENTER
            typeface = Typeface.create("sans-serif-condensed", Typeface.BOLD); setPadding(0, dp(18f), 0, dp(6f))
        })
        col.addView(TextView(this).apply { setText(R.string.offline_text); textSize = 15f; setTextColor(Fern.INK2); gravity = Gravity.CENTER; setLineSpacing(0f, 1.15f) })
        col.addView(Button(this).apply {
            setText(R.string.retry); isAllCaps = false; textSize = 16f; setTextColor(Fern.PAPER)
            background = GradientDrawable().apply { setColor(Fern.FERN); cornerRadius = dp(10f).toFloat() }
            setOnClickListener { web.loadUrl(BuildConfig.APP_URL) }
        }, LinearLayout.LayoutParams(dp(180f), dp(50f)).apply { topMargin = dp(22f) })
        return col
    }

    companion object {
        private const val REQ_CAPTURE = 1
        private const val REQ_NOTIFY = 2
        private const val REQ_FILE = 3
        private const val REQ_CAMERA = 4
    }
}
