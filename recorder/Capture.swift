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

/// The sound every other app plays, from a process tap and a private aggregate device clocked by the output.
@available(macOS 14.2, *)
final class SystemSound {
    private var tap = AudioObjectID(kAudioObjectUnknown)
    private var device = AudioObjectID(kAudioObjectUnknown)
    private var proc: AudioDeviceIOProcID?
    private var resampler: Resampler?
    private var tapBuffers = 1
    private let queue = DispatchQueue(label: "vinutes.system-sound")

    /// starts delivering 16 kHz mono buffers to `deliver`; throws when macOS has no way to tap
    init(_ target: AVAudioFormat, deliver: @escaping (AVAudioPCMBuffer) -> Void) throws {
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
        guard let source = AVAudioFormat(streamDescription: &format), let r = Resampler(from: source, to: target) else {
            throw NSError(domain: "capture", code: 1, userInfo: [NSLocalizedDescriptionKey: "unusable tap format"])
        }
        resampler = r
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
        try check(AudioDeviceCreateIOProcIDWithBlock(&proc, device, queue) { [weak self] _, input, _, _, _ in
            // the tap's buffers come last: an output that also has a microphone (a headset) puts its own first
            guard let self, let r = self.resampler else { return }
            let all = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input))
            guard all.count >= self.tapBuffers else { return }
            let list = AudioBufferList.allocate(maximumBuffers: self.tapBuffers)
            defer { free(list.unsafeMutablePointer) }
            for i in 0..<self.tapBuffers { list[i] = all[all.count - self.tapBuffers + i] }
            guard let buffer = AVAudioPCMBuffer(pcmFormat: r.converter.inputFormat, bufferListNoCopy: list.unsafePointer),
                  let mono = r.convert(buffer) else { return }
            deliver(mono)
        }, "listen to the device")
        try check(AudioDeviceStart(device, proc), "start the device")
    }

    func stop() {
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

/// The recording: microphone plus the Mac's sound, written as they come in. Replaces AVAudioRecorder.
final class MeetingCapture {
    static let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 16000, channels: 1, interleaved: false)!
    let url: URL
    private let engine = AVAudioEngine()
    private var file: AVAudioFile?
    private var stopped = false
    private var failures = 0
    private var micResampler: Resampler?
    private let system = SampleQueue()
    private var systemSound: AnyObject?
    private let writing = DispatchQueue(label: "vinutes.capture")
    private var paused = false
    private var power: Float = -160
    private let powerLock = NSLock()
    private var observer: NSObjectProtocol?
    private var outputListener: AudioObjectPropertyListenerBlock?
    private(set) var hearsSystem = false
    var note: (String) -> Void = { _ in }

    init(url: URL) throws {
        self.url = url
        let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16000, AVNumberOfChannelsKey: 1,
                                       AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
        file = try AVAudioFile(forWriting: url, settings: settings, commonFormat: .pcmFormatFloat32, interleaved: false)
    }

    /// the microphone, and the Mac's sound when macOS lets Vinutes tap it
    func start() throws {
        try startMicrophone()
        listenToSystem()
        // a new microphone (headphones plugged in, AirPods connected) stops the engine: start it again
        observer = NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine,
                                                          queue: .main) { [weak self] _ in
            guard let self, !self.stopped else { return }
            self.note("the microphone changed, listening again")
            self.engine.inputNode.removeTap(onBus: 0)
            self.system.clear()                          // what queued meanwhile would come late
            do { try self.startMicrophone() } catch {
                self.note("the microphone could not start again: \(error.localizedDescription); trying once more")
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
                    guard let self, !self.stopped else { return }
                    do { try self.startMicrophone() } catch { self.note("no microphone: \(error.localizedDescription)") }
                }
            }
        }
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
                systemSound = try SystemSound(Self.format) { [weak self] in self?.system.push($0) }
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

    private func startMicrophone() throws {
        let input = engine.inputNode
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
    }

    /// the microphone's samples plus as many of the Mac's sound, written and measured
    private func mix(_ mic: AVAudioPCMBuffer) {
        let n = Int(mic.frameLength)
        let other = system.take(n)
        guard let data = mic.floatChannelData?[0] else { return }
        var sum: Float = 0
        for i in 0..<n {
            let v = data[i] + other[i]
            let s = v > 1 ? 1 : v < -1 ? -1 : v
            data[i] = s
            sum += s * s
        }
        let rms = n > 0 ? sqrt(sum / Float(n)) : 0
        powerLock.lock(); power = rms > 0 ? 20 * log10(rms) : -160; powerLock.unlock()
        writing.async { [weak self] in
            guard let self, !self.stopped, !self.paused, let file = self.file else { return }
            do { try file.write(from: mic) } catch {
                self.failures += 1                       // a full disk: say so now and then, not every 85 ms
                if self.failures == 1 || self.failures % 100 == 0 {
                    self.note("could not write (\(self.failures)×): \(error.localizedDescription)")
                }
            }
        }
    }

    func pause() { writing.async { self.paused = true } }

    func resume() {
        system.clear()
        writing.async { self.paused = false }
    }

    /// how loud the last moment was, in dB (about -50 is a quiet room, 0 loud)
    var averagePower: Float { powerLock.lock(); defer { powerLock.unlock() }; return power }

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
        writing.sync {                                      // everything heard is in the file, and it is closed
            stopped = true
            file = nil
        }
    }
}
