# Vinutes

Vinutes 是 Mac 選單列上的錄音程式。開會時按一下就開始錄音。會議結束後，Vinutes 會把錄音轉成逐字稿，請你平常在用的 AI 整理成正式的會議紀錄，再發成同事可以直接修改、留言的 Google 文件。要寄給與會人員的信也會先準備好，你按下寄出才會寄。

> 目前是早期版本，只能在 Apple 晶片的 Mac 上執行。程式畫面有英文和繁體中文兩種。English: [README.md](README.md)

## 它能做什麼

- **從選單列錄音**：按一下或按 ⌃⌥R 開始，開會途中可以暫停、繼續。開線上會議時，戴著耳機也會錄到對方說的話（需要 macOS 14.2 以上）。
- **在你的 Mac 上轉逐字稿**：語音辨識用 Whisper 在本機執行，錄音不會上傳。
- **開會時顯示即時字幕**：按浮動列上的 CC 按鈕，浮動列下方會即時顯示大家在講的話（需要 macOS 26 以上）。字幕只在你的 Mac 上產生，不會寫進逐字稿。
- **分辨講者**：依聲音分出不同的人。在「人員」分頁替每個聲音選是誰，紀錄和信裡的名字會跟著改，下一場會議 Vinutes 也會認得這個聲音。
- **用你已經在用的 AI 寫紀錄**：Claude Code、Codex 或 Antigravity 都可以。AI 只能讀寫這場會議的資料夾。
- **對照 Google 行事曆**：自動帶入會議名稱、時間、地點和與會人員。
- **發成 Google 文件並保持同步**：同事在文件上改的字和留言會顯示在程式裡。你在程式裡修改時，只會更新改過的段落，同事的留言會留在原本的位置。
- **越用越準**：聽錯的人名改過一次就會存進詞彙表，下一場會議就不會再錯。
- **準備好要寄給與會人員的信**：你按下寄出之前，信不會寄出。
- **用專案和標籤分類會議**：每場會議可以歸到一個專案，也可以加上標籤。在清單上選一個標籤，就只會顯示有這個標籤的會議。
- **整理會議清單**：不用再看的會議可以封存，也可以刪除。刪除後，錄音檔、逐字稿和紀錄會移到垃圾桶，Google 文件會移到雲端硬碟的垃圾桶。可以一次選好幾場，或在會議上按右鍵。

## 支援哪些語言

**程式畫面**預設跟著 Mac 的語言：「系統設定 > 一般 > 語言與地區」排在第一位的語言是中文，畫面就顯示繁體中文，其他語言都顯示英文。選單列的「設定 > 介面語言」可以固定成 English 或繁體中文。選回「自動判斷」，畫面會再跟著 Mac 的語言。環境設定自檢清單的右上角也可以切換。

**會議語言**：Vinutes 會聽每段錄音的開頭、中間和結尾，判斷這場會議用哪一種語言。如果你的會議固定用同一種語言，可以在「設定 > 會議語言」直接選好，Vinutes 就不會再自己判斷。

**會議紀錄**：中文會議會寫成中文紀錄，英文會議寫成英文紀錄。其他語言的會議，紀錄用程式畫面的語言寫，逐字稿保留會議原本的語言。

各語言的辨識品質如下，每種語言用 24 句真人朗讀的錄音實測（2026 年 10 月）：

| | 語言 | 每 100 個字錯幾個（中日韓泰文以字計，其他語言以單字計） |
|---|---|---|
| 辨識準確 | 中文、英文、日文、韓文、西班牙文、法文、德文 | 3～7 |
| 可以用，紀錄要多核對 | 越南文、印尼文、菲律賓文 | 10～11 |
| 可以用，錯字比較多 | 泰文、粵語（當成中文會議處理） | 約 18 |

最常出錯的是人名、數字和日期。用團隊看不懂的語言開的會，寄出前先核對紀錄裡的這三樣。

## 需要準備什麼

- Apple 晶片的 Mac（M1 以後的機型）
- Xcode Command Line Tools（`xcode-select --install`）和 Python 3.10 以上
- 安裝並登入其中一個 AI 命令列工具：[Claude Code](https://docs.claude.com/en/docs/claude-code/setup)、[Codex](https://github.com/openai/codex) 或 [Antigravity](https://antigravity.google/)
- 要用 Google 文件、Gmail 和行事曆的話，需要一個 Google 帳號，並完成一次 Google Cloud 設定。程式會一步一步帶你做，大約 15 分鐘。

## 安裝方法

```bash
git clone https://github.com/miou1107/Vinutes ~/Vinutes
~/Vinutes/recorder/install.sh
```

第一次安裝會下載語音模型（約 1.6 GB），需要等一段時間。裝好之後，選單列會出現麥克風圖示。打開會議視窗，照環境設定自檢清單完成一次設定。

## 在 Claude Code 和其他 AI 工具裡查會議

Vinutes 也可以當 MCP 伺服器用。安裝或更新 Vinutes 時，會自動接上你 Mac 上的 AI 工具：Claude Code、Codex、Gemini CLI、Claude 桌面版、Antigravity 和 Cursor。後面三個要重新開一次才看得到會議。之後才裝的 AI 工具，執行這一行就能接上：

```bash
~/.config/vin-meeting-minutes-zh/venv/bin/python ~/Vinutes/scripts/connect_agents.py
```

之後不管在哪個資料夾，問 Claude Code（或其他接上的工具）「上週的專案會議決定了什麼」，Claude 會自己去翻會議記錄和逐字稿，回答時附上是哪一天、哪一場會議。你請它改的時候，它也可以幫講者填名字、在「八、補充資訊」補一段、修改紀錄裡的文字、加標籤或換專案。Google 文件會一起更新，操作紀錄會寫是 Claude Code 改的。刪除會議和寄信，還是只能在 Vinutes 裡按。

## 怎麼更新

GitHub 上有新版時，會議視窗會出現更新按鈕。也可以自己更新：

```bash
git -C ~/Vinutes pull && ~/Vinutes/recorder/install.sh
```

## 資料放在哪裡

設定、Google 登入資料、詞彙表和錄音都放在 `~/.config/vin-meeting-minutes-zh/`，跟 Vinutes 的程式分開放，所以更新或重新安裝 Vinutes 都不會改到這些資料。這個資料夾跟 [vin-meeting-minutes-zh](https://github.com/miou1107/vin-meeting-minutes-zh) skill 共用，Google 只要登入一次，兩邊都能用。

## 這個 repo 裡有什麼

| 路徑 | 內容 |
|---|---|
| `recorder/` | Mac 程式（Swift）和會議視窗（HTML、CSS、JavaScript），以及安裝用的 `install.sh` |
| `scripts/` | Python 程式：轉逐字稿、分辨講者、寫紀錄、同步 Google 文件、Gmail 和行事曆、環境設定自檢 |
| `SKILL.md`、`references/` | 會議紀錄的寫法：`SKILL.md` 管中文紀錄（台灣用語），`references/minutes-guide-en.md` 管英文紀錄；每場會議 AI 會讀對應的那一份 |
| `tests/` | `python3 -m unittest discover -s tests` |

## 手上只有逐字稿？

如果不需要錄音，只想讓 AI 把逐字稿整理成會議紀錄，改用 [vin-meeting-minutes-zh](https://github.com/miou1107/vin-meeting-minutes-zh) skill。
