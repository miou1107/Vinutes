// The panel under the menu-bar icon (2026-10-18, after the prototype Vin picked): a large round button that
// starts the recording (red, a white dot) and, while recording, stops it (white, red ring, a red square); under it
// how long the recording runs with the level bars, and pause (no discard here: Vin was afraid of hitting it by
// mistake; a wrong recording is deleted from the meeting list); the last three meetings; All meetings, Usage (用量統計,
// Vin 2026-10-19), Settings and Quit in equal quarters; the version, with an update button when GitHub has a newer one. A recording started while
// the AI is not set up shows a yellow note under the controls, with a button to the setup (Vin 2026-10-19).
import AppKit

final class MenuPanel: NSObject, NSPopoverDelegate {
    weak var owner: AppDelegate?
    let popover = NSPopover()
    let bars = LevelBars(frame: NSRect(x: 0, y: 0, width: 23, height: 18))
    private let round = RoundButton()
    private let label = NSTextField(labelWithString: "")
    private let hint = NSTextField(labelWithString: "")
    private let labelRow = NSStackView()
    private let controls = NSStackView()
    private let pause = NSButton()
    private let aiNote = NSStackView()
    private let recent = NSStackView()
    private let versionRow = NSStackView()
    private let version = NSTextField(labelWithString: "")
    private let update = NSButton()
    private var newest = ""
    private var builtLanguage = ""
    private var closedAt = Date.distantPast
    var isShown: Bool { popover.isShown }

    init(owner: AppDelegate) {
        self.owner = owner
        super.init()
        popover.behavior = .transient            // a click anywhere else closes it, like a menu
        popover.animates = false
        popover.delegate = self
        popover.contentViewController = NSViewController()
        rebuild()
    }

    /// The words are written when the panel is built, so a new app language builds it again.
    private func rebuild() {
        builtLanguage = uiLanguage()
        recentKey = nil
        popover.contentViewController?.view = build()
    }

    // MARK: layout

    private func build() -> NSView {
        let root = NSStackView()
        root.orientation = .vertical
        root.spacing = 0
        root.alignment = .centerX
        root.edgeInsets = NSEdgeInsets(top: 0, left: 0, bottom: 0, right: 0)
        root.translatesAutoresizingMaskIntoConstraints = false
        root.widthAnchor.constraint(equalToConstant: 300).isActive = true

        round.onClick = { [weak self] in self?.roundClicked() }
        label.font = .monospacedDigitSystemFont(ofSize: 14, weight: .semibold)
        hint.font = .systemFont(ofSize: 12)
        hint.textColor = .secondaryLabelColor
        labelRow.orientation = .horizontal
        labelRow.spacing = 8
        labelRow.addArrangedSubview(bars)
        labelRow.addArrangedSubview(label)
        pause.bezelStyle = .rounded
        pause.controlSize = .large
        pause.target = self
        pause.action = #selector(pauseClicked)
        pause.refusesFirstResponder = true          // no blue focus ring around it when the panel opens
        controls.orientation = .horizontal
        controls.spacing = 8
        controls.addArrangedSubview(pause)

        let top = NSStackView(views: [round, labelRow, hint, controls])
        top.orientation = .vertical
        top.alignment = .centerX
        top.spacing = 6
        top.setCustomSpacing(10, after: round)
        top.setCustomSpacing(10, after: hint)
        top.edgeInsets = NSEdgeInsets(top: 16, left: 16, bottom: 14, right: 16)
        root.addArrangedSubview(top)
        root.addArrangedSubview(buildAiNote())

        root.addArrangedSubview(line())
        recent.orientation = .vertical
        recent.alignment = .leading
        recent.spacing = 0
        recent.edgeInsets = NSEdgeInsets(top: 6, left: 5, bottom: 6, right: 5)
        root.addArrangedSubview(recent)
        recent.widthAnchor.constraint(equalTo: root.widthAnchor).isActive = true

        root.addArrangedSubview(line())
        let foot = NSStackView()
        foot.orientation = .horizontal
        foot.distribution = .fillEqually          // four equal quarters, whatever each label's length
        foot.spacing = 4
        foot.edgeInsets = NSEdgeInsets(top: 6, left: 6, bottom: 4, right: 6)
        foot.addArrangedSubview(FootButton(symbol: "list.bullet", title: tr("panel.all")) { [weak self] in
            self?.close(); self?.owner?.showAll() })
        foot.addArrangedSubview(FootButton(symbol: "chart.bar", title: tr("panel.usage")) { [weak self] in
            self?.close(); self?.owner?.showUsage() })
        foot.addArrangedSubview(FootButton(symbol: "gearshape", title: tr("menu.settings"), view: { [weak self] view in
            self?.showSettings(from: view) }))
        foot.addArrangedSubview(FootButton(symbol: "power", title: tr("panel.quit")) { [weak self] in
            self?.close(); self?.owner?.quit() })
        root.addArrangedSubview(foot)
        foot.widthAnchor.constraint(equalTo: root.widthAnchor).isActive = true

        version.font = .systemFont(ofSize: 11)
        version.textColor = .secondaryLabelColor
        update.bezelStyle = .rounded
        update.controlSize = .small
        update.bezelColor = .controlAccentColor
        update.target = self
        update.action = #selector(updateClicked)
        versionRow.orientation = .horizontal
        versionRow.spacing = 8
        versionRow.edgeInsets = NSEdgeInsets(top: 2, left: 10, bottom: 10, right: 10)
        versionRow.addArrangedSubview(version)
        versionRow.addArrangedSubview(update)
        root.addArrangedSubview(versionRow)
        return root
    }

    /// 注意！ 內容生成模型尚未設定 / 需先完成 AI 設定，才能自動生成會議記錄 / 前往設定 (the prototype's words)
    private func buildAiNote() -> NSView {
        let box = NSStackView()
        box.orientation = .vertical
        box.alignment = .leading
        box.spacing = 4
        box.edgeInsets = NSEdgeInsets(top: 10, left: 12, bottom: 10, right: 12)
        box.wantsLayer = true
        box.layer?.cornerRadius = 8
        box.layer?.backgroundColor = NSColor.systemYellow.withAlphaComponent(0.2).cgColor
        let title = NSTextField(wrappingLabelWithString: tr("panel.aiTitle"))
        title.font = .systemFont(ofSize: 12, weight: .semibold)
        let text = NSTextField(wrappingLabelWithString: tr("panel.aiText"))
        text.font = .systemFont(ofSize: 12)
        [title, text].forEach { $0.preferredMaxLayoutWidth = 244 }
        let go = NSButton(title: tr("panel.aiSetup"), target: self, action: #selector(aiSetupClicked))
        go.bezelStyle = .rounded
        go.controlSize = .small
        go.refusesFirstResponder = true
        [title, text, go].forEach { box.addArrangedSubview($0) }
        box.setCustomSpacing(8, after: text)                 // only once the text is in the stack
        box.widthAnchor.constraint(equalToConstant: 268).isActive = true
        aiNote.orientation = .vertical
        aiNote.edgeInsets = NSEdgeInsets(top: 0, left: 16, bottom: 14, right: 16)
        aiNote.addArrangedSubview(box)
        aiNote.isHidden = true
        return aiNote
    }

    private func line() -> NSView {
        let box = NSBox()
        box.boxType = .separator
        box.translatesAutoresizingMaskIntoConstraints = false
        box.widthAnchor.constraint(equalToConstant: 300).isActive = true
        return box
    }

    // MARK: showing

    func toggle(from button: NSStatusBarButton) {
        if popover.isShown { return close() }
        // a click on the icon while the panel is open closes it on mouse down; the same click's mouse up must not
        // open it again
        if Date().timeIntervalSince(closedAt) < 0.3 { return }
        if builtLanguage != uiLanguage() { rebuild() }
        resetHover(popover.contentViewController?.view)
        refresh()
        checkVersion()
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        popover.contentViewController?.view.window?.makeKey()
    }

    func close() { if popover.isShown { popover.performClose(nil) } }

    /// Drawn again when it opens and every second while it is open (the recording's time, a meeting finished).
    func refresh() {
        guard let owner else { return }
        let rec = owner.recording
        round.recording = rec
        round.setAccessibilityLabel(rec ? tr("menu.stop") : tr("menu.start"))
        bars.isHidden = !rec
        if rec {
            label.stringValue = clock(owner.elapsed)
            label.textColor = owner.paused ? .secondaryLabelColor : .labelColor
            hint.stringValue = owner.paused ? tr("tip.paused") : tr("panel.stopHint")
            pause.title = owner.paused ? tr("panel.resume") : tr("menu.pause")
            pause.image = symbol(owner.paused ? "play.fill" : "pause.fill", 12, .semibold)
            pause.imagePosition = .imageLeading
            if owner.paused { bars.show(level: 0, paused: true) }
        } else {
            label.stringValue = tr("menu.start")
            label.textColor = .labelColor
            hint.stringValue = "⌃⌥R"
        }
        controls.isHidden = !rec
        aiNote.isHidden = !(rec && owner.aiWarned)

        // the meeting being recorded is not a recent meeting yet (compared by folder name: the two URLs can differ
        // by a trailing slash)
        let current = owner.currentJob?.lastPathComponent
        let jobs = owner.recentJobs(limit: 40).filter { $0.name != current && !$0.archived }.prefix(3)
        let key = jobs.map { "\($0.name) \($0.step) \($0.title) \($0.sent)" }.joined(separator: "|")
        if key != recentKey { recentKey = key; fillRecent(Array(jobs)) }
        refreshVersion(recording: rec)
    }

    private var recentKey: String?

    private func fillRecent(_ jobs: [Job]) {
        guard let owner else { return }
        recent.arrangedSubviews.forEach { $0.removeFromSuperview() }
        let head = NSTextField(labelWithString: tr("menu.recent"))
        head.font = .systemFont(ofSize: 11, weight: .semibold)
        head.textColor = .secondaryLabelColor
        let headWrap = NSStackView(views: [head])
        headWrap.edgeInsets = NSEdgeInsets(top: 2, left: 8, bottom: 2, right: 8)
        recent.addArrangedSubview(headWrap)
        if jobs.isEmpty {
            let none = NSTextField(labelWithString: tr("menu.none"))
            none.textColor = .secondaryLabelColor
            let wrap = NSStackView(views: [none])
            wrap.edgeInsets = NSEdgeInsets(top: 3, left: 8, bottom: 3, right: 8)
            recent.addArrangedSubview(wrap)
        }
        for job in jobs {
            let name = job.step == "done" ? job.title : owner.stateText(job)
            let row = MeetingRow(symbol: owner.stateSymbol(job), when: job.label, title: name) { [weak self] in
                self?.close(); self?.owner?.openJob(job.dir) }
            recent.addArrangedSubview(row)
            row.widthAnchor.constraint(equalTo: recent.widthAnchor, constant: -10).isActive = true
        }
    }

    private func refreshVersion(recording rec: Bool) {
        let mine = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
        version.stringValue = "Vinutes \(mine)"
        let offer = !newest.isEmpty && !rec           // never while recording: updating quits the app
        update.isHidden = !offer
        update.title = tr("panel.update", newest)
        versionRow.alignment = .centerY
        versionRow.distribution = offer ? .equalSpacing : .gravityAreas
        versionRow.setHuggingPriority(.defaultLow, for: .horizontal)
    }

    /// The level bars jump with the microphone, as on the floating bar.
    func listen(level: CGFloat, paused: Bool) {
        guard popover.isShown else { return }
        bars.show(level: level, paused: paused)
    }

    /// Whether GitHub has a newer version: the same check the meeting window's corner uses (at most once an hour).
    private func checkVersion() {
        let mine = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
        owner?.runScript("minutes_app.py", ["version", mine]) { [weak self] code, out in
            guard let self, code == 0, let obj = lastObject(out, prefix: "JSON ") else { return }
            self.newest = (obj["update"] as? Bool ?? false) ? (obj["newest"] as? String ?? "") : ""
            self.refreshVersion(recording: self.owner?.recording ?? false)
        }
    }

    // MARK: actions

    private func roundClicked() {
        guard let owner else { return }
        close()
        owner.recording ? owner.stopRecording() : owner.startRecording()
    }

    @objc private func pauseClicked() { owner?.togglePause() }     // togglePause redraws the panel

    @objc private func aiSetupClicked() {
        close()
        owner?.openSetup()
    }

    @objc private func updateClicked() {
        guard let owner, !owner.recording else { return }
        close()
        owner.updateApp()
    }

    /// Settings opens from its button: the setup checklist, open at login, the two languages, the recordings folder.
    /// The menu waits for a choice; whatever was picked, the panel closes after it.
    private func showSettings(from view: NSView) {
        guard let owner else { return }
        let menu = owner.settingsMenu()
        menu.popUp(positioning: nil, at: NSPoint(x: 0, y: view.bounds.height + 4), in: view)
        resetHover(view)
        close()
    }

    /// A clicked control loses the pointer without a mouse-exited when the panel closes under it.
    private func resetHover(_ view: NSView?) {
        guard let view else { return }
        (view as? Hovering)?.hover = false
        view.subviews.forEach(resetHover)
    }

    func popoverDidClose(_ notification: Notification) {
        closedAt = Date()
        owner?.refreshIcon()
    }
}

protocol Hovering: AnyObject { var hover: Bool { get set } }

/// The big round button: red with a white dot to start; white with a red ring and a red square while recording.
final class RoundButton: NSView, Hovering {
    var onClick: (() -> Void)?
    var recording = false { didSet { needsDisplay = true } }
    var hover = false { didSet { needsDisplay = true; if !hover { down = false } } }
    private var down = false { didSet { needsDisplay = true } }
    private let size: CGFloat = 62           // a third smaller than the prototype's 92 (Vin)

    override init(frame: NSRect) {
        super.init(frame: frame)
        translatesAutoresizingMaskIntoConstraints = false
        widthAnchor.constraint(equalToConstant: size + 10).isActive = true
        heightAnchor.constraint(equalToConstant: size + 10).isActive = true
        setAccessibilityElement(true)
        setAccessibilityRole(.button)
        addTrackingArea(NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                                       owner: self))
    }
    convenience init() { self.init(frame: .zero) }
    required init?(coder: NSCoder) { fatalError() }

    override func draw(_ dirty: NSRect) {
        let circle = NSRect(x: (bounds.width - size) / 2, y: (bounds.height - size) / 2, width: size, height: size)
        let red = NSColor(srgbRed: 0.90, green: 0.22, blue: 0.23, alpha: 1)
        let shadow = NSShadow()
        shadow.shadowBlurRadius = 10
        shadow.shadowOffset = NSSize(width: 0, height: -3)
        shadow.shadowColor = (recording ? NSColor.black.withAlphaComponent(0.18) : red.withAlphaComponent(0.35))
        NSGraphicsContext.saveGraphicsState()
        shadow.set()
        let path = NSBezierPath(ovalIn: circle.insetBy(dx: recording ? 2 : 0, dy: recording ? 2 : 0))
        if recording {
            NSColor(white: hover || down ? 0.95 : 1, alpha: 1).setFill()
            path.fill()
        } else {
            (hover || down ? red.blended(withFraction: 0.15, of: .black) ?? red : red).setFill()
            path.fill()
        }
        NSGraphicsContext.restoreGraphicsState()
        if recording {
            red.setStroke()
            path.lineWidth = 3.5
            path.stroke()
            let s: CGFloat = 19
            red.setFill()
            NSBezierPath(roundedRect: NSRect(x: circle.midX - s / 2, y: circle.midY - s / 2, width: s, height: s),
                         xRadius: 4, yRadius: 4).fill()
        } else {
            let d: CGFloat = 20
            NSColor.white.setFill()
            NSBezierPath(ovalIn: NSRect(x: circle.midX - d / 2, y: circle.midY - d / 2, width: d, height: d)).fill()
        }
    }

    override func mouseEntered(with event: NSEvent) { hover = true }
    override func mouseExited(with event: NSEvent) { hover = false; down = false }
    override func mouseDown(with event: NSEvent) { down = true }
    override func mouseUp(with event: NSEvent) {
        let inside = bounds.contains(convert(event.locationInWindow, from: nil))
        down = false
        if inside { onClick?() }
    }
    override func accessibilityPerformPress() -> Bool { onClick?(); return true }
}

/// One of the last meetings: a symbol, its date and time, its title; blue under the pointer, like a menu item.
final class MeetingRow: NSView, Hovering {
    private let onClick: () -> Void
    private let icon = NSImageView()
    private let when: NSTextField
    private let title: NSTextField
    var hover = false { didSet { needsDisplay = true; recolor() } }

    init(symbol name: String, when w: String, title t: String, onClick: @escaping () -> Void) {
        self.onClick = onClick
        when = NSTextField(labelWithString: w)
        title = NSTextField(labelWithString: t)
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        heightAnchor.constraint(equalToConstant: 24).isActive = true
        icon.image = symbol(name, 12)
        icon.widthAnchor.constraint(equalToConstant: 16).isActive = true     // envelope and tick line up the times
        when.font = .monospacedDigitSystemFont(ofSize: 13, weight: .regular)
        title.lineBreakMode = .byTruncatingTail
        title.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let row = NSStackView(views: [icon, when, title])
        row.spacing = 8
        row.translatesAutoresizingMaskIntoConstraints = false
        addSubview(row)
        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 8),
            row.trailingAnchor.constraint(lessThanOrEqualTo: trailingAnchor, constant: -8),
            row.centerYAnchor.constraint(equalTo: centerYAnchor),
        ])
        setAccessibilityElement(true)
        setAccessibilityRole(.button)
        setAccessibilityLabel("\(w) \(t)")
        addTrackingArea(NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                                       owner: self))
        recolor()
    }
    required init?(coder: NSCoder) { fatalError() }

    private func recolor() {
        when.textColor = hover ? .white : .secondaryLabelColor
        title.textColor = hover ? .white : .labelColor
        icon.contentTintColor = hover ? .white : .secondaryLabelColor
    }

    override func draw(_ dirty: NSRect) {
        guard hover else { return }
        NSColor.controlAccentColor.setFill()
        NSBezierPath(roundedRect: bounds, xRadius: 5, yRadius: 5).fill()
    }
    override func mouseEntered(with event: NSEvent) { hover = true }
    override func mouseExited(with event: NSEvent) { hover = false }
    // the labels inside must not take the click: the whole row is the button
    override func hitTest(_ point: NSPoint) -> NSView? { frame.contains(point) ? self : nil }
    override func mouseDown(with event: NSEvent) {}
    override func mouseUp(with event: NSEvent) {
        if bounds.contains(convert(event.locationInWindow, from: nil)) { hover = false; onClick() }
    }
    override func accessibilityPerformPress() -> Bool { onClick(); return true }
}

/// One third of the panel's bottom row: a symbol over a short word.
final class FootButton: NSView, Hovering {
    private var onClick: () -> Void = {}
    var onClickView: ((NSView) -> Void)?
    var hover = false { didSet { needsDisplay = true } }

    convenience init(symbol name: String, title: String, onClick: @escaping () -> Void) {
        self.init(symbol: name, title: title, view: { _ in onClick() })
    }

    init(symbol name: String, title: String, view onClick: @escaping (NSView) -> Void) {
        super.init(frame: .zero)
        self.onClickView = onClick
        translatesAutoresizingMaskIntoConstraints = false
        heightAnchor.constraint(equalToConstant: 42).isActive = true
        let icon = NSImageView(image: symbol(name, 14) ?? NSImage())
        icon.contentTintColor = .secondaryLabelColor
        let label = NSTextField(labelWithString: title)
        label.font = .systemFont(ofSize: 11)
        label.textColor = .secondaryLabelColor
        let col = NSStackView(views: [icon, label])
        col.orientation = .vertical
        col.spacing = 2
        col.translatesAutoresizingMaskIntoConstraints = false
        addSubview(col)
        NSLayoutConstraint.activate([col.centerXAnchor.constraint(equalTo: centerXAnchor),
                                     col.centerYAnchor.constraint(equalTo: centerYAnchor)])
        setAccessibilityElement(true)
        setAccessibilityRole(.button)
        setAccessibilityLabel(title)
        addTrackingArea(NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                                       owner: self))
    }
    required init?(coder: NSCoder) { fatalError() }

    override func draw(_ dirty: NSRect) {
        guard hover else { return }
        NSColor.quaternaryLabelColor.setFill()
        NSBezierPath(roundedRect: bounds, xRadius: 6, yRadius: 6).fill()
    }
    override func mouseEntered(with event: NSEvent) { hover = true }
    override func mouseExited(with event: NSEvent) { hover = false }
    override func hitTest(_ point: NSPoint) -> NSView? { frame.contains(point) ? self : nil }
    override func mouseDown(with event: NSEvent) {}
    override func mouseUp(with event: NSEvent) {
        if bounds.contains(convert(event.locationInWindow, from: nil)) { hover = false; onClickView?(self) }
    }
    override func accessibilityPerformPress() -> Bool { onClickView?(self); return true }
}
