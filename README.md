# 美股標的觀察板

一個會自己重新讀取數據嘅觀察板網站，用來睇一份固定清單嘅美股 ETF、主要美股、港股同黃金公開報價。

`index.html`頁面會嘗試讀取最新報價。

報價快照由 GitHub Actions 喺平日大約每 5 分鐘更新一次（呢個係 GitHub 定時任務可設定嘅最快間隔，實際執行可能會偏離或漏跑），並寫入 `data` 分支上嘅單一 `quotes.json`（每次覆蓋，避免主分支 git 歷史膨脹）。前端會優先讀呢份檔案。

工作流程已安裝喺 [`.github/workflows/refresh.yml`](.github/workflows/refresh.yml)，倉庫內亦保留相同副本 [`scripts/github-action-refresh.yml`](scripts/github-action-refresh.yml)。可喺 Actions 頁面用 “Refresh quotes” 手動跑一次。

## 數據來源

- 股票、ETF、恒生指數：Yahoo Finance 公開圖表／報價
- XAUUSD 現貨：Gold API（api.gold-api.com）公開指示中間價
- XAUUSD 日線高低、近一年區間同走勢圖：Yahoo Finance COMEX 黃金期貨（GC=F），只作參考
- US.GLD 同 US.GLDM 只係用來對照嘅黃金 ETF，主要黃金列係 XAUUSD

頁面會標明來源名稱，以及來源拉取時間（香港時間）。呢啲，亦唔係交易所官方即時行情。取得失敗嘅代號會顯示「未能取得」或「過時」，唔會填假數字。

短線看法（偏多／偏空／觀望）同支撐、升穿、短線跌穿，每次更新都會按規則重新計算。並非保證，亦唔係投資建議。

## 本機更新快照

```bash
python3 scripts/refresh_quotes.py --out quotes.json
```

如果已有上一份快照，可以加上 `--prev quotes.json`，個別代號失敗時會標成過時並保留上次成功數字。
