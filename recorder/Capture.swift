// What a recording hears: the microphone, and the sound the Mac plays (an online meeting's other side), mixed into
// the one 16 kHz mono 錄音.caf that the transcriber and the live captions read as it grows (Vinutes issue #3).
//
// The Mac's sound comes from a Core Audio process tap (macOS 14.2 and later) on every app but Vinutes itself, so
// a recording played back in the meeting window is not recorded again. The first time, macOS asks to allow
// "system audio recording"; refused, or on an older Mac, the tap gives silence and the recording is the microphone
// alone, as before. With headphones the other side is only in the tap; through the speakers the microphone hears
// it too, a few hundredths of a second later. Echo cancellation is left off on purpose: it would also weaken the
// voices of people sitting farther from the Mac in a room meeting.
import AVFoundation
import CoreAudio
import Foundation

/// Samples waiting to be mixed, in 16 kHz mono, from one source.
final class SampleQueue {
    private var samples: [Float] = []
    private let lock = NSLock()

    func push(_ buffer: AVAudioPCMBuffer) {
        guard let data = buffer.floatChannelData?[0] else { return }
        lock.lock()
        samples.append(contentsOf: UnsafeBufferPointer(start: data, count: Int(buffer.frameLength)))
        if samples.count > 8000 { samples.removeFirst(samples.count - 4000) }   // the two clocks drift: stay < 0.5 s apart
        lock.unlock()
    }

    /// up to `count` samples, the rest silence
    func take(_ count: Int) -> [Float] {
        lock.lock()
        defer { lock.unlock() }
        let n = min(count, samples.count)
        var out = Array(samples.prefix(n))
        samples.removeFirst(n)
        if n < count { out += [Float](repeating: 0, count: count - n) }
        return out
    }

    func clear() {
        lock.lock(); samples.removeAll(); lock.unlock()
    }
}

/// One audio format to another, for buffers that arrive one by one.
final class Resampler {
    let converter: AVAudioConverter
    let to: AVAudioFormat

    init?(from: AVAudioFormat, to: AVAudioFormat) {
        guard let c = AVAudioConverter(from: from, to: to) else { return nil }
        c.downmix = true
        converter = c
        self.to = to
    }

    func convert(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        let room = AVAudioFrameCount(Double(buffer.frameLength) * to.sampleRate / buffer.format.sampleRate) + 64
        guard let out = AVAudioPCMBuffer(pcmFormat: to, frameCapacity: room) else { return nil }
        var given = false
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if given { status.pointee = .noDataNow; return nil }
            given = true
            status.pointee = .haveData
            return buffer
        }
        return error == nil ? out : nil
    }
}

/// Counts the frames a source really delivers against the clock. Bluetooth earphones switch to their call mode when a
/// meeting app opens their microphone, and the Mac's output drops from 48 kHz to 16 kHz; read as 48 kHz, the other
/// side of the 2026-10-29 meeting came out three times too fast. macOS tells the device's new rate, but not always
/// in time: this notices it from the samples themselves.
struct RateWatch {
    static let rates: [Double] = [8000, 11025, 16000, 22050, 24000, 32000, 44100, 48000, 88200, 96000]
    static let window: TimeInterval = 1.5
    private(set) var assumed: Double
    private var since: TimeInterval?
    private var frames = 0
    private var candidate: Double?

    init(assumed: Double) { self.assumed = assumed }

    /// `frames` came in at `now` (seconds). Answers the rate the source really runs at once two windows in a row
    /// found the same usual rate, more than 4 % off `assumed`: one slow stretch (a tap starting up) is not enough.
    mutating func add(_ frames: Int, at now: TimeInterval) -> Double? {
        guard let start = since else { since = now; return nil }       // the first buffer only starts the clock
        self.frames += frames
        let span = now - start
        guard span >= Self.window else { return nil }
        let measured = Double(self.frames) / span
        since = now
        self.frames = 0
        guard abs(measured - assumed) / assumed > 0.04, let rate = Self.nearest(measured) else { candidate = nil; return nil }
        guard candidate == rate else { candidate = rate; return nil }
        candidate = nil
        assumed = rate
        return rate
    }

    /// the usual sample rate within 4 % of `rate`, if there is one
    static func nearest(_ rate: Double) -> Double? {
        guard let best = rates.min(by: { abs($0 - rate) < abs($1 - rate) }), abs(best - rate) / best < 0.04 else { return nil }
        return best
    }
}

/// The sound every other app plays, from a process tap and a private aggregate device clocked by the output.
@available(macOS 14.2, *)
final class SystemSound {
    private var tap = AudioObjectID(kAudioObjectUnknown)
    private var device = AudioObjectID(kAudioObjectUnknown)
    private var proc: AudioDeviceIOProcID?
    private var resampler: Resampler?
    private var tapBuffers = 1
    private var layout = AudioStreamBasicDescription()     // the tap's channels and sample format; the rate follows the device
    private var watch = RateWatch(assumed: 48000)
    private var rateListener: AudioObjectPropertyListenerBlock?
    private let target: AVAudioFormat
    private let note: (String) -> Void
    private let queue = DispatchQueue(label: "vinutes.system-sound")

    /// starts delivering 16 kHz mono buffers to `deliver`; throws when macOS has no way to tap
    init(_ target: AVAudioFormat, note: @escaping (String) -> Void = { _ in },
         deliver: @escaping (AVAudioPCMBuffer) -> Void) throws {
        self.target = target
        self.note = note
        let desc = CATapDescription(stereoGlobalTapButExcludeProcesses: ownProcess().map { [$0] } ?? [])
        desc.uuid = UUID()
        desc.name = "Vinutes"
        desc.isPrivate = true
        desc.muteBehavior = .unmuted
        try check(AudioHardwareCreateProcessTap(desc, &tap), "create the tap")

        var format = AudioStreamBasicDescription()
        var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        var address = AudioObjectPropertyAddress(mSelector: kAudioTapPropertyFormat, mScope: kAudioObjectPropertyScopeGlobal,
                                                 mElement: kAudioObjectPropertyElementMain)
        try check(AudioObjectGetPropertyData(tap, &address, 0, nil, &size, &format), "read the tap's format")
        guard let source = AVAudioFormat(streamDescription: &format) else {
            throw NSError(domain: "capture", code: 1, userInfo: [NSLocalizedDescriptionKey: "unusable tap format"])
        }
        layout = format
        tapBuffers = source.isInterleaved ? 1 : Int(source.channelCount)

        let output = try defaultOutputUID()
        let aggregate: [String: Any] = [
            kAudioAggregateDeviceNameKey: "Vinutes",
            kAudioAggregateDeviceUIDKey: "vinutes-" + UUID().uuidString,
            kAudioAggregateDeviceMainSubDeviceKey: output,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceIsStackedKey: false,
            kAudioAggregateDeviceTapAutoStartKey: true,
            kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: output]],
            kAudioAggregateDeviceTapListKey: [[kAudioSubTapDriftCompensationKey: true,
                                               kAudioSubTapUIDKey: desc.uuid.uuidString]],
        ]
        try check(AudioHardwareCreateAggregateDevice(aggregate as CFDictionary, &device), "create the device")
        // The samples come at the rate the output runs at, which is not always the tap's: Bluetooth earphones in their
        // call mode run at 16 kHz. Read it from the device, follow it when it changes, and count it as a last resort.
        let running = nominalRate(device)
        useRate(running > 0 ? running : format.mSampleRate, why: "starts")
        var rateAddress = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyNominalSampleRate,
                                                     mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        let tapDevice = device
        let listener: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
            guard let self else { return }
            let rate = nominalRate(tapDevice)
            if rate > 0, rate != self.watch.assumed { self.useRate(rate, why: "macOS says it changed") }
        }
        rateListener = listener
        AudioObjectAddPropertyListenerBlock(device, &rateAddress, queue, listener)
        try check(AudioDeviceCreateIOProcIDWithBlock(&proc, device, queue) { [weak self] _, input, inputTime, _, _ in
            // the tap's buffers come last: an output that also has a microphone (a headset) puts its own first
            guard let self, self.resampler != nil else { return }
            let all = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input))
            guard all.count >= self.tapBuffers else { return }
            let list = AudioBufferList.allocate(maximumBuffers: self.tapBuffers)
            defer { free(list.unsafeMutablePointer) }
            for i in 0..<self.tapBuffers { list[i] = all[all.count - self.tapBuffers + i] }
            let frames = Int(list[0].mDataByteSize) / max(1, Int(self.layout.mBytesPerFrame))
            // when the samples were heard, not when this queue got to them: a busy moment must not look like a new rate
            let host = inputTime.pointee.mHostTime
            let heard = host > 0 ? Double(AudioConvertHostTimeToNanos(host)) / 1e9 : CACurrentMediaTime()
            if let rate = self.watch.add(frames, at: heard) { self.useRate(rate, why: "counted") }
            guard let r = self.resampler,
                  let buffer = AVAudioPCMBuffer(pcmFormat: r.converter.inputFormat, bufferListNoCopy: list.unsafePointer),
                  let mono = r.convert(buffer) else { return }
            deliver(mono)
        }, "listen to the device")
        try check(AudioDeviceStart(device, proc), "start the device")
    }

    /// From now on read the samples as `rate` a second (on `queue`, or before the device starts).
    private func useRate(_ rate: Double, why: String) {
        var asbd = layout
        asbd.mSampleRate = rate
        guard let source = AVAudioFormat(streamDescription: &asbd), let r = Resampler(from: source, to: target) else {
            watch = RateWatch(assumed: rate)        // not again every three seconds
            return note("the Mac's sound at \(Int(rate)) Hz cannot be converted")
        }
        resampler = r
        watch = RateWatch(assumed: rate)
        note("the Mac's sound runs at \(Int(rate)) Hz (\(why))")
    }

    func stop() {
        if let rateListener {
            var address = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyNominalSampleRate,
                                                     mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
            AudioObjectRemovePropertyListenerBlock(device, &address, queue, rateListener)
        }
        rateListener = nil
        if let proc {
            AudioDeviceStop(device, proc)
            AudioDeviceDestroyIOProcID(device, proc)
        }
        proc = nil
        if device != kAudioObjectUnknown { AudioHardwareDestroyAggregateDevice(device) }
        if tap != kAudioObjectUnknown { AudioHardwareDestroyProcessTap(tap) }
        device = kAudioObjectUnknown
        tap = kAudioObjectUnknown
    }

    deinit { stop() }
}

private func check(_ status: OSStatus, _ what: String) throws {
    guard status == noErr else {
        throw NSError(domain: "capture", code: Int(status), userInfo: [NSLocalizedDescriptionKey: "could not \(what) (\(status))"])
    }
}

/// this app's own process object, so its playback is left out of the tap
private func ownProcess() -> AudioObjectID? {
    var pid = getpid()
    var object = AudioObjectID(kAudioObjectUnknown)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    var address = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyTranslatePIDToProcessObject,
                                             mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    let status = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address,
                                            UInt32(MemoryLayout<pid_t>.size), &pid, &size, &object)
    return status == noErr && object != kAudioObjectUnknown ? object : nil
}

/// the rate a device runs at now, 0 when it cannot be read
private func nominalRate(_ device: AudioObjectID) -> Double {
    var rate = 0.0
    var size = UInt32(MemoryLayout<Double>.size)
    var address = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyNominalSampleRate,
                                             mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    return AudioObjectGetPropertyData(device, &address, 0, nil, &size, &rate) == noErr ? rate : 0
}

private func defaultOutputUID() throws -> String {
    var device = AudioObjectID(kAudioObjectUnknown)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    var address = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDefaultOutputDevice,
                                             mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    try check(AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &device),
              "find the output")
    var uid: Unmanaged<CFString>?
    size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    address.mSelector = kAudioDevicePropertyDeviceUID
    try check(AudioObjectGetPropertyData(device, &address, 0, nil, &size, &uid), "read the output's id")
    guard let name = uid?.takeRetainedValue() as String? else { throw NSError(domain: "capture", code: 2) }
    return name
}

/// A microphone of this Mac, as the 麥克風 menu lists it; settings.json keeps the chosen one's uid ("microphone").
struct Microphone {
    let uid: String
    let name: String
}

private func stringProperty(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector) -> String? {
    var value: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    var address = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal,
                                             mElement: kAudioObjectPropertyElementMain)
    guard AudioObjectGetPropertyData(object, &address, 0, nil, &size, &value) == noErr else { return nil }
    return value?.takeRetainedValue() as String?
}

private func objects(_ selector: AudioObjectPropertySelector) -> [AudioObjectID] {
    var address = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal,
                                             mElement: kAudioObjectPropertyElementMain)
    var size: UInt32 = 0
    let system = AudioObjectID(kAudioObjectSystemObject)
    guard AudioObjectGetPropertyDataSize(system, &address, 0, nil, &size) == noErr, size > 0 else { return [] }
    var list = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    guard AudioObjectGetPropertyData(system, &address, 0, nil, &size, &list) == noErr else { return [] }
    return list
}

private func inputChannels(_ device: AudioObjectID) -> Int {
    var address = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyStreamConfiguration,
                                             mScope: kAudioObjectPropertyScopeInput, mElement: kAudioObjectPropertyElementMain)
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(device, &address, 0, nil, &size) == noErr, size > 0 else { return 0 }
    let raw = UnsafeMutableRawPointer.allocate(byteCount: Int(size), alignment: MemoryLayout<AudioBufferList>.alignment)
    defer { raw.deallocate() }
    let list = raw.bindMemory(to: AudioBufferList.self, capacity: 1)
    guard AudioObjectGetPropertyData(device, &address, 0, nil, &size, list) == noErr else { return 0 }
    return UnsafeMutableAudioBufferListPointer(list).reduce(0) { $0 + Int($1.mNumberChannels) }
}

/// every microphone macOS has now (built in, Bluetooth earphones, a headset on the cable), Vinutes' own devices left out
func microphones() -> [Microphone] {
    objects(kAudioHardwarePropertyDevices).compactMap { device in
        guard inputChannels(device) > 0, let uid = stringProperty(device, kAudioDevicePropertyDeviceUID),
              !uid.hasPrefix("vinutes-"), let name = stringProperty(device, kAudioObjectPropertyName) else { return nil }
        return Microphone(uid: uid, name: name)
    }
}

private func device(uid: String) -> AudioObjectID? {
    var id = AudioObjectID(kAudioObjectUnknown)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    var cf = uid as CFString
    var address = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyTranslateUIDToDevice,
                                             mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    let status = withUnsafeMutablePointer(to: &cf) {
        AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address,
                                   UInt32(MemoryLayout<CFString>.size), $0, &size, &id)
    }
    return status == noErr && id != kAudioObjectUnknown ? id : nil
}

/// Whether another app has a microphone open right now: Teams, Zoom or a browser in a call do, a room meeting has none.
/// The bar only warns that the other side is silent while this is so.
func otherAppUsesMicrophone() -> Bool {
    guard #available(macOS 14.2, *) else { return false }
    let me = getpid()
    return objects(kAudioHardwarePropertyProcessObjectList).contains { process in
        var pid: pid_t = 0
        var running: UInt32 = 0
        var size = UInt32(MemoryLayout<pid_t>.size)
        var address = AudioObjectPropertyAddress(mSelector: kAudioProcessPropertyPID, mScope: kAudioObjectPropertyScopeGlobal,
                                                 mElement: kAudioObjectPropertyElementMain)
        guard AudioObjectGetPropertyData(process, &address, 0, nil, &size, &pid) == noErr, pid != me else { return false }
        size = UInt32(MemoryLayout<UInt32>.size)
        address.mSelector = kAudioProcessPropertyIsRunningInput
        return AudioObjectGetPropertyData(process, &address, 0, nil, &size, &running) == noErr && running != 0
    }
}

/// The recording: microphone plus the Mac's sound, written as they come in. Replaces AVAudioRecorder.
final class MeetingCapture {
    static let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 16000, channels: 1, interleaved: false)!
    let url: URL
    private var engine = AVAudioEngine()
    private var file: AVAudioFile?
    private var meFile: AVAudioFile?       // the microphone alone (your voice), beside the mix
    private var otherFile: AVAudioFile?    // the Mac's sound alone (the other side), beside the mix
    private var stopped = false
    private var failures = 0
    private var micResampler: Resampler?
    private let system = SampleQueue()
    private var systemSound: AnyObject?
    private let writing = DispatchQueue(label: "vinutes.capture")
    private var paused = false
    private var power: Float = -160
    private var mePower: Float = -160
    private var otherPower: Float = -160
    private var otherHeardAt = CACurrentMediaTime()
    private let powerLock = NSLock()
    private var observer: NSObjectProtocol?
    private var outputListener: AudioObjectPropertyListenerBlock?
    private(set) var hearsSystem = false
    /// the microphone to record, by uid; "" records the one macOS uses now (自動)
    var microphone = ""
    var note: (String) -> Void = { _ in }

    init(url: URL) throws {
        self.url = url
        let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16000, AVNumberOfChannelsKey: 1,
                                       AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
        file = try AVAudioFile(forWriting: url, settings: settings, commonFormat: .pcmFormatFloat32, interleaved: false)
        // Two side tracks beside the mix: me.caf is the microphone alone, other.caf is the Mac's sound alone. They
        // let a later listen tell the two voices apart, and a silent other.caf shows the other side never came in.
        // They are optional: if they cannot open, the mix (which captions and the transcriber read) records as before.
        let dir = url.deletingLastPathComponent()
        meFile = try? AVAudioFile(forWriting: dir.appendingPathComponent("me.caf"), settings: settings,
                                  commonFormat: .pcmFormatFloat32, interleaved: false)
        otherFile = try? AVAudioFile(forWriting: dir.appendingPathComponent("other.caf"), settings: settings,
                                     commonFormat: .pcmFormatFloat32, interleaved: false)
    }

    /// the microphone, and the Mac's sound when macOS lets Vinutes tap it
    func start() throws {
        try openMicrophone()
        listenToSystem()
        // the sound follows the Mac's output (AirPods connected or gone): tap it again on the new one
        var address = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDefaultOutputDevice,
                                                 mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        let listener: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
            guard let self, !self.stopped else { return }
            self.note("the Mac's output changed, listening to it again")
            self.listenToSystem()
        }
        outputListener = listener
        AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &address, .main, listener)
    }

    /// (again) the sound the Mac plays, when macOS lets Vinutes tap it
    private func listenToSystem() {
        if #available(macOS 14.2, *) {
            (systemSound as? SystemSound)?.stop()
            systemSound = nil
            system.clear()
            do {
                systemSound = try SystemSound(Self.format, note: { [weak self] in self?.note($0) }) { [weak self] in
                    self?.system.push($0)
                }
                hearsSystem = true
                note("asked for the Mac's sound too (silent if macOS was not allowed to share it)")
            } catch {
                hearsSystem = false
                note("microphone only: \(error.localizedDescription)")
            }
        } else {
            note("microphone only: the Mac's sound needs macOS 14.2")
        }
    }

    /// Records `uid` from now on ("" for the one macOS uses), also in the middle of a recording.
    func useMicrophone(_ uid: String) throws {
        microphone = uid
        guard !stopped else { return }
        system.clear()                              // what queued meanwhile would come late
        try openMicrophone()
    }

    /// The chosen microphone, or the one macOS uses when it cannot start: a recording never goes on hearing nothing.
    private func openMicrophone() throws {
        do { try startMicrophone(chosen: true) } catch where !microphone.isEmpty {
            note("the chosen microphone could not start (\(error.localizedDescription)): recording the Mac's own choice")
            try startMicrophone(chosen: false)
        }
    }

    /// (Again) the microphone, on a new engine each time: an engine once told to use one microphone keeps it after
    /// it is gone or 自動 is picked again, and may still give the old one's format.
    private func startMicrophone(chosen: Bool) throws {
        if let observer { NotificationCenter.default.removeObserver(observer) }
        observer = nil
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        engine = AVAudioEngine()
        let input = engine.inputNode
        if chosen, !microphone.isEmpty {
            // the chosen one when it is here; gone (earphones put away), the one macOS uses, as with 自動
            if var id = device(uid: microphone), let unit = input.audioUnit {
                let status = AudioUnitSetProperty(unit, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0,
                                                  &id, UInt32(MemoryLayout<AudioObjectID>.size))
                note(status == noErr ? "microphone: \(microphone)" : "could not choose the microphone (\(status))")
            } else {
                note("the chosen microphone is not connected: recording the Mac's own choice")
            }
        }
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0,
              let mono = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: format.sampleRate, channels: 1,
                                       interleaved: false),
              let r = Resampler(from: mono, to: Self.format) else {
            throw NSError(domain: "capture", code: 3, userInfo: [NSLocalizedDescriptionKey: "no microphone"])
        }
        micResampler = r
        input.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, _ in
            guard let self, let first = buffer.floatChannelData?[0],
                  let one = AVAudioPCMBuffer(pcmFormat: mono, frameCapacity: buffer.frameLength) else { return }
            one.frameLength = buffer.frameLength                  // the first channel: the microphone itself
            one.floatChannelData![0].update(from: first, count: Int(buffer.frameLength))
            guard let converted = r.convert(one) else { return }
            self.mix(converted)
        }
        engine.prepare()
        try engine.start()
        // a new microphone (headphones plugged in, AirPods connected) stops the engine: start a new one. Watched only
        // once this engine runs, so choosing the microphone above does not set it off again.
        let running = engine
        let started = CACurrentMediaTime()
        observer = NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange, object: running,
                                                          queue: .main) { [weak self] _ in
            guard let self, !self.stopped, self.engine === running, CACurrentMediaTime() - started > 1 else { return }
            self.note("the microphone changed, listening again")
            self.system.clear()                          // what queued meanwhile would come late
            do { try self.openMicrophone() } catch {
                self.note("the microphone could not start again: \(error.localizedDescription); trying once more")
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
                    guard let self, !self.stopped else { return }
                    do { try self.openMicrophone() } catch { self.note("no microphone: \(error.localizedDescription)") }
                }
            }
        }
    }

    /// From one microphone buffer and the matching Mac-sound samples, make the two side tracks and mix the Mac's
    /// sound into `mic` in place. Returns the microphone-alone track, the Mac's-sound-alone track, and the mix's
    /// RMS. Pure (no files, no locks, no `self`), so it can be unit-tested; `mix` and the writers do the I/O.
    /// `me` is a copy of the microphone taken before the mix overwrites it; `other` is the Mac's sound alone,
    /// the same length as the mix. The three tracks advance together frame for frame; alignment is best-effort,
    /// since a side track whose buffer can't be allocated or written in a given callback is skipped (rare — the
    /// buffers are a few KB). The silent-`other.caf` signal and speaker separation tolerate such a rare slip.
    static func tracks(mic: AVAudioPCMBuffer, other: [Float]) -> (me: AVAudioPCMBuffer?, other: AVAudioPCMBuffer?, rms: Float) {
        let n = Int(mic.frameLength)
        guard let data = mic.floatChannelData?[0] else { return (nil, nil, 0) }
        let meTrack = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: mic.frameLength)
        meTrack?.frameLength = mic.frameLength
        if n > 0 { meTrack?.floatChannelData?[0].update(from: data, count: n) }
        let otherTrack = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(max(n, 1)))
        if n > 0, let od = otherTrack?.floatChannelData?[0] {
            otherTrack?.frameLength = AVAudioFrameCount(n)
            other.withUnsafeBufferPointer { od.update(from: $0.baseAddress!, count: min(n, other.count)) }
            if other.count < n { for i in other.count..<n { od[i] = 0 } }
        }
        var sum: Float = 0
        for i in 0..<n {
            let v = data[i] + (i < other.count ? other[i] : 0)
            let s = v > 1 ? 1 : v < -1 ? -1 : v
            data[i] = s
            sum += s * s
        }
        let rms = n > 0 ? sqrt(sum / Float(n)) : 0
        return (meTrack, otherTrack, rms)
    }

    /// the microphone's samples plus as many of the Mac's sound, written and measured. The mix goes to the main
    /// file; the microphone alone and the Mac's sound alone go to the two side tracks, so the two voices can be
    /// told apart later and a silent other.caf shows the other side never came in.
    private func mix(_ mic: AVAudioPCMBuffer) {
        let n = Int(mic.frameLength)
        let other = system.take(n)
        let (meTrack, otherTrack, rms) = Self.tracks(mic: mic, other: other)
        let meRMS = meTrack.map { Self.rms($0) } ?? 0
        let otherRMS = otherTrack.map { Self.rms($0) } ?? 0
        powerLock.lock()
        power = Self.decibels(rms)
        mePower = Self.decibels(meRMS)
        otherPower = Self.decibels(otherRMS)
        if otherPower > Self.heard { otherHeardAt = CACurrentMediaTime() }
        powerLock.unlock()
        writing.async { [weak self] in
            guard let self, !self.stopped, !self.paused else { return }
            if let file = self.file {
                do { try file.write(from: mic) } catch {
                    self.failures += 1                       // a full disk: say so now and then, not every 85 ms
                    if self.failures == 1 || self.failures % 100 == 0 {
                        self.note("could not write (\(self.failures)×): \(error.localizedDescription)")
                    }
                }
            }
            if n > 0 {                                   // both side tracks advance by n together, or neither does
                if let meFile = self.meFile, let meTrack { try? meFile.write(from: meTrack) }
                if let otherFile = self.otherFile, let otherTrack { try? otherFile.write(from: otherTrack) }
            }
        }
    }

    func pause() { writing.async { self.paused = true } }

    func resume() {
        system.clear()
        powerLock.lock(); otherHeardAt = CACurrentMediaTime(); powerLock.unlock()   // a pause is not the other side's silence
        writing.async { self.paused = false }
    }

    /// how loud the last moment was, in dB (about -50 is a quiet room, 0 loud)
    var averagePower: Float { powerLock.lock(); defer { powerLock.unlock() }; return power }

    /// the last moment of the microphone alone (我) and of the Mac's sound alone (對方), in dB
    var levels: (me: Float, other: Float) { powerLock.lock(); defer { powerLock.unlock() }; return (mePower, otherPower) }

    /// how many seconds the Mac's sound has been silent (below -55 dB)
    var otherSilentFor: TimeInterval {
        powerLock.lock(); defer { powerLock.unlock() }
        return CACurrentMediaTime() - otherHeardAt
    }

    static let heard: Float = -55

    static func rms(_ buffer: AVAudioPCMBuffer) -> Float {
        guard let d = buffer.floatChannelData?[0], buffer.frameLength > 0 else { return 0 }
        var sum: Float = 0
        for i in 0..<Int(buffer.frameLength) { sum += d[i] * d[i] }
        return sqrt(sum / Float(buffer.frameLength))
    }

    static func decibels(_ rms: Float) -> Float { rms > 0 ? 20 * log10(rms) : -160 }

    func stop() {
        if let observer { NotificationCenter.default.removeObserver(observer) }
        observer = nil
        if let outputListener {
            var address = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDefaultOutputDevice,
                                                     mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
            AudioObjectRemovePropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &address, .main, outputListener)
        }
        outputListener = nil
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        if #available(macOS 14.2, *) { (systemSound as? SystemSound)?.stop() }
        systemSound = nil
        writing.sync {                                      // everything heard is in the files, and they are closed
            stopped = true
            file = nil
            meFile = nil
            otherFile = nil
        }
    }
}
