// The menu-bar recorder for vin-meeting-minutes-zh (macOS 13+, built by recorder/install.sh).
//
// Record from the microphone icon, the floating bar or the shortcuts ⌃⌥R (start / stop) and ⌃⌥P (pause /
// resume). When a recording stops, the app starts scripts/auto_minutes.py in the background: transcript,
// minutes, Google Doc. When the job is done the app posts a notification.
//
// The meeting window (ManagerWindow) is a local page, recorder/app/, copied into the app by install.sh: every
// meeting on the left, one meeting on the right with the minutes from the Google Doc (colleagues' edits and
// comments marked), editable in place. The page asks this app for everything; the app runs
// scripts/minutes_app.py and scripts/auto_minutes.py --send. Nothing is sent until the user presses 寄出 in the
// mail sheet, which shows the recipients, the subject, the text and the attachment that will go out.
//
// Files: $MINUTES_HOME (default ~/.config/vin-meeting-minutes-zh)/recorder.json holds the python and
// Vinutes folder paths written by install.sh; every recording is a job folder under $MINUTES_HOME/recordings/.
// A recording is written as CAF from its first second, so a crash or a power cut still leaves a usable file;
// the next launch finishes it (recoverOrphans).

import AppKit
import AVFoundation
import UniformTypeIdentifiers
import Carbon.HIToolbox
import ServiceManagement
import UserNotifications
import WebKit

let configDir: URL = {
    let env = ProcessInfo.processInfo.environment["MINUTES_HOME"] ?? ""
    if !env.isEmpty { return URL(fileURLWithPath: (env as NSString).expandingTildeInPath) }
    return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".config/vin-meeting-minutes-zh")
}()
let recordingsDir = configDir.appendingPathComponent("recordings")

func readJSON(_ url: URL) -> [String: Any] {
    guard let data = try? Data(contentsOf: url),
          let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return [:] }
    return obj
}

func writeJSON(_ obj: [String: Any], _ url: URL) {
    if let data = try? JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted]) {
        try? data.write(to: url, options: .atomic)
    }
}

// MARK: language

/// settings.json, shared with the scripts and the meeting window: "language" ("auto" | "en" | "zh-TW") is the app's own
/// language, "meeting_language" ("auto" | "en" | "zh") the language the next recording is transcribed in.
let settingsFile = configDir.appendingPathComponent("settings.json")

/// Writes one key of settings.json, keeping every other key and the file's permissions.
func saveSetting(_ key: String, _ value: String) {
    var obj = readJSON(settingsFile)
    obj[key] = value
    let mode = (try? FileManager.default.attributesOfItem(atPath: settingsFile.path))?[.posixPermissions]
    try? FileManager.default.createDirectory(at: configDir, withIntermediateDirectories: true)
    if let data = try? JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .withoutEscapingSlashes]) {
        try? data.write(to: settingsFile, options: .atomic)
    }
    if let mode { try? FileManager.default.setAttributes([.posixPermissions: mode], ofItemAtPath: settingsFile.path) }
}

/// The language the user picked, or nil while they have not picked one.
func pickedLanguage() -> String? {
    let v = (readJSON(settingsFile)["language"] as? String ?? "").lowercased()
    if v.hasPrefix("zh") { return "zh-TW" }
    if v.hasPrefix("en") { return "en" }
    return nil
}

/// The app's language: the one picked, else the Mac's (Chinese of any kind -> zh-TW, anything else -> en).
func uiLanguage() -> String {
    pickedLanguage() ?? ((Locale.preferredLanguages.first ?? "").lowercased().hasPrefix("zh") ? "zh-TW" : "en")
}

func meetingLanguage() -> String {
    let v = readJSON(settingsFile)["meeting_language"] as? String ?? "auto"
    return ["auto", "en", "zh"].contains(v) ? v : "auto"
}

/// Every word the app shows, in both languages, with the same keys and the same %@ / %d blanks.
let STRINGS: [String: [String: String]] = [
    "en": [
        "menu.start": "Start Recording",
        "menu.pause": "Pause Recording",
        "menu.stop": "Stop Recording",
        "menu.recent": "Recent Meetings",
        "menu.none": "No recordings yet",
        "menu.folder": "Open Recordings Folder",
        "menu.settings": "Settings",
        "menu.setup": "Setup Checklist",
        "menu.login": "Open at Login",
        "menu.language": "App Language",
        "menu.languageAuto": "Same as Mac",
        "menu.meetingLanguage": "Meeting Language",
        "menu.meetingAuto": "Detect Automatically",
        "panel.all": "All Meetings",
        "panel.usage": "Usage",
        "panel.quit": "Quit",
        "panel.stopHint": "Click to stop recording",
        "panel.resume": "Resume",
        "panel.update": "Update to %@",
        "panel.aiTitle": "Note: the AI isn't set up",
        "panel.aiText": "Set up the AI first to have the minutes written automatically",
        "panel.aiSetup": "Set Up",
        "update.failTitle": "Vinutes didn't update",
        "app.hide": "Hide %@",
        "app.quit": "Quit %@",
        "edit": "Edit",
        "edit.undo": "Undo",
        "edit.redo": "Redo",
        "edit.cut": "Cut",
        "edit.copy": "Copy",
        "edit.paste": "Paste",
        "edit.selectAll": "Select All",
        "window": "Window",
        "window.minimize": "Minimize",
        "window.close": "Close Window",
        "state.transcribing": "Transcribing",
        "state.writing": "Writing up",
        "state.failed": "Not finished",
        "state.waiting": "Waiting",
        "job.title": "Meeting minutes",
        "tip.recording": "Recording",
        "tip.paused": "Paused",
        "bar.pause": "Pause (⌃⌥P)",
        "bar.resume": "Resume (⌃⌥P)",
        "bar.stop": "Stop recording (⌃⌥R)",
        "bar.captions": "Live captions on your screen only; not saved in the transcript",
        "bar.captionLanguage": "Caption language",
        "caption.downloading": "Downloading %@ captions, the first time only…",
        "caption.unsupported": "No live captions for this language",
        "caption.failed": "Captions stopped. Press CC twice to try again.",
        "caption.listening": "Listening…",
        "quit.title": "You're still recording",
        "btn.keepRecording": "Keep Recording",
        "btn.stopAndWrite": "Stop and Write Up",
        "mic.title": "No microphone access",
        "mic.text": "Open System Settings > Privacy & Security > Microphone and turn on Vinutes.",
        "btn.openSettings": "Open System Settings",
        "btn.close": "Close",
        "btn.ok": "OK",
        "btn.cancel": "Cancel",
        "start.failTitle": "Can't start recording",
        "start.failText": "Another app may be using the microphone. (%@)",
        "status.preparing": "Getting ready to transcribe",
        "status.stopped": "Writing up stopped before it finished.",
        "noApp.title": "Can't find Vinutes' files",
        "noApp.text": "Run recorder/install.sh again.",
        "run.failTitle": "Can't start writing up",
        "notify.done": "Minutes ready",
        "notify.failed": "Not finished",
        "login.failTitle": "Can't change Open at Login",
        "login.failText": "Add Vinutes yourself in System Settings > General > Login Items. (%@)",
        "window.missing": "Can't find the window's files. Run recorder/install.sh again.",
        "err.quitting": "Vinutes is quitting.",
        "err.tryAgain": "That didn't finish. Please try again.",
        "err.noJob": "Can't find this recording.",
        "err.saveEdits": "Couldn't save your changes.",
        "err.noSetupItem": "There's no such setup item.",
        "err.noAI": "Vinutes doesn't work with that AI.",
        "err.badURL": "This link can't be opened from here.",
        "err.nothingToAttach": "There's no file, link or picture to add.",
        "err.speakerName": "Enter a name, up to 30 characters.",
        "err.alreadyDone": "This meeting has already been written up.",
        "err.updateWhileRecording": "You're recording. You can update when the recording ends.",
        "err.unknownCommand": "Vinutes doesn't recognize that action.",
        "err.pasteFailed": "The pasted picture could not be saved. You can choose it with the picture button instead.",
        "err.badFormat": "Vinutes doesn't recognize that attachment format.",
        "err.noRecipient": "Add at least one recipient.",
        "err.emptyMail": "The subject and the message both need text.",
        "err.saveMail": "Couldn't save the message.",
        "err.previewFailed": "The email preview failed. Nothing was sent.",
        "err.mailChanged": "The email about to go out doesn't match what's on screen. Nothing was sent. Press Send again.",
        "err.notSent": "The email wasn't sent.",
        "err.noAudio": "Can't find the recording for this meeting.",
        "format.gdoc": "Google Doc link",
        "format.word": "Word file",
        "format.pdf": "PDF file",
        "signin.title": "Sign in to %@",
        "signin.done": "When you're signed in, close this window and go back to Vinutes.",
        "panel.client": "Choose the client file you downloaded from Google Cloud (a JSON file whose name starts with client_secret)",
        "panel.useFile": "Use This File",
        "panel.images": "Choose pictures to insert into the minutes",
        "paste.name": "Pasted picture",
        "panel.files": "Choose files to add to the minutes",
        "panel.add": "Add",
    ],
    "zh-TW": [
        "menu.start": "開始錄音",
        "menu.pause": "暫停",
        "menu.stop": "結束錄音",
        "menu.recent": "最近會議",
        "menu.none": "還沒有錄音",
        "menu.folder": "打開錄音資料夾",
        "menu.settings": "設定",
        "menu.setup": "環境設定自檢",
        "menu.login": "開機時自動開啟",
        "menu.language": "介面語言",
        "menu.languageAuto": "自動判斷",
        "menu.meetingLanguage": "會議語言",
        "menu.meetingAuto": "自動判斷",
        "panel.all": "所有會議",
        "panel.usage": "用量統計",
        "panel.quit": "退出",
        "panel.stopHint": "按一下結束錄音",
        "panel.resume": "繼續",
        "panel.update": "更新到 %@",
        "panel.aiTitle": "注意！ 內容生成模型尚未設定",
        "panel.aiText": "需先完成 AI 設定，才能自動生成會議記錄",
        "panel.aiSetup": "前往設定",
        "update.failTitle": "更新沒有完成",
        "app.hide": "隱藏 %@",
        "app.quit": "結束 %@",
        "edit": "編輯",
        "edit.undo": "還原",
        "edit.redo": "重做",
        "edit.cut": "剪下",
        "edit.copy": "拷貝",
        "edit.paste": "貼上",
        "edit.selectAll": "全選",
        "window": "視窗",
        "window.minimize": "縮到最小",
        "window.close": "關閉視窗",
        "state.transcribing": "轉逐字稿中",
        "state.writing": "整理中",
        "state.failed": "沒有整理完成",
        "state.waiting": "等待整理",
        "job.title": "會議紀錄",
        "tip.recording": "錄音中",
        "tip.paused": "已暫停",
        "bar.pause": "暫停（⌃⌥P）",
        "bar.resume": "繼續（⌃⌥P）",
        "bar.stop": "結束錄音（⌃⌥R）",
        "bar.captions": "即時字幕：只顯示在你的螢幕上，不會寫進逐字稿",
        "bar.captionLanguage": "字幕語言",
        "caption.downloading": "正在下載%@字幕資料，只有第一次要等…",
        "caption.unsupported": "這個語言沒有即時字幕",
        "caption.failed": "字幕停了，按兩下 CC 可以重試",
        "caption.listening": "正在聽…",
        "quit.title": "還在錄音",
        "btn.keepRecording": "繼續錄音",
        "btn.stopAndWrite": "結束錄音並整理",
        "mic.title": "沒有麥克風權限",
        "mic.text": "到「系統設定 > 隱私權與安全性 > 麥克風」，打開「Vinutes」。",
        "btn.openSettings": "打開系統設定",
        "btn.close": "關閉",
        "btn.ok": "好",
        "btn.cancel": "取消",
        "start.failTitle": "沒辦法開始錄音",
        "start.failText": "麥克風可能被其他程式占用。（%@）",
        "status.preparing": "準備轉逐字稿",
        "status.stopped": "整理中斷了。",
        "noApp.title": "找不到 Vinutes 的程式",
        "noApp.text": "請重新執行 recorder/install.sh。",
        "run.failTitle": "沒辦法開始整理",
        "notify.done": "整理好了",
        "notify.failed": "沒有整理完成",
        "login.failTitle": "沒辦法設定開機時自動開啟",
        "login.failText": "到「系統設定 > 一般 > 登入項目」手動加入「Vinutes」。（%@）",
        "window.missing": "找不到視窗的檔案，請重新執行 recorder/install.sh。",
        "err.quitting": "程式正在結束。",
        "err.tryAgain": "沒有完成，請再試一次。",
        "err.noJob": "找不到這場錄音。",
        "err.saveEdits": "沒辦法存下改過的內容。",
        "err.noSetupItem": "沒有這個設定項目。",
        "err.noAI": "沒有這個 AI。",
        "err.badURL": "這個網址不能從這裡打開。",
        "err.nothingToAttach": "沒有要加進去的檔案、連結或圖片。",
        "err.speakerName": "請輸入名字，最多 30 個字。",
        "err.alreadyDone": "這場會議已經整理好了。",
        "err.updateWhileRecording": "正在錄音，錄音結束後才能更新。",
        "err.unknownCommand": "不認得的動作。",
        "err.pasteFailed": "貼上的圖片儲存失敗，可以改用圖片按鈕選擇圖片。",
        "err.badFormat": "不認得的附件格式。",
        "err.noRecipient": "至少要有一位收件人。",
        "err.emptyMail": "主旨和信件內容都要有字。",
        "err.saveMail": "沒辦法存下信件內容。",
        "err.previewFailed": "信件預覽失敗，信沒有寄出。",
        "err.mailChanged": "準備寄出的信跟畫面上的不一樣，信沒有寄出，請再按一次寄出。",
        "err.notSent": "信沒有寄出。",
        "err.noAudio": "找不到這場會議的錄音檔。",
        "format.gdoc": "Google 文件連結",
        "format.word": "Word 檔",
        "format.pdf": "PDF 檔",
        "signin.title": "登入 %@",
        "signin.done": "登入好了就可以關掉這個視窗，回到 Vinutes。",
        "panel.client": "選擇從 Google Cloud 下載的用戶端檔案（client_secret 開頭的 JSON 檔）",
        "panel.useFile": "使用這個檔案",
        "panel.images": "選擇要插入會議記錄的圖片",
        "paste.name": "貼上的圖片",
        "panel.files": "選擇要加進會議記錄的檔案",
        "panel.add": "加入",
    ],
]

/// The words for `key` in the app's language right now (a language switch applies at once), blanks filled in.
func tr(_ key: String, _ args: CVarArg...) -> String {
    let text = STRINGS[uiLanguage()]?[key] ?? STRINGS["en"]?[key] ?? key
    return args.isEmpty ? text : String(format: text, arguments: args)
}

/// A word for a shell script inside single quotes.
func shellQuoted(_ text: String) -> String {
    "'" + text.replacingOccurrences(of: "'", with: "'\\''") + "'"
}

func isoString(_ date: Date) -> String {
    let f = ISO8601DateFormatter()
    f.timeZone = .current
    f.formatOptions = [.withInternetDateTime]
    return f.string(from: date)
}

func clock(_ seconds: TimeInterval) -> String {
    let s = max(0, Int(seconds))
    return s >= 3600 ? String(format: "%d:%02d:%02d", s / 3600, s % 3600 / 60, s % 60)
                     : String(format: "%02d:%02d", s / 60, s % 60)
}

/// The last line a script printed, which is where auto_minutes.py puts its message for the user.
func lastLine(_ text: String) -> String {
    text.split(separator: "\n").map { $0.trimmingCharacters(in: .whitespaces) }.last { !$0.isEmpty } ?? ""
}

func symbol(_ name: String, _ size: CGFloat = 13, _ weight: NSFont.Weight = .regular, tint: NSColor? = nil) -> NSImage? {
    var config = NSImage.SymbolConfiguration(pointSize: size, weight: weight)
    if let tint { config = config.applying(.init(paletteColors: [tint])) }
    return NSImage(systemSymbolName: name, accessibilityDescription: nil)?.withSymbolConfiguration(config)
}

/// The object a script printed on its last line starting with `prefix` (minutes_app.py: "JSON ", the mail: "MAIL ").
func lastObject(_ out: String, prefix: String) -> [String: Any]? {
    guard let line = out.split(separator: "\n").last(where: { $0.hasPrefix(prefix) }),
          let data = line.dropFirst(prefix.count).data(using: .utf8),
          let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
    return obj
}

struct Job {
    let dir: URL
    var name: String { dir.lastPathComponent }
    func json(_ file: String) -> [String: Any] { readJSON(dir.appendingPathComponent(file)) }
    var meta: [String: Any] { json("job.json") }
    var status: [String: Any] { json("status.json") }
    var step: String { status["step"] as? String ?? "" }
    var message: String { status["message"] as? String ?? "" }
    var result: [String: Any] { json("result.json") }
    var title: String {
        let t = result["title"] as? String ?? ""
        return t.isEmpty ? tr("job.title") : t
    }
    var mail: [String: Any]? { result["mail"] as? [String: Any] }
    var sent: Bool { result["sent_at"] != nil }
    var archived: Bool { FileManager.default.fileExists(atPath: dir.appendingPathComponent("封存.json").path) }
    var notifiedMarker: URL { dir.appendingPathComponent(".notified") }
    var finished: Bool { step == "done" || step == "failed" }
    // "20261014-145212" -> "10/14 14:52"
    var label: String {
        let c = Array(name)
        guard c.count >= 13 else { return name }
        return "\(c[4])\(c[5])/\(c[6])\(c[7]) \(c[9])\(c[10]):\(c[11])\(c[12])"
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    var statusItem: NSStatusItem!
    var bar: RecordingBar!
    var panel: MenuPanel!
    var recorder: MeetingCapture?
    var currentJob: URL?
    var aiWarned = false                 // this recording started while the AI could not write its minutes
    var startedAt: Date?
    var pausedAt: Date?
    var pausedTotal: TimeInterval = 0
    var tick: Timer?
    var poll: Timer?
    var awake: NSObjectProtocol?
    var notificationsAllowed = false
    var hotKeys: [EventHotKeyRef?] = []
    var manager: ManagerWindow?
    var jobsSeen = ""

    var recording: Bool { recorder != nil }
    var paused: Bool { pausedAt != nil }
    var elapsed: TimeInterval {
        guard let started = startedAt else { return 0 }
        return (pausedAt ?? Date()).timeIntervalSince(started) - pausedTotal
    }

    // MARK: launch

    func applicationDidFinishLaunching(_ notification: Notification) {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"
        appLog("start: Vinutes \(version), macOS \(ProcessInfo.processInfo.operatingSystemVersionString), " +
               "language \(uiLanguage()), meeting language \(meetingLanguage()), " +
               "microphone \(AVCaptureDevice.authorizationStatus(for: .audio).rawValue)")
        NSApp.mainMenu = mainMenu()
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.target = self                 // the icon opens the panel (MenuPanel.swift), not a menu
        statusItem.button?.action = #selector(statusClicked)
        statusItem.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])
        bar = RecordingBar(owner: self)
        panel = MenuPanel(owner: self)
        try? FileManager.default.createDirectory(at: recordingsDir, withIntermediateDirectories: true)
        registerHotKeys()
        refreshIcon()
        recoverOrphans()

        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            DispatchQueue.main.async {
                self.notificationsAllowed = granted
                self.checkJobs()
            }
        }
        poll = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.checkJobs() }
        // 版本更新 closed the meeting window to install the new app: it opens again here
        let reopen = configDir.appendingPathComponent("open-window-after-update")
        if let at = (try? FileManager.default.attributesOfItem(atPath: reopen.path))?[.modificationDate] as? Date {
            try? FileManager.default.removeItem(at: reopen)
            if Date().timeIntervalSince(at) < 600 { showManager(select: nil) }     // not a failed update days ago
        }
        checkSetupAtStart()
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        appLog("quit asked" + (recording ? " while recording" : ""))
        if recording {
            let alert = NSAlert()
            alert.messageText = tr("quit.title")
            alert.addButton(withTitle: tr("btn.keepRecording"))
            alert.addButton(withTitle: tr("btn.stopAndWrite"))
            NSApp.activate(ignoringOtherApps: true)
            if alert.runModal() == .alertFirstButtonReturn { return .terminateCancel }
            stopRecording()
        }
        guard let manager, manager.window.isVisible else { appLog("quit", wait: true); return .terminateNow }
        manager.finish { appLog("quit after the meeting window saved", wait: true); NSApp.reply(toApplicationShouldTerminate: true) }
        return .terminateLater
    }

    // MARK: shortcuts ⌃⌥R and ⌃⌥P, wherever the user is

    func registerHotKeys() {
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, event, _ in
            var id = EventHotKeyID()
            GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil,
                              MemoryLayout<EventHotKeyID>.size, nil, &id)
            DispatchQueue.main.async { (NSApp.delegate as? AppDelegate)?.hotKey(id.id) }
            return noErr
        }, 1, &spec, nil, nil)
        for (number, key) in [(UInt32(1), kVK_ANSI_R), (UInt32(2), kVK_ANSI_P)] {
            var ref: EventHotKeyRef?
            let id = EventHotKeyID(signature: OSType(0x564D_5243), id: number)       // 'VMRC'
            if RegisterEventHotKey(UInt32(key), UInt32(controlKey | optionKey), id, GetApplicationEventTarget(), 0, &ref) == noErr {
                hotKeys.append(ref)
            } else {
                appLog("shortcut \(number == 1 ? "⌃⌥R" : "⌃⌥P") could not be registered (another app has it?)")
            }
        }
    }

    func hotKey(_ id: UInt32) {
        appLog("shortcut \(id == 1 ? "⌃⌥R" : "⌃⌥P")" + (recording ? " while recording" : ""))
        switch id {
        case 1: recording ? stopRecording() : startRecording()
        case 2: if recording { togglePause() }
        default: break
        }
    }

    // MARK: menu bar

    @objc func statusClicked() {
        guard let button = statusItem.button else { return }
        panel.toggle(from: button)
    }

    /// The panel's Settings: the setup checklist, open at login, the two languages, the recordings folder.
    func settingsMenu() -> NSMenu {
        let sub = NSMenu()
        sub.autoenablesItems = false
        sub.addItem(item(tr("menu.setup"), #selector(openSetup), image: "checklist"))
        let login = item(tr("menu.login"), #selector(toggleLogin))
        login.state = SMAppService.mainApp.status == .enabled ? .on : .off
        sub.addItem(login)
        sub.addItem(.separator())
        sub.addItem(languageItem())
        sub.addItem(meetingLanguageItem())
        sub.addItem(.separator())
        sub.addItem(item(tr("menu.folder"), #selector(openFolder), image: "folder"))
        return sub
    }

    /// 版本更新 from the panel: what the meeting window has typed is saved first, then the same update its corner runs.
    private var updating = false

    func updateApp() {
        guard !recording, !updating else { return }
        updating = true
        let run: () -> Void = { [weak self] in
            // the meeting window may have taken up to 20 s to save: a recording started meanwhile wins
            guard let self else { return }
            guard !self.recording else { self.updating = false; return }
            self.runScript("minutes_app.py", ["update"]) { [weak self] code, out in
                guard code != 0 else { return }           // install.sh quits this app and opens the new one
                self?.updating = false
                let why = lastLine(out)
                self?.showError(tr("update.failTitle"), why.isEmpty || why.hasPrefix("JSON ") ? tr("err.tryAgain") : why)
            }
        }
        if let manager, manager.window.isVisible { manager.finish(run) } else { run() }
    }

    @objc func noop() {}

    /// Settings > App Language: Same as Mac (the default) / English / 繁體中文, the one picked checked.
    func languageItem() -> NSMenuItem {
        let it = item(tr("menu.language"), #selector(noop), image: "globe")
        it.action = nil
        let sub = NSMenu()
        sub.autoenablesItems = false
        let current = pickedLanguage() ?? "auto"
        for (lang, label) in [("auto", tr("menu.languageAuto")), ("", ""), ("en", "English"), ("zh-TW", "繁體中文")] {
            if lang.isEmpty { sub.addItem(.separator()); continue }
            let choice = item(label, #selector(pickLanguage(_:)))
            choice.representedObject = lang
            choice.state = lang == current ? .on : .off
            sub.addItem(choice)
        }
        it.submenu = sub
        return it
    }

    /// Settings > Meeting Language: what the next recording is transcribed in.
    func meetingLanguageItem() -> NSMenuItem {
        let it = item(tr("menu.meetingLanguage"), #selector(noop), image: "waveform")
        it.action = nil
        let sub = NSMenu()
        sub.autoenablesItems = false
        let current = meetingLanguage()
        for (value, label) in [("auto", tr("menu.meetingAuto")), ("", ""), ("en", "English"), ("zh", "中文")] {
            if value.isEmpty { sub.addItem(.separator()); continue }
            let choice = item(label, #selector(pickMeetingLanguage(_:)))
            choice.representedObject = value
            choice.state = value == current ? .on : .off
            sub.addItem(choice)
        }
        it.submenu = sub
        return it
    }

    @objc func pickLanguage(_ sender: NSMenuItem) {
        guard let lang = sender.representedObject as? String else { return }
        setLanguage(lang)
        manager?.languageChanged()
    }

    @objc func pickMeetingLanguage(_ sender: NSMenuItem) {
        guard let value = sender.representedObject as? String, ["auto", "en", "zh"].contains(value) else { return }
        saveSetting("meeting_language", value)
    }

    /// Keeps the language the user picked and redraws the menu bar in it (the status menu is drawn each time it opens).
    func setLanguage(_ lang: String) {
        guard ["auto", "en", "zh-TW"].contains(lang) else { return }
        saveSetting("language", lang)                 // "auto": follow the Mac again
        NSApp.mainMenu = mainMenu()
    }

    /// The menu bar while the meeting window is open (the app is in the Dock then); the shortcuts work in the window.
    func mainMenu() -> NSMenu {
        let main = NSMenu()
        let name = "Vinutes"
        let appMenu = NSMenu(title: name)
        appMenu.addItem(withTitle: tr("app.hide", name), action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: tr("app.quit", name), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        main.addItem(withTitle: "", action: nil, keyEquivalent: "").submenu = appMenu
        let edit = NSMenu(title: tr("edit"))
        edit.addItem(withTitle: tr("edit.undo"), action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: tr("edit.redo"), action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: tr("edit.cut"), action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: tr("edit.copy"), action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: tr("edit.paste"), action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: tr("edit.selectAll"), action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        main.addItem(withTitle: "", action: nil, keyEquivalent: "").submenu = edit
        let windows = NSMenu(title: tr("window"))
        windows.addItem(withTitle: tr("window.minimize"), action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windows.addItem(withTitle: tr("window.close"), action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        main.addItem(withTitle: "", action: nil, keyEquivalent: "").submenu = windows
        NSApp.windowsMenu = windows
        return main
    }

    func item(_ title: String, _ action: Selector, key: String = "", image: String? = nil) -> NSMenuItem {
        let it = NSMenuItem(title: title, action: action, keyEquivalent: key)
        if !key.isEmpty { it.keyEquivalentModifierMask = [.control, .option] }
        if let image { it.image = symbol(image) }
        it.target = self
        return it
    }

    func stateText(_ job: Job) -> String {
        switch job.step {
        case "transcribing": return tr("state.transcribing")
        case "writing": return tr("state.writing")
        case "failed": return tr("state.failed")
        case "done": return job.title
        default: return tr("state.waiting")
        }
    }

    func stateSymbol(_ job: Job) -> String {
        switch job.step {
        case "done": return job.sent ? "checkmark.circle" : (job.mail == nil ? "doc.text" : "envelope")
        case "failed": return "exclamationmark.triangle"
        default: return "hourglass"
        }
    }

    func refreshIcon() {
        guard let button = statusItem.button else { return }
        if recording {
            button.image = symbol(paused ? "pause.circle.fill" : "record.circle.fill", 14)
            button.contentTintColor = paused ? .systemOrange : .systemRed
            button.title = " " + clock(elapsed)
            button.imagePosition = .imageLeading
        } else {
            let busy = recentJobs(limit: 6).contains { !$0.finished }
            button.image = symbol(busy ? "waveform" : "mic", 14)
            button.contentTintColor = nil
            button.title = ""
        }
        button.toolTip = recording ? (paused ? tr("tip.paused") : tr("tip.recording")) : "Vinutes"
        bar.update()
        if panel?.isShown == true { panel.refresh() }
    }

    // MARK: recording

    @objc func startRecording() {
        guard !recording else { return }
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            beginRecording()
        case .notDetermined:
            appLog("asking for the microphone")
            AVCaptureDevice.requestAccess(for: .audio) { ok in
                appLog("microphone " + (ok ? "allowed" : "refused"))
                DispatchQueue.main.async { ok ? self.beginRecording() : self.micDenied() }
            }
        default:
            appLog("recording refused: no microphone permission")
            micDenied()
        }
    }

    func micDenied() {
        let alert = NSAlert()
        alert.messageText = tr("mic.title")
        alert.informativeText = tr("mic.text")
        alert.addButton(withTitle: tr("btn.openSettings"))
        alert.addButton(withTitle: tr("btn.close"))
        NSApp.activate(ignoringOtherApps: true)
        if alert.runModal() == .alertFirstButtonReturn,
           let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone") {
            NSWorkspace.shared.open(url)
        }
    }

    func beginRecording() {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyyMMdd-HHmmss"
        let now = Date()
        let dir = recordingsDir.appendingPathComponent(fmt.string(from: now))
        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            // 16 kHz mono PCM in CAF: what the transcriber wants, and readable even if the app dies mid-meeting;
            // the microphone and the sound the Mac plays (an online meeting's other side) together (Capture.swift)
            let rec = try MeetingCapture(url: dir.appendingPathComponent("錄音.caf"))
            rec.note = { appLog("recording: \($0)") }
            try rec.start()
            writeJSON(["audio": "錄音.caf", "started": isoString(now), "ended": NSNull()], dir.appendingPathComponent("job.json"))
            recorder = rec
            currentJob = dir
            startedAt = now
            pausedAt = nil
            pausedTotal = 0
            awake = ProcessInfo.processInfo.beginActivity(options: [.userInitiated, .idleSystemSleepDisabled], reason: tr("tip.recording"))
            tick = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.refreshIcon() }
            bar.show()
            refreshIcon()
            appLog("recording started: \(dir.lastPathComponent)")
            checkAIForRecording()
        } catch {
            appLog("recording could not start: \(error.localizedDescription)")
            try? FileManager.default.removeItem(at: dir)
            showError(tr("start.failTitle"), tr("start.failText", error.localizedDescription))
        }
    }

    @objc func togglePause() {
        guard let rec = recorder else { return }
        if let since = pausedAt {
            rec.resume()
            pausedTotal += Date().timeIntervalSince(since)
            pausedAt = nil
            appLog("recording resumed")
        } else {
            rec.pause()
            pausedAt = Date()
            appLog("recording paused")
        }
        refreshIcon()
    }

    /// A recording started while the AI is not installed or signed out: the panel opens once with a note and a way
    /// to set it up. The recording goes on either way, and the minutes can be written later (Vin 2026-10-18).
    func checkAIForRecording() {
        runScript("setup_check.py", ["status", "--quick"]) { [weak self] code, out in
            guard let self, self.recording, code == 0, let obj = lastObject(out, prefix: "JSON ") else { return }
            let state = (obj["ai"] as? [String: Any])?["state"] as? String ?? ""
            guard ["install", "installing", "login", "plan"].contains(state) else { return }   // not 'unknown'
            appLog("recording without a ready AI: \(state)")
            self.aiWarned = true
            if self.panel.isShown { self.panel.refresh() }
            else if let button = self.statusItem.button { self.panel.toggle(from: button) }
        }
    }

    func endRecording() -> URL? {
        guard let rec = recorder, let dir = currentJob else { return nil }
        aiWarned = false
        if let since = pausedAt { pausedTotal += Date().timeIntervalSince(since) }
        rec.stop()                          // the file is complete once the recorder is let go, just below
        tick?.invalidate()
        if let a = awake { ProcessInfo.processInfo.endActivity(a) }
        recorder = nil; currentJob = nil; startedAt = nil; pausedAt = nil; awake = nil
        bar.hide()
        refreshIcon()
        return dir
    }

    @objc func stopRecording() {
        let paused = Int(pausedTotal + (pausedAt.map { Date().timeIntervalSince($0) } ?? 0))
        guard let dir = endRecording() else { return }
        var meta = readJSON(dir.appendingPathComponent("job.json"))
        meta["ended"] = isoString(Date())
        meta["paused_seconds"] = paused
        writeJSON(meta, dir.appendingPathComponent("job.json"))
        let size = (try? FileManager.default.attributesOfItem(atPath: dir.appendingPathComponent("錄音.caf").path))?[.size] as? Int ?? 0
        appLog("recording stopped: \(dir.lastPathComponent), \(Int(elapsedFor(meta))) s, paused \(paused) s, \(size / 1024) KB")
        process(dir)
    }

    /// how long a finished recording ran, from its job.json
    func elapsedFor(_ meta: [String: Any]) -> TimeInterval {
        let f = ISO8601DateFormatter()
        guard let a = (meta["started"] as? String).flatMap({ f.date(from: $0) }),
              let b = (meta["ended"] as? String).flatMap({ f.date(from: $0) }) else { return 0 }
        return b.timeIntervalSince(a)
    }

    // MARK: background job

    func writeStatus(_ dir: URL, _ step: String, _ message: String) {
        writeJSON(["step": step, "message": message, "at": isoString(Date())], dir.appendingPathComponent("status.json"))
    }

    /// Start (or restart) the whole job for a finished recording.
    func process(_ dir: URL) {
        try? FileManager.default.removeItem(at: Job(dir: dir).notifiedMarker)
        writeStatus(dir, "transcribing", tr("status.preparing"))
        refreshIcon()
        appLog("write-up started: \(dir.lastPathComponent)")
        runPipeline([dir.path]) { [weak self] code, out in
            // the script records its own failures; this covers a crash before it could
            let job = Job(dir: dir)
            appLog("write-up ended: \(dir.lastPathComponent), exit \(code), step \(job.status["step"] as? String ?? "?")")
            if code != 0 && !job.finished {
                self?.writeStatus(dir, "failed", lastLine(out).isEmpty ? tr("status.stopped") : lastLine(out))
            }
            self?.checkJobs()
        }
    }

    /// A recording that never got its end time: the app or the Mac stopped mid-meeting. Finish it now.
    func recoverOrphans() {
        for job in recentJobs(limit: 20) where job.dir != currentJob && job.status.isEmpty {
            var meta = job.meta
            guard meta["ended"] == nil || meta["ended"] is NSNull else { continue }
            let audio = job.dir.appendingPathComponent(meta["audio"] as? String ?? "錄音.caf")
            guard let attrs = try? FileManager.default.attributesOfItem(atPath: audio.path),
                  let size = attrs[.size] as? Int, size > 64_000,
                  let modified = attrs[.modificationDate] as? Date else { continue }
            meta["ended"] = isoString(modified)
            writeJSON(meta, job.dir.appendingPathComponent("job.json"))
            appLog("recording found unfinished after a stop: \(job.dir.lastPathComponent)")
            process(job.dir)
        }
    }

    func recorderConfig() -> (python: String, skill: String)? {
        let obj = readJSON(configDir.appendingPathComponent("recorder.json"))
        guard let python = obj["python"] as? String, let skill = obj["app_dir"] as? String else { return nil }
        return (python, skill)
    }

    func runPipeline(_ args: [String], done: @escaping (Int32, String) -> Void) {
        runScript("auto_minutes.py", args, done: done)
    }

    /// Runs one of the Python scripts through a login shell, so the claude command is found on the user's PATH.
    func runScript(_ name: String, _ args: [String], done: @escaping (Int32, String) -> Void) {
        // the script, its command and the meeting folder: never what the user typed (a request, a name, a subject)
        var parts = [name]
        if let first = args.first { parts.append(first.hasPrefix("/") ? URL(fileURLWithPath: first).lastPathComponent : first) }
        if args.count > 1, args[1].hasPrefix("/") { parts.append(URL(fileURLWithPath: args[1]).lastPathComponent) }
        let what = parts.joined(separator: " ")
        let began = Date()
        // asked every few seconds while the window is open: logged only when they fail
        let quiet = name == "minutes_app.py" && ["refresh", "list", "version", "log", "locate"].contains(args.first ?? "")
        let done: (Int32, String) -> Void = { code, out in
            let took = String(format: "%.1f s", Date().timeIntervalSince(began))
            if code == 0 { if !quiet { appLog("ran \(what): ok, \(took)") } }
            else { appLog("ran \(what): exit \(code), \(took): \(String(lastLine(out).prefix(300)))") }
            done(code, out)
        }
        guard let cfg = recorderConfig() else {
            appLog("no recorder.json: install.sh has not been run")
            showError(tr("noApp.title"), tr("noApp.text"))
            done(1, "")
            return
        }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/bin/zsh")
        proc.arguments = ["-lc", "exec \"$0\" \"$@\"", cfg.python, (cfg.skill as NSString).appendingPathComponent("scripts/" + name)] + args
        // the scripts speak the app's language, so the window, the menu and their messages never disagree
        var env = ProcessInfo.processInfo.environment
        env["VINUTES_LANG"] = uiLanguage()
        proc.environment = env
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe
        var output = Data()
        let lock = NSLock()
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let chunk = handle.availableData
            lock.lock(); output.append(chunk); lock.unlock()
        }
        proc.terminationHandler = { p in
            pipe.fileHandleForReading.readabilityHandler = nil
            lock.lock()
            output.append(pipe.fileHandleForReading.readDataToEndOfFile())
            let text = String(data: output, encoding: .utf8) ?? ""
            lock.unlock()
            DispatchQueue.main.async { done(p.terminationStatus, text) }
        }
        do { try proc.run() } catch {
            showError(tr("run.failTitle"), error.localizedDescription)
            done(1, "")
        }
    }

    func recentJobs(limit: Int) -> [Job] {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: recordingsDir.path)) ?? []
        return names.filter { !$0.hasPrefix(".") }.sorted(by: >)
            .map { Job(dir: recordingsDir.appendingPathComponent($0)) }
            .filter { FileManager.default.fileExists(atPath: $0.dir.appendingPathComponent("job.json").path) }
            .prefix(limit).map { $0 }
    }

    /// Notice jobs that died without saying so, and tell the user once about every job that finished.
    func checkJobs() {
        if !recording { refreshIcon() }
        for job in recentJobs(limit: 10) where !job.finished && !job.step.isEmpty && job.dir != currentJob {
            if let pid = job.status["pid"] as? Int {
                if kill(pid_t(pid), 0) != 0 && errno == ESRCH { writeStatus(job.dir, "failed", tr("status.stopped")) }
            } else if let attrs = try? FileManager.default.attributesOfItem(atPath: job.dir.appendingPathComponent("status.json").path),
                      let at = attrs[.modificationDate] as? Date, Date().timeIntervalSince(at) > 180 {
                writeStatus(job.dir, "failed", tr("status.stopped"))
            }
        }
        for job in recentJobs(limit: 10) where job.finished && !FileManager.default.fileExists(atPath: job.notifiedMarker.path) {
            FileManager.default.createFile(atPath: job.notifiedMarker.path, contents: nil)
            announce(job)
        }
        // the meeting window's list follows every recording that starts, finishes or fails
        let seen = recentJobs(limit: 40).map { "\($0.name):\($0.step):\($0.sent)" }.joined(separator: ",")
        if seen != jobsSeen {
            jobsSeen = seen
            manager?.event("jobs", ["recording": recording])
        }
    }

    func announce(_ job: Job) {
        let content = UNMutableNotificationContent()
        content.title = job.step == "done" ? tr("notify.done") : tr("notify.failed")
        content.body = job.step == "done" ? job.title : job.message
        content.sound = .default
        content.userInfo = ["job": job.dir.path]
        guard notificationsAllowed else { openJob(job.dir); return }
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: job.name, content: content, trigger: nil))
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler done: @escaping () -> Void) {
        if let path = response.notification.request.content.userInfo["job"] as? String {
            DispatchQueue.main.async { self.openJob(URL(fileURLWithPath: path)) }
        }
        done()
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler done: @escaping (UNNotificationPresentationOptions) -> Void) {
        done([.banner, .sound])
    }

    // MARK: windows

    @objc func openJob(_ sender: Any) {
        guard let dir = (sender as? NSMenuItem)?.representedObject as? URL ?? sender as? URL else { return }
        showManager(select: dir.lastPathComponent)
    }

    @objc func showAll() { showManager(select: nil) }

    /// 用量統計: the meeting window on what the month's meetings used (the menu bar panel's button)
    @objc func showUsage() { showManager(select: nil, usage: true) }

    func showManager(select id: String?, setup: Bool = false, usage: Bool = false) {
        if manager == nil { appLog("meeting window opened" + (setup ? " on the setup checklist" : usage ? " on usage" : "")); manager = ManagerWindow(owner: self) }
        manager?.show(select: id, setup: setup, usage: usage)
    }

    @objc func openSetup() { showManager(select: nil, setup: true) }

    /// 環境設定自檢 opens by itself the first time the app starts after it is installed, and afterwards whenever
    /// something needed for recording and writing the minutes is missing (the microphone, the speech model, the AI).
    func checkSetupAtStart() {
        let seen = configDir.appendingPathComponent("setup-seen")
        if !FileManager.default.fileExists(atPath: seen.path) {
            FileManager.default.createFile(atPath: seen.path, contents: nil)
            return showManager(select: nil, setup: true)
        }
        runScript("setup_check.py", ["status", "--quick"]) { [weak self] code, out in
            guard code == 0, let obj = lastObject(out, prefix: "JSON ") else { return }
            let state = { (key: String) in (obj[key] as? [String: Any])?["state"] as? String ?? "" }
            let mic = AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
            // an AI that did not answer the sign-in question in time ('unknown') is not counted as missing
            let ai = state("ai")
            if !mic || state("speech") != "done" || (ai != "done" && ai != "unknown") { self?.showManager(select: nil, setup: true) }
        }
    }

    /// While the meeting window is open the app is in the Dock and in ⌘Tab, so clicking another app
    /// does not lose the window; with it closed the app is back to the menu bar only.
    func managerClosed() {
        appLog("meeting window closed")
        manager = nil
        NSApp.setActivationPolicy(.accessory)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showManager(select: nil)        // the Dock icon (or opening the app again) brings the meeting window back
        return true
    }

    func showError(_ title: String, _ text: String) {
        appLog("error shown: \(title): \(String(text.prefix(300)))")
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = text
        alert.addButton(withTitle: tr("btn.ok"))
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }

    @objc func openFolder() { NSWorkspace.shared.open(recordingsDir) }

    @objc func toggleLogin() {
        do {
            if SMAppService.mainApp.status == .enabled { try SMAppService.mainApp.unregister() }
            else { try SMAppService.mainApp.register() }
        } catch {
            showError(tr("login.failTitle"), tr("login.failText", error.localizedDescription))
        }
    }

    @objc func quit() { NSApp.terminate(nil) }
}


// MARK: live captions
// Shown under the floating bar, never written anywhere: the minutes still come from the transcript made after the
// recording. A helper (Captions.swift) reads the recording file as it grows and runs Apple's transcriber on this Mac
// (macOS 26 and later), so the recording itself is untouched.

/// The languages the caption menu offers: (Apple's locale, its name in that language)
let CAPTION_LANGUAGES: [(id: String, name: String)] = [("zh-TW", "中文"), ("en-US", "English"), ("ja-JP", "日本語"),
                                                       ("ko-KR", "한국어"), ("es-ES", "Español"), ("fr-FR", "Français")]

/// What captions start in: the meeting language from Settings, or the app's language when that is automatic
func defaultCaptionLanguage() -> String {
    switch meetingLanguage() {
    case "en": return "en-US"
    case "zh": return "zh-TW"
    default: return uiLanguage() == "en" ? "en-US" : "zh-TW"
    }
}

// MARK: logs
// What Vinutes does goes to ~/Library/Logs/Vinutes/ (Console.app shows them too): app.log for the app, captions.log
// for live captions (app and helper), scripts.log for the Python scripts. Only what happened and how long it took:
// no transcript, minutes, mail text or addresses. Each file is kept under 5 MB; past that it becomes <name>.1
// (replacing the one before), so a log never takes more than 10 MB.

let LOG_DIR = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/Vinutes")
let LOG_LIMIT = 5_000_000
private let logQueue = DispatchQueue(label: "vinutes.log")

func writeLog(_ name: String, _ line: String, wait: Bool = false) {
    let stamp = ISO8601DateFormatter.string(from: Date(), timeZone: .current, formatOptions: [.withInternetDateTime, .withFractionalSeconds])
    // a message may name a recipient: never an address in a log
    let clean = line.replacingOccurrences(of: #"[\w.+-]+@[\w-]+(\.[\w-]+)+"#, with: "<address>", options: .regularExpression)
    let text = "[\(stamp)] \(clean)\n"
    let work = {
        try? FileManager.default.createDirectory(at: LOG_DIR, withIntermediateDirectories: true)
        let file = LOG_DIR.appendingPathComponent(name)
        if let size = (try? FileManager.default.attributesOfItem(atPath: file.path))?[.size] as? Int, size > LOG_LIMIT {
            _ = rename(file.path, LOG_DIR.appendingPathComponent(name + ".1").path)   // one step, replacing the older
        }
        let fd = open(file.path, O_WRONLY | O_APPEND | O_CREAT, 0o644)      // whole lines, also beside other writers
        guard fd >= 0 else { return }
        _ = text.withCString { write(fd, $0, strlen($0)) }
        close(fd)
    }
    if wait { logQueue.sync(execute: work) } else { logQueue.async(execute: work) }
}

/// what the app did: app.log (wait: written before returning, for the last lines before quitting)
func appLog(_ line: String, wait: Bool = false) { writeLog("app.log", line, wait: wait) }

/// what the app did with live captions, beside the caption helper's own steps: captions.log
func captionLog(_ line: String) { writeLog("captions.log", "app " + line) }

/// Runs the caption helper (Contents/MacOS/VinutesCaptions, built from Captions.swift) on the recording file and passes
/// what it hears to the panel. In a process of its own: Apple's transcriber can fail or crash there without touching
/// the recording or this app.
final class CaptionFeed {
    private var process: Process?
    private var wanted = false
    var onText: ((String, String, String) -> Void)?
    var onNote: ((String) -> Void)?

    func start(file: URL, language: String) {
        stop()
        let helper = Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/VinutesCaptions")
        guard FileManager.default.isExecutableFile(atPath: helper.path) else {
            captionLog("no caption helper at \(helper.path)")
            onNote?(tr("caption.failed"))
            return
        }
        let p = Process()
        p.executableURL = helper
        p.arguments = [file.path, language]
        let out = Pipe(), err = Pipe()
        p.standardOutput = out
        p.standardError = err
        var pending = Data()
        out.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            if chunk.isEmpty { handle.readabilityHandler = nil; return }
            pending.append(chunk)
            while let end = pending.firstIndex(of: 10) {
                let line = pending.subdata(in: pending.startIndex..<end)
                pending.removeSubrange(pending.startIndex...end)
                guard let obj = (try? JSONSerialization.jsonObject(with: line)) as? [String: String] else { continue }
                DispatchQueue.main.async { if self?.process === p { self?.handle(obj, language) } }   // not an old helper's
            }
        }
        err.fileHandleForReading.readabilityHandler = { handle in
            let chunk = handle.availableData
            if chunk.isEmpty { handle.readabilityHandler = nil; return }
            captionLog("helper said: " + String(decoding: chunk, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines))
        }
        p.terminationHandler = { [weak self] done in
            let how = done.terminationReason == .uncaughtSignal ? "signal \(done.terminationStatus)" : "exit \(done.terminationStatus)"
            captionLog("helper \(done.processIdentifier) ended: \(how)")
            DispatchQueue.main.async {
                guard let self, self.wanted, self.process === done else { return }
                self.process = nil
                if !(done.terminationReason == .exit && done.terminationStatus == 0) { self.onNote?(tr("caption.failed")) }
            }
        }
        do {
            try p.run()
            process = p
            wanted = true
            captionLog("helper \(p.processIdentifier) started: \(language) \(file.lastPathComponent)")
        } catch {
            captionLog("helper did not start: \(error.localizedDescription)")
            onNote?(tr("caption.failed"))
        }
    }

    private func handle(_ obj: [String: String], _ language: String) {
        guard wanted else { return }
        if let note = obj["note"] {
            let name = CAPTION_LANGUAGES.first { $0.id == language }?.name ?? language
            switch note {
            case "downloading": onNote?(tr("caption.downloading", name))
            case "unsupported": onNote?(tr("caption.unsupported"))
            case "failed": onNote?(tr("caption.failed"))
            default: onNote?(tr("caption.listening"))
            }
        } else {
            onText?(obj["prev"] ?? "", obj["done"] ?? "", obj["hearing"] ?? "")
        }
    }

    func stop() {
        wanted = false
        if let p = process, p.isRunning {
            captionLog("stopping helper \(p.processIdentifier)")
            p.terminate()
        }
        process = nil
    }
}

/// The captions: one line, no background, purple words with a white outline, the newest words on the right and the
/// older ones fading out on the left (Vin 2026-10-17). A panel of its own under the floating bar that follows it and
/// lets clicks through.
final class CaptionPanel {
    let panel: NSPanel
    private let back = NSTextField(labelWithString: ""), front = NSTextField(labelWithString: "")
    private let width: CGFloat = 320, height: CGFloat = 30, fade: CGFloat = 0.28   // the left 28% fades out
    private let font = NSFont.systemFont(ofSize: 18, weight: .bold)
    static let done = NSColor(srgbRed: 0x7C / 255, green: 0x4D / 255, blue: 1, alpha: 1)
    static let hearing = NSColor(srgbRed: 0xA3 / 255, green: 0xA3 / 255, blue: 0xA9 / 255, alpha: 1)

    init() {
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: width, height: height),
                        styleMask: [.nonactivatingPanel, .borderless], backing: .buffered, defer: true)
        panel.level = .floating
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.canHide = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = false
        panel.ignoresMouseEvents = true
        let view = NSView(frame: NSRect(x: 0, y: 0, width: width, height: height))
        view.wantsLayer = true
        let mask = CAGradientLayer()                       // transparent on the left edge, fully shown from `fade` on
        mask.frame = view.bounds
        mask.startPoint = CGPoint(x: 0, y: 0.5)
        mask.endPoint = CGPoint(x: 1, y: 0.5)
        mask.colors = [NSColor.clear.cgColor, NSColor.black.cgColor]
        mask.locations = [0, NSNumber(value: Double(fade))]
        view.layer?.mask = mask
        panel.contentView = view
        for f in [back, front] {
            f.frame = NSRect(x: 0, y: 2, width: width, height: height - 4)
            f.autoresizingMask = [.width]
            f.drawsBackground = false
            f.lineBreakMode = .byClipping
            f.maximumNumberOfLines = 1
            view.addSubview(f)
        }
    }

    private func words(_ parts: [(String, NSColor)], outline: Bool) -> NSAttributedString {
        let style = NSMutableParagraphStyle()
        style.alignment = .right
        style.lineBreakMode = .byClipping
        let out = NSMutableAttributedString()
        for (text, color) in parts {
            var attrs: [NSAttributedString.Key: Any] = [.font: font, .paragraphStyle: style]
            if outline {                           // the white edge behind the words: an outline only, drawn wide
                attrs[.strokeColor] = NSColor.white
                attrs[.strokeWidth] = 26
                attrs[.foregroundColor] = NSColor.white
            } else {
                attrs[.foregroundColor] = color
            }
            out.append(NSAttributedString(string: text, attributes: attrs))
        }
        return out
    }

    /// the end of the line that fits the panel; what is cut off the front is what the fade would hide anyway
    private func fitting(_ done: String, _ hearing: String) -> (String, String) {
        var d = done, h = hearing
        let room = width - 8
        while !(d + h).isEmpty, words([(d + h, .clear)], outline: false).size().width > room {
            if !d.isEmpty { d.removeFirst() } else { h.removeFirst() }
        }
        return (d, h)
    }

    func show(prev: String, done: String, hearing: String, align: NSTextAlignment) {
        let (d, h) = fitting(done.replacingOccurrences(of: "…", with: ""), hearing)
        back.attributedStringValue = words([(d + h, .clear)], outline: true)
        front.attributedStringValue = words([(d, Self.done), (h, Self.hearing)], outline: false)
    }

    func note(_ text: String, align: NSTextAlignment) { show(prev: "", done: "", hearing: text, align: align) }

    /// under the bar, lined up with its right edge (or its left edge when the bar sits on the left of the screen)
    func place(under bar: NSRect) -> NSTextAlignment {
        let screen = (NSScreen.screens.first { $0.frame.intersects(bar) } ?? NSScreen.main)?.visibleFrame ?? bar
        let left = bar.midX < screen.midX
        var x = left ? bar.minX : bar.maxX - width
        x = max(screen.minX + 4, min(x, screen.maxX - width - 4))
        var y = bar.minY - height - 4
        if y < screen.minY { y = bar.maxY + 4 }                 // the bar sits low on the screen: captions above it
        panel.setFrame(NSRect(x: x, y: y, width: width, height: height), display: false)
        return left ? .left : .right
    }
}

/// Five small bars that jump with the microphone's level while recording, so a glance shows the recording is
/// running and the microphone hears the room; they lie flat and turn orange while paused.
final class LevelBars: NSView {
    private var bars: [CALayer] = []
    private let count = 5, barWidth: CGFloat = 3, gap: CGFloat = 2, low: CGFloat = 3

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        for i in 0..<count {
            let bar = CALayer()
            bar.cornerRadius = barWidth / 2
            bar.frame = CGRect(x: CGFloat(i) * (barWidth + gap), y: 0, width: barWidth, height: low)
            layer?.addSublayer(bar)
            bars.append(bar)
        }
        translatesAutoresizingMaskIntoConstraints = false
        widthAnchor.constraint(equalToConstant: CGFloat(count) * barWidth + CGFloat(count - 1) * gap).isActive = true
        heightAnchor.constraint(equalToConstant: 18).isActive = true
    }
    required init?(coder: NSCoder) { fatalError() }

    /// level: 0 (silence) ... 1 (loud); paused: flat and orange
    func show(level: CGFloat, paused: Bool) {
        let color = (paused ? NSColor.systemOrange : NSColor.systemRed).cgColor
        CATransaction.begin()
        CATransaction.setAnimationDuration(0.12)
        for bar in bars {
            let h = paused ? low : low + (bounds.height - low) * min(1, level * CGFloat.random(in: 0.45...1.2))
            bar.backgroundColor = color
            bar.frame = CGRect(x: bar.frame.minX, y: (bounds.height - h) / 2, width: barWidth, height: h)
        }
        CATransaction.commit()
    }
}

/// The small floating bar while recording: time, pause / resume, stop. Stays above other windows,
/// on every desktop, and never takes the keyboard away from the meeting notes.
final class RecordingBar: NSObject {
    weak var owner: AppDelegate?
    let panel: NSPanel
    let dot = LevelBars(frame: NSRect(x: 0, y: 0, width: 23, height: 18))
    var meter: Timer?
    var ccButton: NSButton?
    var langButton: NSButton?
    let captions = CaptionPanel()
    let feed = CaptionFeed()
    var captionLanguage = defaultCaptionLanguage()
    var align: NSTextAlignment = .right
    var captionsOn: Bool {
        get { UserDefaults.standard.bool(forKey: "captionsOn") }
        set { UserDefaults.standard.set(newValue, forKey: "captionsOn") }
    }
    let time = NSTextField(labelWithString: "00:00")
    var pauseButton: NSButton!
    var stopButton: NSButton!

    init(owner: AppDelegate) {
        self.owner = owner
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 164, height: 38),
                        styleMask: [.nonactivatingPanel, .borderless], backing: .buffered, defer: true)
        super.init()
        panel.level = .floating
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.canHide = false                    // ⌘H on the meeting window must not hide the recording bar
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isMovableByWindowBackground = true
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true

        let fx = NSVisualEffectView()
        fx.material = .hudWindow
        fx.blendingMode = .behindWindow
        fx.state = .active
        fx.wantsLayer = true
        fx.layer?.cornerRadius = 19
        fx.layer?.masksToBounds = true
        panel.contentView = fx

        time.font = .monospacedDigitSystemFont(ofSize: 15, weight: .medium)
        pauseButton = button("pause.fill", #selector(AppDelegate.togglePause), tr("bar.pause"))
        stopButton = button("stop.fill", #selector(AppDelegate.stopRecording), tr("bar.stop"))
        var views: [NSView] = [dot, time]
        if #available(macOS 26.0, *) {
            let cc = NSButton(image: symbol("captions.bubble", 14, .semibold) ?? NSImage(), target: self, action: #selector(toggleCaptions))
            cc.isBordered = false
            cc.toolTip = tr("bar.captions")
            let lang = NSButton(image: symbol("chevron.down", 9, .bold) ?? NSImage(), target: self, action: #selector(pickLanguage(_:)))
            lang.isBordered = false
            lang.toolTip = tr("bar.captionLanguage")
            lang.contentTintColor = .secondaryLabelColor
            ccButton = cc
            langButton = lang
            views += [cc, lang]
        }
        views += [pauseButton, stopButton]
        let row = NSStackView(views: views)
        row.orientation = .horizontal
        row.spacing = 10
        row.setCustomSpacing(6, after: dot)
        if let cc = ccButton { row.setCustomSpacing(1, after: cc) }
        row.edgeInsets = NSEdgeInsets(top: 0, left: 14, bottom: 0, right: 12)
        row.translatesAutoresizingMaskIntoConstraints = false
        fx.addSubview(row)
        NSLayoutConstraint.activate([row.leadingAnchor.constraint(equalTo: fx.leadingAnchor),
                                     row.trailingAnchor.constraint(equalTo: fx.trailingAnchor),
                                     row.centerYAnchor.constraint(equalTo: fx.centerYAnchor)])
        panel.setFrameAutosaveName("RecordingBar")
        if ccButton != nil { panel.setContentSize(NSSize(width: 204, height: 38)) }
        NotificationCenter.default.addObserver(forName: NSWindow.didMoveNotification, object: panel, queue: .main) { [weak self] _ in
            guard let self else { return }
            self.align = self.captions.place(under: self.panel.frame)
        }
    }

    func button(_ image: String, _ action: Selector, _ tip: String) -> NSButton {
        let b = NSButton(image: symbol(image, 14, .semibold) ?? NSImage(), target: owner, action: action)
        b.isBordered = false
        b.toolTip = tip
        b.contentTintColor = .labelColor
        return b
    }

    func show() {
        if !panel.setFrameUsingName("RecordingBar"), let screen = NSScreen.main?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: screen.maxX - panel.frame.width - 24, y: screen.maxY - panel.frame.height - 14))
        }
        // a place saved when the bar was narrower can leave its right end off the screen
        if let screen = (NSScreen.screens.first { $0.frame.intersects(panel.frame) } ?? NSScreen.main)?.visibleFrame {
            let f = panel.frame
            panel.setFrameOrigin(NSPoint(x: max(screen.minX, min(f.minX, screen.maxX - f.width)),
                                         y: max(screen.minY, min(f.minY, screen.maxY - f.height))))
        }
        update()
        panel.orderFrontRegardless()
        meter?.invalidate()
        meter = Timer.scheduledTimer(withTimeInterval: 0.13, repeats: true) { [weak self] _ in self?.listen() }
        captionLanguage = defaultCaptionLanguage()     // each recording starts in the meeting language
        if captionsOn { startCaptions() }
        refreshCaptionButton()
    }

    func hide() {
        meter?.invalidate()
        meter = nil
        stopCaptions()
        panel.orderOut(nil)
    }

    // captions

    @objc func toggleCaptions() {
        captionsOn.toggle()
        if captionsOn { startCaptions() } else { stopCaptions() }
        refreshCaptionButton()
    }

    @objc func pickLanguage(_ sender: NSButton) {
        let menu = NSMenu()
        for lang in CAPTION_LANGUAGES {
            let it = NSMenuItem(title: lang.name, action: #selector(chooseLanguage(_:)), keyEquivalent: "")
            it.target = self
            it.representedObject = lang.id
            it.state = lang.id == captionLanguage ? .on : .off
            menu.addItem(it)
        }
        menu.popUp(positioning: nil, at: NSPoint(x: 0, y: sender.bounds.maxY + 4), in: sender)
    }

    @objc func chooseLanguage(_ item: NSMenuItem) {
        guard let id = item.representedObject as? String, id != captionLanguage else { return }
        captionLanguage = id
        if !captionsOn { captionsOn = true; refreshCaptionButton() }
        startCaptions()
    }

    func refreshCaptionButton() {
        ccButton?.image = symbol(captionsOn ? "captions.bubble.fill" : "captions.bubble", 14, .semibold)
        ccButton?.contentTintColor = captionsOn ? CaptionPanel.done : .labelColor
    }

    func startCaptions() {
        guard #available(macOS 26.0, *), let owner, owner.recording, let job = owner.currentJob else { return }
        align = captions.place(under: panel.frame)
        feed.onText = { [weak self] prev, done, hearing in
            guard let self else { return }
            self.captions.show(prev: prev, done: done, hearing: hearing, align: self.align)
        }
        feed.onNote = { [weak self] text in
            guard let self else { return }
            self.captions.note(text, align: self.align)
        }
        captions.note(tr("caption.listening"), align: align)
        feed.start(file: job.appendingPathComponent("錄音.caf"), language: captionLanguage)
        captions.panel.orderFrontRegardless()
    }

    func stopCaptions() {
        feed.stop()
        captions.note("", align: align)
        captions.panel.orderOut(nil)
    }

    /// about -50 dB and below counts as a quiet room, 0 dB as loud
    func listen() {
        guard let owner, owner.recording, let rec = owner.recorder else { return }
        let level = CGFloat(max(0, min(1, (rec.averagePower + 50) / 50)))
        dot.show(level: level, paused: owner.paused)
        owner.panel?.listen(level: level, paused: owner.paused)
    }

    func update() {
        guard let owner, owner.recording else { return }
        if owner.paused { dot.show(level: 0, paused: true) }

        time.stringValue = clock(owner.elapsed)
        time.textColor = owner.paused ? .secondaryLabelColor : .labelColor
        pauseButton.image = symbol(owner.paused ? "play.fill" : "pause.fill", 14, .semibold)
        pauseButton.toolTip = owner.paused ? tr("bar.resume") : tr("bar.pause")
        stopButton.toolTip = tr("bar.stop")
    }
}


final class WeakHandler: NSObject, WKScriptMessageHandler {
    weak var target: WKScriptMessageHandler?
    init(_ target: WKScriptMessageHandler) { self.target = target }
    func userContentController(_ c: WKUserContentController, didReceive message: WKScriptMessage) {
        target?.userContentController(c, didReceive: message)
    }
}


/// Top-left origin, so a rectangle the page measures in CSS pixels is a frame here as it is.
final class FlippedView: NSView {
    override var isFlipped: Bool { true }
}


/// The meeting window. The page (Resources/app/index.html) sends {id, cmd, args} to the "app" handler; every
/// request runs a script and the answer goes back as window.reply(id, ok, data). Events the page did not ask
/// for (the list changed, a meeting picked in the menu, the recording playing) arrive as window.onEvent(name, data).
/// The minutes' Google Doc is a second web view laid over the page, where the page keeps a place for it (`gdoc`).
final class ManagerWindow: NSObject, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler,
                           AVAudioPlayerDelegate {
    weak var owner: AppDelegate?
    let window: NSWindow
    var web: WKWebView!
    var docView: WKWebView?
    var docURL = ""                  // the Doc asked for: its address as the page sent it
    var docWanted = false            // the page has a place for it right now
    var docReady = false             // the Doc asked for has started to show (until then the page's spinner shows)
    var blinkWaiting = false         // the blanks blink once the Doc being loaded shows
    var picked = Set<String>()       // files the user chose in this window's open panel: the only ones 附件 sends
    var appDir: URL?
    var loaded = false
    var pendingSelect: String?
    var pendingSetup = false         // 環境設定自檢 shows once the page has loaded
    var pendingUsage = false         // 用量統計 too
    var player: AVAudioPlayer?
    var playerJob = ""
    var playerTick: Timer?
    var closing = false

    init(owner: AppDelegate) {
        self.owner = owner
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1400, height: 860),
                          styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
        super.init()
        window.title = "Vinutes"
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 1080, height: 640)
        window.delegate = self
        let config = WKWebViewConfiguration()
        config.userContentController.add(WeakHandler(self), name: "app")
        config.userContentController.addUserScript(ManagerWindow.languageScript())
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        let content = FlippedView()
        window.contentView = content
        web.frame = content.bounds
        web.autoresizingMask = [.width, .height]
        content.addSubview(web)
        if !window.setFrameUsingName("MeetingWindow") { window.center() }
        window.setFrameAutosaveName("MeetingWindow")
        if let page = Bundle.main.url(forResource: "index", withExtension: "html", subdirectory: "app") {
            appDir = page.deletingLastPathComponent()
            web.loadFileURL(page, allowingReadAccessTo: page.deletingLastPathComponent())
        } else {
            web.loadHTMLString("<p style='font:14px -apple-system;padding:24px'>\(tr("window.missing"))</p>", baseURL: nil)
        }
    }

    func show(select id: String?, setup: Bool = false, usage: Bool = false) {
        if let id {
            if loaded { event("select", ["id": id]) } else { pendingSelect = id }
        }
        if setup {
            if loaded { event("setup") } else { pendingSetup = true }
        }
        if usage {
            if loaded { event("usage") } else { pendingUsage = true }
        }
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        if window.isMiniaturized { window.deminiaturize(nil) }
        window.makeKeyAndOrderFront(nil)
    }

    // MARK: language

    /// window.VINUTES_LANG before the page's own scripts run, so the page draws itself in the app's language.
    static func languageScript() -> WKUserScript {
        WKUserScript(source: "window.VINUTES_LANG = \"\(uiLanguage())\";", injectionTime: .atDocumentStart,
                     forMainFrameOnly: true)
    }

    /// The language changed (here or in the menu): a reload starts in the new one, the open page switches now.
    func languageChanged() {
        let scripts = web.configuration.userContentController
        scripts.removeAllUserScripts()
        scripts.addUserScript(ManagerWindow.languageScript())
        event("language", ["lang": uiLanguage()])
    }

    // MARK: talking to the page

    func js(_ value: Any) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed]),
              let text = String(data: data, encoding: .utf8) else { return "null" }
        return text
    }

    func reply(_ id: Int, _ ok: Bool, _ data: Any) {
        web.evaluateJavaScript("window.reply(\(id), \(ok), \(js(data)))")
    }

    func event(_ name: String, _ data: [String: Any] = [:]) {
        guard loaded else { return }
        web.evaluateJavaScript("window.onEvent(\(js(name)), \(js(data)))")
    }

    func userContentController(_ c: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any], let id = (body["id"] as? NSNumber)?.intValue,
              let cmd = body["cmd"] as? String else { return }
        if cmd == "closed" && id == -1 {                 // finish(): the page has saved what was typed
            let waiting = closing_
            closing_ = []
            waiting.forEach { $0() }
            return
        }
        let began = Date()
        let quiet = ["refresh", "gdoc", "blink", "version", "audio", "find", "log"].contains(cmd)  // asked every few seconds
        handle(cmd, body["args"] as? [String: Any] ?? [:]) { [weak self] ok, data in
            if !ok || !quiet {
                let why = ok ? "" : ": " + String(((data as? [String: Any])?["message"] as? String ?? "").prefix(200))
                appLog(String(format: "window %@: %@, %.1f s%@", cmd, ok ? "ok" : "failed", Date().timeIntervalSince(began), why))
            }
            self?.reply(id, ok, data)
        }
    }

    /// minutes_app.py: the last line `JSON {...}` is the answer; anything else, its last line is the message.
    func app(_ args: [String], _ done: @escaping (Bool, Any) -> Void) {
        guard let owner else { return done(false, ["message": tr("err.quitting")]) }
        owner.runScript("minutes_app.py", args) { code, out in
            if code == 0, let obj = lastObject(out, prefix: "JSON ") { return done(true, obj) }
            let why = lastLine(out)
            done(false, ["message": why.isEmpty || why.hasPrefix("JSON ") ? tr("err.tryAgain") : why])
        }
    }

    func handle(_ cmd: String, _ args: [String: Any], _ done: @escaping (Bool, Any) -> Void) {
        // a meeting is one of the folders the app itself made: 20261014-145212; nothing else reaches the scripts
        let id = args["id"] as? String ?? ""
        let dir = recordingsDir.appendingPathComponent(id)
        let isJob = id.range(of: #"^\d{8}-\d{6}$"#, options: .regularExpression) != nil
            && FileManager.default.fileExists(atPath: dir.appendingPathComponent("job.json").path)
        let text = args["text"] as? String ?? ""
        let needJob: Set<String> = ["open", "learn", "log", "undo", "save", "ask", "quick", "unlearn", "relearn", "reply",
                                     "resolve", "confirm", "retry", "folder", "audio", "mailPrepare", "send", "refresh",
                                     "speaker", "attach", "move", "tags", "people", "moveLearned"]
        if needJob.contains(cmd) && !isJob && !(cmd == "audio" && (args["action"] as? String) != "play") {
            return done(false, ["message": tr("err.noJob")])
        }
        switch cmd {
        case "ready":
            loaded = true
            done(true, ["select": pendingSelect ?? "", "setup": pendingSetup, "usage": pendingUsage])
            pendingSelect = nil
            pendingSetup = false
            pendingUsage = false
        case "list":
            app(["list"], done)
        case "usage":                                    // 用量統計: one month, YYYY-MM ('' = this month)
            let month = args["month"] as? String ?? ""
            app(["usage", month.range(of: #"^\d{4}-\d{2}$"#, options: .regularExpression) != nil ? month : ""], done)
        case "record":                                   // the button shown before the first meeting is recorded
            guard let owner else { return done(false, ["message": tr("err.unknownCommand")]) }
            owner.startRecording()
            done(true, ["recording": owner.recording])
        case "setLanguage":
            let lang = args["lang"] as? String ?? ""
            guard lang == "en" || lang == "zh-TW", let owner else { return done(false, ["message": tr("err.unknownCommand")]) }
            owner.setLanguage(lang)
            done(true, ["lang": lang])
            languageChanged()
        case "open", "learn", "log", "undo", "refresh":
            app([cmd, dir.path], done)
        case "gdoc":
            placeDoc(args)
            done(true, [:])
        case "find":
            findInDoc(dir, text) { [weak self] ok, data in
                if args["blink"] as? Bool ?? false { self?.blinkDoc() }
                done(ok, data)
            }
        case "blink":
            blinkDoc()
            done(true, [:])
        case "save":
            let file = dir.appendingPathComponent("編輯中.html")
            do { try (args["html"] as? String ?? "").write(to: file, atomically: true, encoding: .utf8) } catch {
                return done(false, ["message": tr("err.saveEdits")])
            }
            // the token of the preview the user was editing: 16 hex characters, or nothing
            let shown = args["shown"] as? String ?? ""
            let token = shown.range(of: #"^[0-9a-f]{16}$"#, options: .regularExpression) != nil ? shown : ""
            app(["save", dir.path, file.path] + (token.isEmpty ? [] : [token]), done)
        case "ask", "quick":
            app([cmd, dir.path, text], done)
        case "unlearn", "relearn":
            app([cmd, dir.path, String((args["item"] as? NSNumber)?.intValue ?? 0)], done)
        case "moveLearned":
            // a learned word goes to the project's brief or to the glossary
            let to = args["where"] as? String ?? ""
            guard to == "brief" || to == "glossary" else { return done(false, ["message": tr("err.tryAgain")]) }
            app(["move_learned", dir.path, String((args["item"] as? NSNumber)?.intValue ?? 0), to], done)
        case "reply":
            app(["reply", dir.path, args["comment"] as? String ?? "", text], done)
        case "resolve":
            app(["resolve", dir.path, args["comment"] as? String ?? ""], done)
        case "confirm":
            app(["confirm", dir.path, args["item"] as? String ?? ""], done)
        case "pick":
            pickFiles(images: args["kind"] as? String == "image", done)
        case "pastePicture":
            pastedPictures(done)
        case "setupState":
            setupState(progress: args["progress"] as? Bool ?? false, done)
        case "setupMic":
            switch AVCaptureDevice.authorizationStatus(for: .audio) {
            case .notDetermined:
                AVCaptureDevice.requestAccess(for: .audio) { _ in DispatchQueue.main.async { self.setupState(done) } }
            case .authorized:
                setupState(done)
            default:
                openSettings("x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")
                done(true, [:])
            }
        case "setupNotify":
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                DispatchQueue.main.async {
                    if settings.authorizationStatus == .notDetermined {
                        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in
                            DispatchQueue.main.async { self.setupState(done) }
                        }
                    } else {
                        self.openSettings("x-apple.systempreferences:com.apple.Notifications-Settings.extension")
                        done(true, [:])
                    }
                }
            }
        case "setupRun":
            // the downloads and the Google login run on their own; the page asks again how far they got
            let what = args["what"] as? String ?? ""
            let known: [String: [String]] = ["speech": ["download", "speech"], "voice": ["download", "voice"],
                                            "login": ["login"]]
            guard let run = known[what] else { return done(false, ["message": tr("err.noSetupItem")]) }
            owner?.runScript("setup_check.py", run) { code, out in
                if code == 0 { return done(true, [:]) }
                done(false, ["message": lastLine(out).isEmpty ? tr("err.tryAgain") : lastLine(out)])
            }
        case "setupAI":
            let key = args["ai"] as? String ?? ""
            guard ["claude", "codex", "antigravity"].contains(key) else { return done(false, ["message": tr("err.noAI")]) }
            setupScript(["ai", key], done)
        case "aiStates":
            setupScript(["ais"], done)
        case "setupAILogin":
            aiLogin(args["ai"] as? String ?? "")
            done(true, [:])
        case "setupAIInstall":
            // the maker's own install script, run in the background by setup_check.py (item 5, step 2)
            let key = args["ai"] as? String ?? ""
            guard ["claude", "codex", "antigravity"].contains(key) else { return done(false, ["message": tr("err.noAI")]) }
            setupScript(["aiinstall", key], done)
        case "setupAITest":
            setupScript(["aitest"], done)          // one short answer from the AI (step 4), some seconds
        case "setupClient":
            pickClient(done)
        case "setupOpen":
            // only the pages the checklist links to: Google Cloud (the AIs are installed by setup_check.py)
            let text = args["url"] as? String ?? ""
            let hosts = ["console.cloud.google.com"]
            guard let url = URL(string: text), url.scheme == "https", hosts.contains(url.host ?? "") else {
                return done(false, ["message": tr("err.badURL")])
            }
            NSWorkspace.shared.open(url)
            done(true, [:])
        case "attach":
            // files and pictures only from the open panel above; a link only http(s)
            var items: [[String: String]] = []
            for item in args["items"] as? [[String: Any]] ?? [] {
                let kind = item["kind"] as? String ?? ""
                if kind == "file" || kind == "image", let path = item["path"] as? String, picked.contains(path) {
                    items.append(["kind": kind, "path": path])
                } else if kind == "link", let url = item["url"] as? String, url.hasPrefix("https://") || url.hasPrefix("http://") {
                    items.append(["kind": kind, "url": url])
                }
            }
            guard !items.isEmpty, let data = try? JSONSerialization.data(withJSONObject: items),
                  let json = String(data: data, encoding: .utf8) else {
                return done(false, ["message": tr("err.nothingToAttach")])
            }
            app(["attach", dir.path, text, json], done)
        case "speaker":
            // a voice named in the transcript: 講者 A (a letter) -> a name, for every line of it or one line
            let group = args["group"] as? String ?? ""
            let name = (args["name"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard group.range(of: #"^[A-Z]$"#, options: .regularExpression) != nil, !name.isEmpty, name.count <= 30 else {
                return done(false, ["message": tr("err.speakerName")])
            }
            let line = (args["line"] as? NSNumber).map { [String($0.intValue)] } ?? []
            app(["speaker", dir.path, group, name] + line, done)
        case "people":
            // 人員: add someone to the meeting, take someone off, or a voice's guessed name (with its letter)
            let action = args["action"] as? String ?? ""
            let name = (args["name"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let group = args["group"] as? String ?? ""
            guard action == "add" || action == "remove", !name.isEmpty, name.count <= 30,
                  group.isEmpty || group.range(of: #"^[A-Z]$"#, options: .regularExpression) != nil else {
                return done(false, ["message": tr("err.speakerName")])
            }
            app(["people", dir.path, action, name] + (group.isEmpty ? [] : [group]), done)
        case "move":
            // the project this meeting belongs to ('' = 未分類); minutes_app.py trims it to one line
            app(["move", dir.path, args["project"] as? String ?? ""], done)
        case "tags":
            // a list of words or nothing: anything else would empty the meeting's tags
            guard let given = args["tags"] as? [String] else { return done(false, ["message": tr("err.tryAgain")]) }
            let tags = given.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            guard let data = try? JSONSerialization.data(withJSONObject: tags),
                  let json = String(data: data, encoding: .utf8) else { return done(false, ["message": tr("err.tryAgain")]) }
            app(["tags", dir.path, json], done)
        case "renameProject":
            let old = args["old"] as? String ?? "", new = args["new"] as? String ?? ""
            app(["rename_project", old, new], done)
        case "brief":
            // a project's brief (專案小抄): its people with what they do, its terms, its background
            app(["brief", args["project"] as? String ?? ""], done)
        case "saveBrief":
            // the brief as the user left it in 專案設定; anything that is not one would empty it
            guard let brief = args["brief"] as? [String: Any], JSONSerialization.isValidJSONObject(brief),
                  let data = try? JSONSerialization.data(withJSONObject: brief),
                  let json = String(data: data, encoding: .utf8) else { return done(false, ["message": tr("err.tryAgain")]) }
            app(["save_brief", args["project"] as? String ?? "", json], done)
        case "retry":
            // only a recording that failed starts over; a finished one keeps its Doc and its sent mail
            guard Job(dir: dir).step == "failed" else { return done(false, ["message": tr("err.alreadyDone")]) }
            owner?.process(dir)
            done(true, [:])
        case "folder":
            NSWorkspace.shared.open(dir)
            done(true, [:])
        case "link":
            // only the minutes' own Google Doc opens from here
            if let url = URL(string: args["url"] as? String ?? ""), url.scheme == "https",
               ["docs.google.com", "drive.google.com"].contains(url.host ?? "") {
                NSWorkspace.shared.open(url)
            }
            done(true, [:])
        case "audio":
            audio(dir, args, done)
        case "version":
            // the list's corner: this app's version, whether GitHub has a newer one, and whether a recording runs
            let mine = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
            app(["version", mine]) { [weak self] ok, data in
                var info = data as? [String: Any] ?? [:]
                info["recording"] = self?.owner?.recording ?? false
                done(ok, info)
            }
        case "update":
            guard owner?.recording != true else { return done(false, ["message": tr("err.updateWhileRecording")]) }
            app(["update"], done)
        case "mailPrepare", "send":
            mail(dir, args, send: cmd == "send", done)
        case "archive", "unarchive", "delete":
            let ids = (args["ids"] as? [String] ?? []).filter {
                $0.range(of: #"^\d{8}-\d{6}$"#, options: .regularExpression) != nil
                    && FileManager.default.fileExists(atPath: recordingsDir.appendingPathComponent($0)
                        .appendingPathComponent("job.json").path)
            }
            eachMeeting(cmd, ids, done)
        default:
            done(false, ["message": tr("err.unknownCommand")])
        }
    }

    // MARK: sending the minutes

    /// The sheet's recipients, subject, text and attachment become the preview (--dry); the mail is sent only if
    /// the preview is exactly what the sheet showed when the user pressed 寄出.
    func mail(_ dir: URL, _ args: [String: Any], send: Bool, _ done: @escaping (Bool, Any) -> Void) {
        guard let owner else { return done(false, ["message": tr("err.quitting")]) }
        let to = (args["to"] as? [String] ?? []).map { $0.trimmingCharacters(in: .whitespaces).lowercased() }.filter { !$0.isEmpty }
        let subject = (args["subject"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let body = (args["body"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let format = args["format"] as? String ?? "gdoc"
        guard ["gdoc", "word", "pdf"].contains(format) else { return done(false, ["message": tr("err.badFormat")]) }
        guard !to.isEmpty else { return done(false, ["message": tr("err.noRecipient")]) }
        guard !subject.isEmpty, !body.isEmpty else { return done(false, ["message": tr("err.emptyMail")]) }
        do { try body.write(to: dir.appendingPathComponent("信件內文.txt"), atomically: true, encoding: .utf8) } catch {
            return done(false, ["message": tr("err.saveMail")])
        }
        let base = ["--send", dir.path, "--to", to.joined(separator: ","), "--subject", subject, "--format", format]
        owner.runPipeline(base + ["--dry"]) { code, out in
            guard code == 0, let preview = lastObject(out, prefix: "MAIL "), let confirm = preview["code"] as? String else {
                let why = lastLine(out)
                return done(false, ["message": why.isEmpty ? tr("err.previewFailed") : why])
            }
            guard send else { return done(true, preview) }
            let same = Set(preview["to"] as? [String] ?? []) == Set(to)
                && (preview["subject"] as? String ?? "") == subject
                && (preview["body"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines) == body
            guard same else { return done(false, ["message": tr("err.mailChanged")]) }
            owner.runPipeline(base + ["--confirm", confirm]) { code, out in
                guard code == 0 else {
                    let why = lastLine(out)
                    return done(false, ["message": why.isEmpty ? tr("err.notSent") : why])
                }
                let f = DateFormatter()
                f.dateFormat = "MM/dd HH:mm"
                let words = ["gdoc": tr("format.gdoc"), "word": tr("format.word"), "pdf": tr("format.pdf")][format] ?? ""
                done(true, ["sent": ["at": f.string(from: Date()), "count": to.count, "format": words]])
                owner.checkJobs()
            }
        }
    }

    // MARK: listening to the recording

    func audio(_ dir: URL, _ args: [String: Any], _ done: @escaping (Bool, Any) -> Void) {
        switch args["action"] as? String ?? "" {
        case "play":
            if player == nil || playerJob != dir.lastPathComponent {
                let name = Job(dir: dir).meta["audio"] as? String ?? "錄音.m4a"
                guard let p = try? AVAudioPlayer(contentsOf: dir.appendingPathComponent(name)) else {
                    return done(false, ["message": tr("err.noAudio")])
                }
                p.enableRate = true
                p.delegate = self
                p.prepareToPlay()
                player = p
                playerJob = dir.lastPathComponent
            }
            if let at = (args["at"] as? NSNumber)?.doubleValue { player?.currentTime = max(0, min(at, player?.duration ?? 0)) }
            player?.play()
            playerTick?.invalidate()
            playerTick = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in self?.tellPlayer() }
        case "pause":
            player?.pause()
        case "rate":
            player?.rate = (args["rate"] as? NSNumber)?.floatValue ?? 1
        case "stop":
            player?.stop()
            player = nil
            playerTick?.invalidate()
        default:
            break
        }
        tellPlayer()
        done(true, [:])
    }

    /// 封存, 取消封存 or 刪除 for the meetings picked in the list, one after the other (main thread: runScript
    /// answers there). Answers the ones that went through and a message. The first one that fails stops the rest:
    /// offline, each of them would wait for Google too. A deleted meeting's folder goes to the Mac's Trash first,
    /// once minutes_app.py has sent its Doc to Google's trash; if the folder can't go, the meeting stays listed.
    /// The files beside its minutes follow; one that can't go is only mentioned.
    func eachMeeting(_ cmd: String, _ ids: [String], _ done: @escaping (Bool, Any) -> Void) {
        var through: [String] = []
        func next(_ rest: ArraySlice<String>, _ note: String) {
            guard let id = rest.first else { return done(true, ["done": through, "message": note]) }
            let dir = recordingsDir.appendingPathComponent(id)
            app([cmd, dir.path]) { [weak self] ok, data in
                let answer = data as? [String: Any] ?? [:]
                guard ok else {
                    return done(true, ["done": through, "message": answer["message"] as? String ?? tr("err.tryAgain")])
                }
                guard cmd == "delete" else {
                    through.append(id)
                    return next(rest.dropFirst(), note)
                }
                if let self, self.playerJob == id {
                    self.player?.stop()
                    self.player = nil
                    self.playerTick?.invalidate()
                    self.tellPlayer()
                }
                do { try FileManager.default.trashItem(at: dir, resultingItemURL: nil) }
                catch { return done(true, ["done": through, "message": error.localizedDescription]) }
                through.append(id)
                var why = note
                for url in (answer["trash"] as? [String] ?? []).map({ URL(fileURLWithPath: $0) }) {
                    do { try FileManager.default.trashItem(at: url, resultingItemURL: nil) }
                    catch { if why.isEmpty { why = error.localizedDescription } }
                }
                next(rest.dropFirst(), why)
            }
        }
        next(ids[...], "")
    }

    func tellPlayer() {
        guard let p = player else { return event("player", ["pos": 0, "dur": 0, "playing": false]) }
        event("player", ["pos": p.currentTime, "dur": p.duration, "playing": p.isPlaying, "rate": p.rate])
    }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) { tellPlayer() }

    // MARK: the Google Doc in the middle of the window

    /// The page says where the Doc goes (CSS pixels from the top left of the window) and which Doc; or hides it,
    /// for a meeting without one, while it loads, or while a sheet (the mail, the transcript) covers that place.
    func placeDoc(_ args: [String: Any]) {
        let text = args["url"] as? String ?? ""
        guard args["show"] as? Bool ?? false, let url = URL(string: text), url.scheme == "https",
              url.host == "docs.google.com", url.path.hasPrefix("/document/d/") else {
            docWanted = false
            docView?.isHidden = true
            return
        }
        let n = { (key: String) in CGFloat((args[key] as? NSNumber)?.doubleValue ?? 0) }
        let view = docView ?? makeDocView()
        view.frame = NSRect(x: n("x"), y: n("y"), width: max(n("w"), 0), height: max(n("h"), 0))
        docWanted = true
        if text != docURL {
            // the Doc opens with the Google account the app itself uses, whichever others the user signed in to
            var parts = URLComponents(url: url, resolvingAgainstBaseURL: false)
            let account = args["account"] as? String ?? ""
            if !account.isEmpty {
                let items = (parts?.queryItems ?? []).filter { $0.name != "authuser" }
                parts?.queryItems = items + [URLQueryItem(name: "authuser", value: account)]
            }
            docURL = text
            docReady = false                                 // the last meeting's Doc stays out of sight meanwhile
            view.load(URLRequest(url: parts?.url ?? url))
        } else if args["reload"] as? Bool ?? false {
            docReady = false
            view.reload()
        }
        view.isHidden = !docReady
    }

    func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
        guard webView === docView else { return }
        docReady = true
        webView.isHidden = !docWanted
        if blinkWaiting && webView.url?.host == "docs.google.com" { blinkDoc() }   // not the Google sign-in page
    }

    // MARK: 環境設定自檢

    /// Items 1 and 2 (the microphone and notifications) from macOS, the other eight from setup_check.py.
    func setupState(progress: Bool = false, _ done: @escaping (Bool, Any) -> Void) {
        let mic: String
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: mic = "done"
        case .notDetermined: mic = "todo"
        default: mic = "denied"
        }
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            let notify: String
            switch settings.authorizationStatus {
            case .authorized, .provisional, .ephemeral: notify = "done"
            case .notDetermined: notify = "todo"
            default: notify = "denied"
            }
            DispatchQueue.main.async {
                self.setupScript(["status"] + (progress ? ["--progress"] : [])) { ok, data in
                    guard ok, var all = data as? [String: Any] else { return done(ok, data) }
                    if ((all["ai"] as? [String: Any])?["state"] as? String) == "done" {
                        self.owner?.aiWarned = false             // set up while recording: the panel's note goes
                    }
                    all["mic"] = ["state": mic]
                    all["notify"] = ["state": notify]
                    done(true, all)
                }
            }
        }
    }

    func setupScript(_ args: [String], _ done: @escaping (Bool, Any) -> Void) {
        guard let owner else { return done(false, ["message": tr("err.quitting")]) }
        owner.runScript("setup_check.py", args) { code, out in
            if code == 0, let obj = lastObject(out, prefix: "JSON ") { return done(true, obj) }
            let why = lastLine(out)
            done(false, ["message": why.isEmpty || why.hasPrefix("JSON ") ? tr("err.tryAgain") : why])
        }
    }

    func openSettings(_ address: String) {
        if let url = URL(string: address) { NSWorkspace.shared.open(url) }
    }

    /// 登入 for the chosen AI: its own sign-in, in a Terminal window (each one asks in the terminal or the browser).
    func aiLogin(_ key: String) {
        let commands = ["claude": ("Claude Code", "claude auth login"), "codex": ("Codex", "codex login"),
                        "antigravity": ("Antigravity", "agy")]
        guard let (name, command) = commands[key] else { return }
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(tr("signin.title", name) + ".command")
        // an AI the checklist just installed sits in ~/.local/bin, which a new Mac's shell does not search (the same
        // folders ai_runner.py looks in); setup-ai-login-done tells the checklist the sign-in command has ended
        let marker = configDir.appendingPathComponent("setup-ai-login-done")
        try? FileManager.default.removeItem(at: marker)
        let path = "export PATH=\"$HOME/.local/bin:$HOME/.claude/local:/opt/homebrew/bin:/usr/local/bin:$HOME/.npm-global/bin:$PATH\""
        let script = "#!/bin/zsh -l\n\(path)\necho \(shellQuoted(tr("signin.title", name)))\n\(command)\n"
            + "touch \(shellQuoted(marker.path))\necho\necho \(shellQuoted(tr("signin.done")))\n"
        do {
            try script.write(to: file, atomically: true, encoding: .utf8)
            try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: file.path)
            NSWorkspace.shared.open(file)
        } catch {
            NSSound.beep()
        }
    }

    /// The OAuth client JSON the user downloaded from Google Cloud (item 6).
    func pickClient(_ done: @escaping (Bool, Any) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.allowedContentTypes = [.json]
        panel.directoryURL = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
        panel.message = tr("panel.client")
        panel.prompt = tr("panel.useFile")
        panel.beginSheetModal(for: window) { [weak self] answer in
            guard answer == .OK, let url = panel.url else { return done(true, ["cancelled": true]) }
            self?.setupScript(["client", url.path], done)
        }
    }

    /// The ＋ (上傳檔案) and picture buttons under the Doc: the files the user picks, as {path, name}.
    func pickFiles(images: Bool, _ done: @escaping (Bool, Any) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        if images { panel.allowedContentTypes = [.png, .jpeg, .gif, .heic, .webP, .tiff, .bmp] }
        panel.message = images ? tr("panel.images") : tr("panel.files")
        panel.prompt = tr("panel.add")
        panel.beginSheetModal(for: window) { [weak self] answer in
            guard answer == .OK else { return done(true, ["files": []]) }
            let files = panel.urls.map { url -> [String: String] in
                self?.picked.insert(url.path)
                return ["path": url.path, "name": url.lastPathComponent]
            }
            done(true, ["files": files])
        }
    }

    /// ⌘V in the box under the Doc: the pictures on the clipboard, as {path, name}, like the picture button's. Picture
    /// files copied in Finder are used where they are; a picture itself (a screenshot, an image copied from a page) is
    /// saved as a PNG in the temporary folder first. Nothing else on the clipboard is read.
    func pastedPictures(_ done: @escaping (Bool, Any) -> Void) {
        let board = NSPasteboard.general
        let urls = board.readObjects(forClasses: [NSURL.self],
                                     options: [.urlReadingFileURLsOnly: true,
                                               .urlReadingContentsConformToTypes: [UTType.image.identifier]]) as? [URL] ?? []
        if !urls.isEmpty {
            for url in urls { picked.insert(url.path) }
            appLog("pasted \(urls.count) picture file(s)")
            return done(true, ["files": urls.map { ["path": $0.path, "name": $0.lastPathComponent] }])
        }
        // text copied in Excel, Word or Keynote comes with a picture of itself: when the text is what was copied
        // (it comes first), it pastes as text; a screenshot or "Copy Image" has the picture first
        let first = board.pasteboardItems?.first?.types.first.flatMap { UTType($0.rawValue) }
        if let text = board.string(forType: .string), !text.isEmpty, !(first?.conforms(to: .image) ?? false) {
            return done(true, ["files": []])
        }
        let png = board.data(forType: .png)
        let image = png == nil ? NSImage(pasteboard: board) : nil
        guard png != nil || image != nil else { return done(true, ["files": []]) }
        let name = tr("paste.name")
        // a big picture takes a moment to become a PNG: not on the main thread, where the window would stop
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let data = png ?? image.flatMap { $0.tiffRepresentation }.flatMap { NSBitmapImageRep(data: $0) }
                .flatMap { $0.representation(using: .png, properties: [:]) }
            let folder = FileManager.default.temporaryDirectory.appendingPathComponent("Vinutes pasted", isDirectory: true)
            let fmt = DateFormatter()
            fmt.locale = Locale(identifier: "en_US_POSIX")
            fmt.calendar = Calendar(identifier: .gregorian)
            fmt.dateFormat = "yyyy-MM-dd HH.mm.ss"
            let stamp = fmt.string(from: Date())
            var url = folder.appendingPathComponent("\(name) \(stamp).png")
            var n = 2
            while FileManager.default.fileExists(atPath: url.path) {      // two pastes in the same second
                url = folder.appendingPathComponent("\(name) \(stamp) \(n).png")
                n += 1
            }
            var saved = false
            if let data {
                do {
                    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                    try data.write(to: url)
                    saved = true
                } catch { appLog("pasted picture not saved: \(error.localizedDescription)") }
            }
            DispatchQueue.main.async {
                guard saved else { return done(false, ["message": tr("err.pasteFailed")]) }
                self?.picked.insert(url.path)
                appLog("pasted a picture, \(data?.count ?? 0) bytes")
                done(true, ["files": [["path": url.path, "name": url.lastPathComponent]]])
            }
        }
    }

    /// Every [__] in the Doc blinks three times (Resources/app/docblink.js): on opening a meeting, and after a
    /// 待補充 item moved the Doc to its place. A Doc still loading blinks once it shows.
    func blinkDoc() {
        guard let view = docView, docWanted, let file = appDir?.appendingPathComponent("docblink.js"),
              let code = try? String(contentsOf: file, encoding: .utf8) else { return }
        guard docReady else { blinkWaiting = true; return }
        blinkWaiting = false
        view.callAsyncJavaScript(code, arguments: [:], in: nil, in: .page) { _ in }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        docFailed(webView, error)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        docFailed(webView, error)
    }

    /// The Doc did not load (no network, Google down): the page shows the minutes as this computer has them.
    func docFailed(_ webView: WKWebView, _ error: Error) {
        guard webView === docView, (error as NSError).code != NSURLErrorCancelled else { return }
        webView.isHidden = true
        docURL = ""
        blinkWaiting = false
        event("docfail")
    }

    /// Moves the Doc to the first place holding `words` and selects it, the way 編輯 > 尋找並取代 would, with
    /// Google's menu and dialog kept out of sight (Resources/app/docfind.js). When Google's page does not answer
    /// that way any more, the Doc scrolls to about as far down as those words are.
    func findInDoc(_ dir: URL, _ words: String, _ done: @escaping (Bool, Any) -> Void) {
        guard let view = docView, !view.isHidden, docReady, !words.isEmpty,
              let file = appDir?.appendingPathComponent("docfind.js"),
              let code = try? String(contentsOf: file, encoding: .utf8) else { return done(true, ["found": false]) }
        view.callAsyncJavaScript(code, arguments: ["words": words], in: nil, in: .page) { [weak self] result in
            if case .success(let value) = result, value as? String == "found" { return done(true, ["found": true]) }
            self?.app(["locate", dir.path, words]) { ok, data in
                guard ok, let at = ((data as? [String: Any])?["at"] as? NSNumber)?.doubleValue else {
                    return done(true, ["found": false])
                }
                let scroll = """
                    const all = [...document.querySelectorAll('div')].filter((e) => e.scrollHeight > e.clientHeight + 200
                      && /auto|scroll/.test(getComputedStyle(e).overflowY));
                    const box = document.querySelector('.kix-appview-editor')
                      || all.sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
                    if (box) box.scrollTop = Math.max(0, at * box.scrollHeight - box.clientHeight / 3);
                    """
                view.callAsyncJavaScript(scroll, arguments: ["at": at], in: nil, in: .page) { _ in
                    done(true, ["found": true])
                }
            }
        }
    }

    func makeDocView() -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()                 // the Google sign-in is kept between launches
        let view = WKWebView(frame: .zero, configuration: config)
        // Google Docs draws the page at a quarter of its resolution for a web view that calls itself Safari, and
        // sharp for Chrome; typing, the input methods and the toolbar work the same either way. The version keeps
        // up with Chrome's (one every four weeks since 140 on 2025-09-02), so Docs never calls the browser too old.
        let weeks = Date().timeIntervalSince(Date(timeIntervalSince1970: 1_756_771_200)) / (7 * 86_400)
        let chrome = 140 + max(0, Int(weeks / 4) - 1)
        view.customUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
            + "Chrome/\(chrome).0.0.0 Safari/537.36"
        view.navigationDelegate = self
        view.uiDelegate = self
        view.autoresizingMask = [.width, .height]          // grows with the window until the page measures again
        window.contentView?.addSubview(view)
        docView = view
        return view
    }

    /// In the Doc: Google's own pages stay (this Doc, signing in, the frames Docs runs inside itself); a link to
    /// anything else, another Doc included, opens in the browser.
    func docPolicy(_ action: WKNavigationAction) -> WKNavigationActionPolicy {
        guard let url = action.request.url else { return .cancel }
        if action.targetFrame?.isMainFrame == false { return .allow }
        let host = url.host ?? ""
        let google = url.scheme == "https" && (host == "google.com" || host.hasSuffix(".google.com"))
        // /document/d/<id>/… or, with an account picked, /document/u/<n>/d/<id>/…
        let id = { (u: URL) -> String in
            let p = u.path.split(separator: "/").map(String.init)
            guard let d = p.firstIndex(of: "d"), p.first == "document", d + 1 < p.count else { return "" }
            return p[d + 1]
        }
        let mine = host == "docs.google.com" && !id(url).isEmpty && id(url) == URL(string: docURL).map(id)
        if action.navigationType != .linkActivated && google { return .allow }
        if mine || host == "accounts.google.com" { return .allow }
        if action.navigationType == .linkActivated, ["https", "http"].contains(url.scheme ?? "") {
            NSWorkspace.shared.open(url)
        }
        return .cancel
    }

    /// 插入 > 圖片 > 從電腦上傳, and any other file the Doc asks for.
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = false
        panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url, ["https", "http"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: tr("btn.ok"))
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: tr("btn.ok"))
        alert.addButton(withTitle: tr("btn.cancel"))
        alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    // MARK: the page itself

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if webView === docView { return decisionHandler(docPolicy(action)) }
        // only the window's own page loads here; a link in the minutes opens in the browser
        // (both sides standardized: macOS drops a leading /private from one and not the other)
        if let url = action.request.url, url.isFileURL, let appDir,
           url.standardizedFileURL.path.hasPrefix(appDir.standardizedFileURL.path) {
            return decisionHandler(.allow)
        }
        if action.navigationType == .linkActivated, let url = action.request.url, url.scheme == "https" {
            NSWorkspace.shared.open(url)
        }
        decisionHandler(.cancel)
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        if webView !== docView { loaded = false }
        webView.reload()
    }

    // MARK: closing

    /// Calls back once the page has saved what was typed and handed the user's edits to `learn`.
    /// what waits for the page to save before the window closes or the app quits
    var closing_: [() -> Void] = []

    func finish(_ done: @escaping () -> Void) {
        var called = false
        let once = { if !called { called = true; done() } }
        closing_.append(once)
        // the page says it is done through the "app" handler; no completion block here, since WebKit's Swift wrapper
        // for one crashed the app while it was quitting (2026-10-17)
        web.evaluateJavaScript("Promise.resolve(window.beforeClose && window.beforeClose()).catch(() => {})"
                               + ".then(() => window.webkit.messageHandlers.app.postMessage({id: -1, cmd: 'closed'}))",
                               completionHandler: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 20) { once() }       // a stuck save must not keep the app open
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if closing { return true }
        closing = true
        finish { self.window.close() }
        return false
    }

    func windowWillClose(_ notification: Notification) {
        player?.stop()
        playerTick?.invalidate()
        owner?.managerClosed()
    }
}


#if SNAPSHOT
// For development only:  swiftc -D SNAPSHOT -swift-version 5 MeetingRecorder.swift, inside an .app with Resources/app.
// <app>/Contents/MacOS/MeetingRecorder <job id> <out.png> [light|dark] opens the meeting window on that job, waits
// for it to load and saves what the window shows.
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
app.appearance = NSAppearance(named: CommandLine.arguments.count > 3 && CommandLine.arguments[3] == "dark" ? .darkAqua : .aqua)
let delegate = AppDelegate()
delegate.showManager(select: CommandLine.arguments[1])
DispatchQueue.main.asyncAfter(deadline: .now() + 12) {
    delegate.manager?.web.evaluateJavaScript("location.href + ' | ' + document.body.innerText.slice(0, 300)") { value, error in
        print("PAGE", value ?? "", error ?? "")
    }
}
DispatchQueue.main.asyncAfter(deadline: .now() + 13) {
    delegate.manager?.web.takeSnapshot(with: nil) { image, _ in
        if let tiff = image?.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
            try? png.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
        }
        exit(0)
    }
}
app.run()
#else
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
#endif
