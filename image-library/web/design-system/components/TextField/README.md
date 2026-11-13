文字欄位：輸入或編輯一小段特定文字（姓名、電子郵件）。

**使用者提供**：`label`、`placeholder`、`value`／`defaultValue`、`onChange`、`secure`、`type`／`inputMode`、`clearButton`、`error`、`hint`、`leadingIcon`、`width`。

## 規則（HIG Text fields）
- 佔位文字輸入後就消失，所以**另外提供常駐標籤**；佔位文字可用來示範格式（name@example.com）。
- 密碼等敏感資料一律用安全欄位（`secure`）。
- 欄位大小符合預期的文字量；多個欄位垂直堆疊、寬度一致、間距平均。
- 在適當時機驗證：電子郵件在離開欄位時；帳號或密碼在離開前。只能輸入數字的欄位要檢查其他字元。
- 錯誤訊息貼近問題、不責怪人、說清楚怎麼修正：「請輸入完整的電子郵件地址，例如 name@example.com。」——不用「無效的名稱」或「哎呀」。本元件以圖示＋文字呈現錯誤，不只靠紅色。
- iOS：尾端放清除按鈕；顯示對應的鍵盤類型（`inputMode`）。macOS：需要輸入加上清單選擇時用 combo box。
- 大量文字改用多行文字視圖。
