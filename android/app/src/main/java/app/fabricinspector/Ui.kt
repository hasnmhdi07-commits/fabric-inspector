package app.fabricinspector

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.Shader
import android.view.View

/** Fern theme colours (spec v2, section 6). Severity colours are separate from the brand green. */
object Fern {
    val PAPER = Color.parseColor("#FFFFFF")
    val SURFACE = Color.parseColor("#F6F9F5")
    val INK = Color.parseColor("#15211A")
    val INK2 = Color.parseColor("#4D5C52")
    val LINE = Color.parseColor("#DDE6DA")
    val FERN = Color.parseColor("#2F7D3B")
    val SWATCH = Color.parseColor("#63B96C")
    val CHALK = Color.parseColor("#F0BF45")
    val SEVERITY = mapOf(
        "minor" to Color.parseColor("#A86F12"),
        "major" to Color.parseColor("#CF5A24"),
        "critical" to Color.parseColor("#C23A3A"),
    )
}

fun Context.dp(v: Float): Int = (v * resources.displayMetrics.density + 0.5f).toInt()

/** The floating bubble: a pick glass (thread-counting lens, 5 mm reticle, chalk-yellow handle) on fern green.
 *  The dot on its rim shows the last verdict. */
class BubbleView(context: Context) : View(context) {
    /** null = no dot (nothing found / no check yet) */
    var badge: Int? = null
        set(value) { field = value; invalidate() }

    private val p = Paint(Paint.ANTI_ALIAS_FLAG)

    override fun onDraw(c: Canvas) {
        val s = width.toFloat()
        val pad = s * 0.06f
        val r = s / 2f - pad
        val cx = s / 2f
        val cy = s / 2f
        // soft shadow
        p.shader = null; p.style = Paint.Style.FILL; p.color = Color.argb(50, 30, 80, 40)
        c.drawCircle(cx, cy + pad * 0.6f, r, p)
        // fern disc (reset the paint to opaque first: the shadow above left it at 20 % alpha)
        p.color = Color.WHITE
        p.shader = RadialGradient(cx - r * 0.3f, cy - r * 0.4f, r * 1.5f,
            intArrayOf(Color.parseColor("#86CF8D"), Fern.SWATCH, Color.parseColor("#3F8F48")),
            floatArrayOf(0f, 0.45f, 1f), Shader.TileMode.CLAMP)
        c.drawCircle(cx, cy, r, p)
        p.shader = null
        p.style = Paint.Style.STROKE; p.strokeWidth = s * 0.035f; p.color = Color.argb(180, 255, 255, 255)
        c.drawCircle(cx, cy, r - s * 0.02f, p)
        // pick glass, drawn in a 54-unit box like the design
        val k = (2 * r) / 54f
        fun x(v: Float) = cx - r + v * k
        fun y(v: Float) = cy - r + v * k
        p.style = Paint.Style.FILL; p.color = Color.argb(26, 255, 255, 255)
        c.drawCircle(x(27f), y(27f), 17f * k, p)
        p.style = Paint.Style.STROKE; p.color = Color.WHITE; p.strokeWidth = 2.2f * k
        c.drawCircle(x(27f), y(27f), 17f * k, p)
        p.color = Color.argb(140, 255, 255, 255); p.strokeWidth = 1f * k
        c.drawLine(x(14f), y(27f), x(40f), y(27f), p); c.drawLine(x(27f), y(14f), x(27f), y(40f), p)
        p.color = Color.WHITE; p.strokeWidth = 1.1f * k
        for (i in 0..5) c.drawLine(x(17f + i * 4), y(27f), x(17f + i * 4), y(27f - if (i % 5 == 0) 5f else 3f), p)
        p.color = Fern.CHALK; p.strokeWidth = 4f * k; p.strokeCap = Paint.Cap.ROUND
        c.drawLine(x(39.5f), y(39.5f), x(45.5f), y(45.5f), p)
        p.strokeCap = Paint.Cap.BUTT
        // verdict dot
        badge?.let {
            val br = s * 0.13f
            val bx = cx + r * 0.68f
            val by = cy - r * 0.68f
            p.style = Paint.Style.FILL; p.color = Color.WHITE; c.drawCircle(bx, by, br + s * 0.03f, p)
            p.color = it; c.drawCircle(bx, by, br, p)
        }
    }
}
