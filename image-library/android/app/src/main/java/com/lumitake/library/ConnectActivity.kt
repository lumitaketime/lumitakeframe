package com.lumitake.library

import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.util.TypedValue
import android.view.Gravity
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlin.concurrent.thread

/** 配對畫面：掃描 Mac 設定頁的 QR code，或手動輸入網址。 */
class ConnectActivity : AppCompatActivity() {
    private lateinit var input: EditText
    private lateinit var status: TextView
    private lateinit var progress: ProgressBar
    private lateinit var connectButton: Button

    private val scanner = registerForActivityResult(ScanContract()) { result ->
        val text = result.contents ?: return@registerForActivityResult
        input.setText(text)
        connect(text, force = false)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val dp = { v: Int -> TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt() }
        val textColor = ContextCompat.getColor(this, R.color.text)
        val muted = ContextCompat.getColor(this, R.color.muted)

        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(28), dp(48), dp(28), dp(28))
            gravity = Gravity.CENTER_HORIZONTAL
        }
        column.addView(android.widget.ImageView(this).apply {
            setImageResource(R.mipmap.ic_launcher)
            layoutParams = LinearLayout.LayoutParams(dp(88), dp(88)).apply { bottomMargin = dp(16) }
        })
        column.addView(TextView(this).apply {
            text = "連線到 Mac 上的圖庫"
            setTextColor(textColor)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
        })
        column.addView(TextView(this).apply {
            text = "在 Mac 的 Re'memor 打開「設定 → 手機與平板」，開啟連線後掃描畫面上的 QR code。手機需要和 Mac 連同一個 Wi-Fi。"
            setTextColor(muted)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            gravity = Gravity.CENTER
            setPadding(0, dp(8), 0, dp(24))
        })
        column.addView(Button(this).apply {
            text = "掃描 QR code"
            setOnClickListener {
                scanner.launch(ScanOptions().apply {
                    setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                    setPrompt("掃描 Mac 設定頁上的 QR code")
                    setBeepEnabled(false)
                    setOrientationLocked(false)
                })
            }
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        column.addView(TextView(this).apply {
            text = "或手動輸入網址"
            setTextColor(muted)
            setPadding(0, dp(24), 0, dp(6))
        })
        input = EditText(this).apply {
            hint = "例如 192.168.1.20:8766"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            imeOptions = EditorInfo.IME_ACTION_GO
            setSingleLine()
            setText(Server.get(this@ConnectActivity) ?: "")
            setOnEditorActionListener { _, _, _ -> connect(text.toString(), force = false); true }
        }
        column.addView(input, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        connectButton = Button(this).apply {
            text = "連線"
            setOnClickListener { connect(input.text.toString(), force = false) }
        }
        column.addView(connectButton, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        progress = ProgressBar(this).apply { visibility = android.view.View.GONE }
        column.addView(progress)
        status = TextView(this).apply {
            setTextColor(muted)
            gravity = Gravity.CENTER
            setPadding(0, dp(12), 0, 0)
        }
        column.addView(status)

        val root = ScrollView(this).apply { addView(column) }
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        setContentView(root)
    }

    private fun connect(raw: String, force: Boolean) {
        val url = Server.normalize(raw)
        if (url == null) {
            status.text = "網址格式不正確"
            return
        }
        if (force) {
            open(url)
            return
        }
        status.text = "連線中…"
        progress.visibility = android.view.View.VISIBLE
        connectButton.isEnabled = false
        thread {
            val ok = Server.check(url)
            runOnUiThread {
                progress.visibility = android.view.View.GONE
                connectButton.isEnabled = true
                if (ok) {
                    open(url)
                } else {
                    status.text = "連不到 $url\n請確認 Mac 開機、Re'memor 正在執行、已開啟手機連線，並和手機在同一個 Wi-Fi。"
                    connectButton.text = "仍要使用這個網址"
                    connectButton.setOnClickListener { connect(input.text.toString(), force = true) }
                }
            }
        }
    }

    private fun open(url: String) {
        Server.set(this, url)
        startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP))
        finish()
    }
}
