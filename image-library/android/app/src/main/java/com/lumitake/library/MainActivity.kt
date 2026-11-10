package com.lumitake.library

import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.Intent
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.URLUtil
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import java.net.URLDecoder

/**
 * 主畫面：全螢幕的 WebView，顯示 Mac 上 Re'memor 的介面。
 * 介面本身來自 Mac，所以 Mac 更新後手機自動是新版，App 很少需要更新。
 */
class MainActivity : AppCompatActivity() {
    companion object {
        const val ACTION_CHANGE_SERVER = "com.lumitake.library.CHANGE_SERVER"
    }

    private lateinit var root: FrameLayout
    private lateinit var web: WebView
    private lateinit var errorView: View
    private lateinit var errorText: TextView
    private var serverUrl: String = ""
    private var fullscreenView: View? = null
    private var fullscreenCallback: WebChromeClient.CustomViewCallback? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val saved = Server.get(this)
        if (saved == null || intent?.action == ACTION_CHANGE_SERVER) {
            startActivity(Intent(this, ConnectActivity::class.java))
            finish()
            return
        }
        serverUrl = saved

        root = FrameLayout(this)
        web = WebView(this)
        root.addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        errorView = buildErrorView()
        root.addView(errorView, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        errorView.visibility = View.GONE
        // Android 15 起畫面預設延伸到系統列底下，這裡把內容留在安全區域內
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            if (fullscreenView == null) v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        setContentView(root)

        CookieManager.getInstance().setAcceptCookie(true)
        with(web.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = false
            mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
            userAgentString = "$userAgentString LumitakeAndroid/0.3"
        }
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                if (Server.sameHost(url, serverUrl)) return false
                // 外部連結（地圖、說明網頁）交給瀏覽器
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, request.url))
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "無法開啟連結", Toast.LENGTH_SHORT).show()
                }
                return true
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) showError("連不到 Mac 上的圖庫（${error.description}）")
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowCustomView(view: View, callback: WebChromeClient.CustomViewCallback) {
                enterFullscreen(view, callback)
            }

            override fun onHideCustomView() {
                exitFullscreen()
            }
        }
        web.setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
            download(url, userAgent, contentDisposition, mimeType)
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                when {
                    fullscreenView != null -> exitFullscreen()
                    errorView.visibility == View.VISIBLE -> finish()
                    web.canGoBack() -> web.goBack()
                    else -> finish()
                }
            }
        })

        if (savedInstanceState != null) web.restoreState(savedInstanceState) else web.loadUrl(serverUrl)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.action == ACTION_CHANGE_SERVER) {
            startActivity(Intent(this, ConnectActivity::class.java))
            finish()
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        if (::web.isInitialized) web.saveState(outState)
    }

    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush()
    }

    private fun dp(v: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun buildErrorView(): View {
        val muted = ContextCompat.getColor(this, R.color.muted)
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(32), dp(32), dp(32), dp(32))
            setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.bg))
        }
        column.addView(TextView(this).apply {
            text = "無法連線到 Mac"
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
        })
        errorText = TextView(this).apply {
            setTextColor(muted)
            gravity = Gravity.CENTER
            setPadding(0, dp(10), 0, dp(24))
        }
        column.addView(errorText)
        column.addView(Button(this).apply {
            text = "重試"
            setOnClickListener {
                errorView.visibility = View.GONE
                web.loadUrl(serverUrl)
            }
        })
        column.addView(Button(this).apply {
            text = "更換連線"
            setOnClickListener {
                startActivity(Intent(this@MainActivity, ConnectActivity::class.java))
                finish()
            }
        })
        return column
    }

    private fun showError(reason: String) {
        errorText.text = "$reason\n\n請確認：\n• Mac 已開機且 Re'memor 正在執行\n• 已在 Mac 的設定開啟「手機與平板」連線\n• 手機和 Mac 連同一個 Wi-Fi\n\n目前連線：$serverUrl"
        errorView.visibility = View.VISIBLE
    }

    /** 「存到這台裝置」：用系統下載管理員存到 圖片/Rememor，帶上登入 cookie。 */
    private fun download(url: String, userAgent: String, contentDisposition: String?, mimeType: String?) {
        try {
            val name = fileName(contentDisposition) ?: URLUtil.guessFileName(url, contentDisposition, mimeType)
            val request = DownloadManager.Request(Uri.parse(url)).apply {
                CookieManager.getInstance().getCookie(url)?.let { addRequestHeader("Cookie", it) }
                addRequestHeader("User-Agent", userAgent)
                if (!mimeType.isNullOrBlank()) setMimeType(mimeType)
                setTitle(name)
                setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                setDestinationInExternalPublicDir(Environment.DIRECTORY_PICTURES, "Rememor/$name")
            }
            (getSystemService(DOWNLOAD_SERVICE) as DownloadManager).enqueue(request)
            Toast.makeText(this, "正在存到「圖片/Rememor」：$name", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, "無法下載：${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    /** 支援 filename*=utf-8''中文檔名.jpg */
    private fun fileName(disposition: String?): String? {
        if (disposition == null) return null
        Regex("filename\\*=(?:UTF-8|utf-8)''([^;]+)").find(disposition)?.let {
            return URLDecoder.decode(it.groupValues[1].trim(), "UTF-8")
        }
        Regex("filename=\"?([^\";]+)\"?").find(disposition)?.let { return it.groupValues[1].trim() }
        return null
    }

    private fun enterFullscreen(view: View, callback: WebChromeClient.CustomViewCallback) {
        if (fullscreenView != null) {
            callback.onCustomViewHidden()
            return
        }
        fullscreenView = view
        fullscreenCallback = callback
        root.setPadding(0, 0, 0, 0)
        root.addView(view, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        web.visibility = View.GONE
        WindowCompat.getInsetsController(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    private fun exitFullscreen() {
        val view = fullscreenView ?: return
        root.removeView(view)
        fullscreenView = null
        web.visibility = View.VISIBLE
        fullscreenCallback?.onCustomViewHidden()
        fullscreenCallback = null
        WindowCompat.getInsetsController(window, window.decorView).show(WindowInsetsCompat.Type.systemBars())
        ViewCompat.requestApplyInsets(root)
    }
}
