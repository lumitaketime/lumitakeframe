package com.lumitake.library

import android.content.Context
import java.net.HttpURLConnection
import java.net.URL

/** 記住 Mac 圖庫的網址，並提供連線檢查。 */
object Server {
    private const val PREFS = "lumitake"
    private const val KEY_URL = "server_url"
    const val DEFAULT_PORT = 8765

    fun get(context: Context): String? =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_URL, null)

    fun set(context: Context, url: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY_URL, url).apply()
    }

    /** 「192.168.1.20」「mac.local:8765」「http://…」都整理成 http://主機:埠/ */
    fun normalize(input: String): String? {
        var text = input.trim()
        if (text.isEmpty()) return null
        if (!text.startsWith("http://") && !text.startsWith("https://")) text = "http://$text"
        return try {
            val url = URL(text)
            if (url.host.isNullOrEmpty()) return null
            val port = if (url.port == -1 && url.protocol == "http") DEFAULT_PORT else url.port
            val portPart = if (port == -1) "" else ":$port"
            "${url.protocol}://${url.host}$portPart/"
        } catch (e: Exception) {
            null
        }
    }

    /** 確認對方真的是 Lumitake Library（在背景執行緒呼叫） */
    fun check(baseUrl: String): Boolean = try {
        val conn = URL(baseUrl + "api/auth/status").openConnection() as HttpURLConnection
        conn.connectTimeout = 4000
        conn.readTimeout = 4000
        val body = conn.inputStream.bufferedReader().use { it.readText() }
        conn.disconnect()
        body.contains("\"authenticated\"")
    } catch (e: Exception) {
        false
    }

    fun sameHost(a: String, b: String): Boolean = try {
        val ua = URL(a)
        val ub = URL(b)
        ua.host.equals(ub.host, ignoreCase = true) && ua.port == ub.port
    } catch (e: Exception) {
        false
    }
}
