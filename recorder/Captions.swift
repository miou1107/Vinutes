// VinutesCaptions: live captions for the meeting being recorded, in a process of its own.
//
//   VinutesCaptions <recording.caf> <locale>        e.g. ~/.../recordings/20261017-201734/錄音.caf zh-TW
//
// It reads the recording file as Vinutes' recorder writes it (16 kHz mono 16-bit PCM in CAF) and gives the new audio
// to Apple's on-device transcriber (macOS 26 and later); nothing leaves the Mac. Every change is one JSON line on
// stdout, which the app shows under the floating bar:
//   {"prev": "...", "done": "...", "hearing": "..."}   the sentence before, the latest finished words, words still heard
//   {"note": "listening" | "downloading" | "unsupported" | "failed"}
// It never writes the recording, so a crash here can't touch the meeting; the app stops it with SIGTERM, and it quits
// by itself when the app is gone. What it did goes to ~/Library/Logs/Vinutes/captions.log.
import AVFoundation
import Foundation
import Speech

/// Every step, with the time and this process's id: ~/Library/Logs/Vinutes/captions.log, at most 5 MB (+ one older)
func log(_ line: String) {
    let dir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/Vinutes")
    try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let file = dir.appendingPathComponent("captions.log")
    // past 5 MB the log becomes captions.log.1 (replacing the one before), as the app does with its own logs
    if let size = (try? FileManager.default.attributesOfItem(atPath: file.path))?[.size] as? Int, size > 5_000_000 {
        _ = rename(file.path, dir.appendingPathComponent("captions.log.1").path)   // one step, replacing the older
    }
    let stamp = ISO8601DateFormatter.string(from: Date(), timeZone: .current, formatOptions: [.withInternetDateTime, .withFractionalSeconds])
    let text = "[\(stamp)] captions[\(getpid())] \(line)\n"
    let fd = open(file.path, O_WRONLY | O_APPEND | O_CREAT, 0o644)      // appends whole lines, also beside the app's
    guard fd >= 0 else { return }
    _ = text.withCString { write(fd, $0, strlen($0)) }
    close(fd)
}

/// seconds of the recording given to the transcriber so far, to log how far behind the captions are
nonisolated(unsafe) var heardUpTo = 0.0
nonisolated(unsafe) var startedAt = 0.0

func say(_ object: [String: String]) {
    guard let data = try? JSONSerialization.data(withJSONObject: object) else { return }
    FileHandle.standardOutput.write(data + Data([10]))
}

/// Apple's Taiwanese captions come with a few characters converted wrongly from simplified ones (裏麵, 復雜)
func tidy(_ text: String) -> String {
    var t = text.replacingOccurrences(of: "裏", with: "裡")
    for (wrong, right) in [("復雜", "複雜"), ("麵對", "面對"), ("見麵", "見面"), ("畫麵", "畫面"), ("頁麵", "頁面"), ("麵試", "面試"),
                           ("方麵", "方面"), ("表麵", "表面"), ("全麵", "全面"), ("當麵", "當面"), ("版麵", "版面"), ("介麵", "介面")] {
        t = t.replacingOccurrences(of: wrong, with: right)
    }
    return t.replacingOccurrences(of: "(裡|上|下|前|後|外|對|這|那|正|反|背|側)麵", with: "$1面", options: .regularExpression)
        .trimmingCharacters(in: .whitespaces)
}

/// Where the samples begin in a CAF file: after the 'data' chunk's header and its 4-byte edit count.
func audioStart(_ head: Data) -> Int? {
    guard head.count >= 8, head.prefix(4) == Data("caff".utf8) else { return nil }
    var at = 8
    while at + 12 <= head.count {
        let type = String(decoding: head[at..<at + 4], as: UTF8.self)
        let size = head[at + 4..<at + 12].reduce(UInt64(0)) { $0 << 8 | UInt64($1) }
        if type == "data" { return at + 12 + 4 }
        if size >= UInt64(Int.max / 2) { return nil }                // -1 (still growing) or a broken header
        at += 12 + Int(size)
    }
    return nil
}

/// The recording's audio as it grows, every 0.15 s, as buffers in the transcriber's format. It starts 2 s before the
/// end of what is recorded so far (captions turned on mid-meeting don't replay the meeting) and sends at most 1 s
/// at a time.
@available(macOS 26.0, *)
func follow(_ path: String, into feed: AsyncStream<AnalyzerInput>.Continuation, as format: AVAudioFormat) async {
    let source = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true)!
    let converter = source == format ? nil : AVAudioConverter(from: source, to: format)
    var start: Int?
    var offset = 0
    var sent = 0
    log("reading \(path) as \(source), giving \(format)\(converter == nil ? "" : " through a converter")")
    while !Task.isCancelled {
        guard let file = FileHandle(forReadingAtPath: path) else {
            log("recording file not readable yet: \(path)")
            try? await Task.sleep(for: .milliseconds(300))
            continue
        }
        defer { try? file.close() }
        if start == nil {
            let head = (try? file.read(upToCount: 65536)) ?? Data()
            start = audioStart(head)
            if let start, let end = try? file.seekToEnd() {
                offset = max(start, start + (Int(end) - start - 64000) / 2 * 2)
                startedAt = 0
                heardUpTo = Double(offset - start) / 32000
            }
            log(start.map { "audio starts at byte \($0), reading from byte \(offset)" } ?? "no audio yet in \(head.count) bytes of header")
        }
        if start != nil, let end = try? file.seekToEnd(), Int(end) - offset >= 2 {
            let bytes = min(32000, (Int(end) - offset) / 2 * 2)
            try? file.seek(toOffset: UInt64(offset))
            if let data = try? file.read(upToCount: bytes), data.count >= 2,
               let buffer = AVAudioPCMBuffer(pcmFormat: source, frameCapacity: AVAudioFrameCount(data.count / 2)) {
                buffer.frameLength = AVAudioFrameCount(data.count / 2)
                data.withUnsafeBytes { raw in
                    buffer.int16ChannelData![0].update(from: raw.bindMemory(to: Int16.self).baseAddress!, count: data.count / 2)
                }
                offset += data.count / 2 * 2
                heardUpTo = Double(offset - (start ?? 0)) / 32000 + startedAt
                if let converter {
                    let room = AVAudioFrameCount(Double(buffer.frameLength) * format.sampleRate / 16000) + 64
                    if let out = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: room) {
                        var given = false
                        _ = converter.convert(to: out, error: nil) { _, status in
                            if given { status.pointee = .noDataNow; return nil }
                            given = true
                            status.pointee = .haveData
                            return buffer
                        }
                        feed.yield(AnalyzerInput(buffer: out))
                    } else { log("could not make a converted buffer") }
                } else {
                    feed.yield(AnalyzerInput(buffer: buffer))
                }
                sent += 1
                if sent == 1 || sent % 400 == 0 { log("audio \(sent) chunks, \(offset) bytes") }
            }
        }
        try? await Task.sleep(for: .milliseconds(150))
    }
    log("stopped reading after \(sent) chunks")
}

@main
struct Captions {
    static func main() async {
        let args = CommandLine.arguments
        guard args.count == 3 else {
            FileHandle.standardError.write(Data("usage: VinutesCaptions <recording.caf> <locale>\n".utf8))
            exit(2)
        }
        let path = args[1], id = args[2]
        Thread.detachNewThread {                                   // the app is gone: so is this
            while true { if getppid() == 1 { log("the app is gone, quitting"); exit(0) }; sleep(1) }
        }
        guard #available(macOS 26.0, *) else { say(["note": "unsupported"]); exit(0) }
        log("start \(id) \(path)")
        say(["note": "listening"])
        do {
            let supported = await SpeechTranscriber.supportedLocales.map { $0.identifier(.bcp47) }
            let installed = await SpeechTranscriber.installedLocales.map { $0.identifier(.bcp47) }
            log("\(supported.count) languages supported, installed: \(installed.joined(separator: " "))")
            guard supported.contains(id) else {
                log("unsupported \(id)")
                say(["note": "unsupported"])
                return
            }
            // fastResults: words sooner, a little less accurate; CAPTIONS_FAST=0 turns it off to compare
            let fast = ProcessInfo.processInfo.environment["CAPTIONS_FAST"] != "0"
            let transcriber = SpeechTranscriber(locale: Locale(identifier: id), transcriptionOptions: [],
                                                reportingOptions: fast ? [.volatileResults, .fastResults] : [.volatileResults],
                                                attributeOptions: [.audioTimeRange])
            log(fast ? "fast results on" : "fast results off")
            if !installed.contains(id), let ask = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
                log("downloading the \(id) model")
                say(["note": "downloading"])
                try await ask.downloadAndInstall()
                log("downloaded")
                say(["note": "listening"])
            } else {
                log("\(id) model already on this Mac")
            }
            guard let format = await SpeechAnalyzer.bestAvailableAudioFormat(compatibleWith: [transcriber]) else {
                throw NSError(domain: "captions", code: 1, userInfo: [NSLocalizedDescriptionKey: "no audio format"])
            }
            log("transcriber wants \(format)")
            let analyzer = SpeechAnalyzer(modules: [transcriber])
            try await analyzer.prepareToAnalyze(in: format)          // loads the model now, not on the first words
            log("model loaded")
            let (stream, feed) = AsyncStream<AnalyzerInput>.makeStream()
            let reader = Task { await follow(path, into: feed, as: format) }
            log("starting the analyzer")
            try await analyzer.start(inputSequence: stream)
            log("analyzer started, waiting for words")
            var finished: [String] = []
            var finals = 0, partials = 0
            // one line, purple as soon as Apple hears the words (Vin 2026-10-17: the grey stage felt too slow, and the
            // sentence before is not needed); the app shows as much of the end as fits
            func line(_ text: String) -> String { String(text.suffix(60)) }   // the app fits it to its width
            for try await result in transcriber.results {
                let text = tidy(String(result.text.characters))
                if result.isFinal { finals += 1 } else { partials += 1 }
                // how far behind: the recording given so far minus where these words end
                let behind = heardUpTo - result.range.end.seconds
                if result.isFinal || finals + partials <= 3 || partials % 25 == 0 {
                    log(String(format: "words: %d finished, %d partial; %@ %d characters, %.1f s behind", finals, partials,
                               result.isFinal ? "finished" : "partial", text.count, behind))
                }
                if result.isFinal {
                    if !text.isEmpty { finished = Array((finished + [text]).suffix(2)) }
                    say(["prev": "", "done": line(finished.last ?? ""), "hearing": ""])
                } else if !text.isEmpty {
                    say(["prev": "", "done": line(text), "hearing": ""])
                }
            }
            log("transcriber ended after \(finals) finished lines")
            reader.cancel()
        } catch {
            log("failed \(error)")
            say(["note": "failed"])
        }
    }
}
