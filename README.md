# 美股標的觀察板

一個會自己重新讀取數據嘅觀察板網站，用來睇一份固定清單嘅美股 ETF、主要美股、港股同黃金公開報價。

## 點樣打開

網站由 GitHub Pages 託管：

[https://rilakkuma-kuki.github.io/predict/](https://rilakkuma-kuki.github.io/predict/)

倉庫： [https://github.com/RILAKKUMA-KUKI/predict](https://github.com/RILAKKUMA-KUKI/predict)

如果 Pages 仲未發布完成，可以喺呢個倉庫打開 `index.html`（需要本機或任何靜態網站服務），頁面一樣會嘗試讀取最新報價。

## 開啟中嘅頁面會自己更新

你唔使撳 F5，亦唔使等新連結。頁面大約每 45 秒自動讀取一次 `quotes.json`，數字會喺原位轉新。切返呢個分頁時亦會即刻再讀一次。

報價快照由 GitHub Actions 喺平日大約每 5 分鐘更新一次（呢個係 GitHub 定時任務可設定嘅最快間隔，實際執行可能會偏離或漏跑），並寫入 `data` 分支上嘅單一 `quotes.json`（每次覆蓋，避免主分支 git 歷史膨脹）。前端會優先讀呢份檔案。

工作流程已安裝喺 [`.github/workflows/refresh.yml`](.github/workflows/refresh.yml)，倉庫內亦保留相同副本 [`scripts/github-action-refresh.yml`](scripts/github-action-refresh.yml)。可喺 Actions 頁面用 “Refresh quotes” 手動跑一次。

## 數據來源

- 股票、ETF、恒生指數：Yahoo Finance 公開圖表／報價
- XAUUSD 現貨：Gold API（api.gold-api.com）公開指示中間價
- XAUUSD 日線高低、近一年區間同走勢圖：Yahoo Finance COMEX 黃金期貨（GC=F），只作參考
- US.GLD 同 US.GLDM 只係用來對照嘅黃金 ETF，主要黃金列係 XAUUSD

頁面會標明來源名稱，以及來源拉取時間（香港時間）。呢啲**唔係富途官方報價**，亦唔係交易所官方即時行情。取得失敗嘅代號會顯示「未能取得」或「過時」，唔會填假數字。

短線看法（偏多／偏空／觀望）同支撐、升穿、短線跌穿，每次更新都會按規則重新計算；短線跌穿只用今趟或近期低位，唔會把近一年低位當作跌穿目標。並非保證，亦唔係投資建議。

## 唔會使用富途登入授權

呢個倉庫、GitHub Actions 同網站都**唔會**讀取、儲存或使用富途（或其他券商）嘅登入授權、token 或帳戶資料。請唔好把任何密鑰、token 或個人證件資料提交到呢個倉庫。

## 將倉庫轉返私人

免費 GitHub 帳戶把倉庫轉成私人之後，免費 GitHub Pages 通常會停止公開網站。程式碼仍然喺倉庫度，但 [https://rilakkuma-kuki.github.io/predict/](https://rilakkuma-kuki.github.io/predict/) 可能會一齊離線。如果之後要繼續用免費 Pages，就要保持倉庫公開，或者改用付費方案／其他託管。

請唔好隨便把密鑰放進倉庫再轉私人；轉私人亦唔等於可以公開保存過嘅密鑰已經消失。

## 本機更新快照

```bash
python3 scripts/refresh_quotes.py --out quotes.json
```

如果已有上一份快照，可以加上 `--prev quotes.json`，個別代號失敗時會標成過時並保留上次成功數字。
