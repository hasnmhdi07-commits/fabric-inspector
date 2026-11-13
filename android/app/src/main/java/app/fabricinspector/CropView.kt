package app.fabricinspector

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Typeface
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/** Dimmed full-screen layer with a selection rectangle: drag a corner to resize, drag inside to move. */
class CropView(context: Context) : View(context) {
    val rect = RectF()
    private val dim = Paint().apply { color = Color.argb(140, 10, 12, 30) }
    private val border = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; style = Paint.Style.STROKE; strokeWidth = context.dp(2f).toFloat() }
    private val handle = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textSize = context.dp(12f).toFloat(); typeface = Typeface.MONOSPACE }
    private val path = Path()
    private val hs = context.dp(7f).toFloat()            // half size of a corner handle
    private val grab = context.dp(30f).toFloat()         // how close a touch must be to take a corner
    private val minSize = context.dp(56f).toFloat()
    private var mode = 0                                 // 0 none, 1-4 corners (TL, TR, BL, BR), 5 move
    private var lastX = 0f
    private var lastY = 0f

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        rect.set(w * 0.12f, h * 0.28f, w * 0.88f, h * 0.62f)   // start like the design mockup
    }

    override fun onDraw(c: Canvas) {
        path.reset(); path.fillType = Path.FillType.EVEN_ODD
        path.addRect(0f, 0f, width.toFloat(), height.toFloat(), Path.Direction.CW)
        path.addRect(rect, Path.Direction.CW)
        c.drawPath(path, dim)
        c.drawRect(rect, border)
        for ((x, y) in listOf(rect.left to rect.top, rect.right to rect.top, rect.left to rect.bottom, rect.right to rect.bottom))
            c.drawRoundRect(x - hs, y - hs, x + hs, y + hs, hs * 0.4f, hs * 0.4f, handle)
        c.drawText("${rect.width().toInt()} × ${rect.height().toInt()} px", rect.left, rect.bottom + label.textSize * 1.6f, label)
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                lastX = e.x; lastY = e.y
                val corners = listOf(rect.left to rect.top, rect.right to rect.top, rect.left to rect.bottom, rect.right to rect.bottom)
                val i = corners.indexOfFirst { abs(it.first - e.x) < grab && abs(it.second - e.y) < grab }
                mode = if (i >= 0) i + 1 else if (rect.contains(e.x, e.y)) 5 else 0
                return mode != 0
            }
            MotionEvent.ACTION_MOVE -> {
                val x = min(max(e.x, 0f), width.toFloat())
                val y = min(max(e.y, 0f), height.toFloat())
                when (mode) {
                    1 -> { rect.left = min(x, rect.right - minSize); rect.top = min(y, rect.bottom - minSize) }
                    2 -> { rect.right = max(x, rect.left + minSize); rect.top = min(y, rect.bottom - minSize) }
                    3 -> { rect.left = min(x, rect.right - minSize); rect.bottom = max(y, rect.top + minSize) }
                    4 -> { rect.right = max(x, rect.left + minSize); rect.bottom = max(y, rect.top + minSize) }
                    5 -> {
                        val dx = min(max(e.x - lastX, -rect.left), width - rect.right)
                        val dy = min(max(e.y - lastY, -rect.top), height - rect.bottom)
                        rect.offset(dx, dy); lastX = e.x; lastY = e.y
                    }
                }
                invalidate()
                return true
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> { mode = 0; return true }
        }
        return false
    }
}
