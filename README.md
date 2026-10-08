# PDF → Markdown with Docling

在本機把單份 PDF 轉成 Markdown、結構化 JSON 和圖片，保留來源頁碼、檔案雜湊與轉換紀錄。這個工具包裝 Docling，讓閱讀材料可以回查原文，並準備匯入 Obsidian 的圖片素材。

## 功能

- 指定原始頁碼、整頁 OCR、可選公式辨識；CPU 本機處理。
- 同來源與設定的完整產物可重用；已變動或失敗的輸出不會被覆蓋。
- Markdown 圖片連結改為相對路徑，檢查圖片是否存在於輸出目錄。
- `conversion.json` 記錄來源 SHA-256、Docling／wrapper 版本、設定、原頁碼與每個輸出檔的 SHA-256。
- [Obsidian 素材整理](prepare_obsidian.py)依圖說和頁碼命名圖片，產生待審核素材包。

## 安裝

Python 3.12；Windows 是目前驗證環境。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

[requirements.txt](requirements.txt)固定 Docling 2.133.0；[requirements-lock.txt](requirements-lock.txt)保存原 Windows 驗收環境版本。首次執行會下載 Docling／OCR 模型，PDF 內容在本機處理。權重不包含在 repo 中。

## 轉換

```powershell
./Convert-Pdf.ps1 -Pdf 'paper.pdf' -Pages '1-6'
```

或直接呼叫 Python：

```bash
python convert_pdf.py paper.pdf --pages 1-6 --output converted-paper
```

`--full-page-ocr` 強制整頁 OCR；`--enrich-formula` 啟用公式辨識。可設定 `--threads` 和 `--timeout-seconds`。未指定輸出時，放在工具目錄的 `outputs/<來源與設定雜湊>/`。

輸出包含 Markdown、Docling JSON、圖片、`docling.log` 和 `conversion.json`。相同輸入重跑會先檢查雜湊；輸出不完整或被修改時，請保留原產物，換一個空目錄。

## 準備 Obsidian 圖片

```bash
python prepare_obsidian.py --conversion converted-paper --vault my-vault --note my-vault/paper-note.md --stage staged-figures
```

Vault 必須已存在；`--note` 可以指定尚未建立的 Markdown 筆記。程式只產生待審核的圖片、`figure-map.md` 和 `asset-manifest.json`，由使用者核對後再加入筆記。暫存資料夾須位於 vault 之外，已有同名圖片但內容不同時會停止。

## 驗證與限制

2026-10-09 公開版以自製單頁 PDF 實跑：1 張圖片、1 個表格及 6 格文字／數字吻合；來源 PDF 雜湊不變，相同產物可重用，改動過的輸出會被拒絕覆蓋。Obsidian 素材包成功保留圖號和第 1 頁來源，筆記庫沒有被寫入。這是有限的功能驗收。

轉換成功狀態固定標為 `converted_unverified`。表格、公式、圖說和閱讀順序仍須對照原頁；重要數字不應只從 OCR 結果引用。舊驗收已觀察到密集表格合列與公式下標遺失；中文掃描、模糊掃描和 Linux 執行尚未完成驗證。

此公開版將原 DEV 專用輸出改為 repo 內的 `outputs/`，並新增明確的 `--vault` 參數；原始工作區設定及研究來源文件沒有一併發布。

下一步是以更多具明確來源的掃描樣本檢查 OCR 邊界。這個工具不會自動把擷取稿當成已校訂的閱讀筆記。

## 來源與使用範圍

轉換引擎：[Docling](https://github.com/docling-project/docling)；[官方安裝說明](https://docling-project.github.io/docling/getting_started/installation/)。本 repo 的工作是轉換流程、輸出檢查與筆記素材整理，Docling 與 OCR 模型是外部元件。

原創程式碼目前供公開檢視，未授予額外使用授權；詳見 [NOTICE](NOTICE.md)。
