# 千倍股評估在 Claude Code session 裡執行，不呼叫 Claude API

不申請 Anthropic API key、不在後端呼叫 Claude API，評估改在站長開著的 Claude Code session 裡做：由 session 裡的 Claude 讀後端準備好的數據、產生評估，經後端驗證後存進 DB，儀表板只負責顯示已存的結果。這樣不用另外付 API 費用（用的是既有的 Claude 訂閱），也不用在伺服器上保管一把 API key。代價是儀表板本身無法觸發評估：沒開 session 就不能評估新的股票，也沒有辦法開放給其他使用者。
