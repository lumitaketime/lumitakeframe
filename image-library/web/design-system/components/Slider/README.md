滑桿：在最小值與最大值之間調整一個值，軌道從最小值填到圓鈕。

**使用者提供**：`value`／`defaultValue`、`min`、`max`、`step`、`onChange`、`ticks`（macOS 刻度數）、`minIcon`／`maxIcon`、`label`、`valueLabel`（給螢幕閱讀器的值描述）。

- 最小值在前緣、最大值在後緣（直式則下小上大）。
- 範圍很大時搭配文字欄位與 Stepper。
- **iOS／iPadOS 不要用滑桿調音量**，改用系統音量視圖。
- macOS：刻度幫助對準值；即時回饋；標籤用句子式大小寫並以冒號結尾；通常只標最小與最大；可在滑過時用工具提示顯示目前值。重複的值（角度）用圓形滑桿。
- 按住時圓鈕轉為 Liquid Glass。tvOS 不支援滑桿。
