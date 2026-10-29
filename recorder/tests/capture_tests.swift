// Unit tests for MeetingCapture.tracks(mic:other:) — the pure mix/side-track logic.
// Build & run from the repo root:
//   swiftc -parse-as-library -o /tmp/capture_tests recorder/Capture.swift recorder/tests/capture_tests.swift
//   /tmp/capture_tests
import AVFoundation
import Foundation

func mkbuf(_ samples: [Float]) -> AVAudioPCMBuffer {
    let b = AVAudioPCMBuffer(pcmFormat: MeetingCapture.format, frameCapacity: AVAudioFrameCount(max(samples.count, 1)))!
    b.frameLength = AVAudioFrameCount(samples.count)
    for i in samples.indices { b.floatChannelData![0][i] = samples[i] }
    return b
}
func arr(_ b: AVAudioPCMBuffer?) -> [Float] {
    guard let b, let d = b.floatChannelData?[0] else { return [] }
    return (0..<Int(b.frameLength)).map { d[$0] }
}
func near(_ a: [Float], _ b: [Float]) -> Bool {
    guard a.count == b.count else { return false }
    for i in a.indices where abs(a[i] - b[i]) > 1e-5 { return false }
    return true
}

@main
enum CaptureTests {
    static func main() {
        var fails = 0
        func check(_ cond: Bool, _ msg: String) {
            print((cond ? "ok  : " : "FAIL: ") + msg); if !cond { fails += 1 }
        }

        // 1. Normal: me is the mic before mixing, other is the system samples, mix is mic+other, all same length.
        do {
            let mic = mkbuf([0.5, 0.5, 0.5])
            let (me, other, rms) = MeetingCapture.tracks(mic: mic, other: [0.2, 0.2, 0.2])
            check(near(arr(me), [0.5, 0.5, 0.5]), "me = microphone taken before the mix overwrites it")
            check(near(arr(other), [0.2, 0.2, 0.2]), "other = the Mac's sound alone")
            check(near(arr(mic), [0.7, 0.7, 0.7]), "the main buffer is mixed in place (mic + other)")
            check(abs(rms - 0.7) < 1e-4, "rms of the mix is reported")
        }

        // 2. Clipping: mic+other over 1.0 is clamped in the mix, but the side tracks keep the originals.
        do {
            let mic = mkbuf([0.9, -0.9])
            let (me, other, _) = MeetingCapture.tracks(mic: mic, other: [0.9, -0.9])
            check(near(arr(mic), [1.0, -1.0]), "mix clamps to [-1, 1]")
            check(near(arr(me), [0.9, -0.9]), "me keeps the un-clamped microphone")
            check(near(arr(other), [0.9, -0.9]), "other keeps the un-clamped Mac sound")
        }

        // 3. The other side never came in: all-zero system samples -> other.caf is silent, mix == mic.
        do {
            let mic = mkbuf([0.3, 0.4, 0.5])
            let (me, other, _) = MeetingCapture.tracks(mic: mic, other: [0, 0, 0])
            check(arr(other).allSatisfy { $0 == 0 }, "silent system -> other track is all zeros (detectable)")
            check(near(arr(mic), [0.3, 0.4, 0.5]), "mix equals the microphone when the other side is silent")
            check(near(arr(me), [0.3, 0.4, 0.5]), "me still carries the microphone")
        }

        // 4. Fewer system samples than mic frames: the tail is padded with silence, no crash, lengths match.
        do {
            let mic = mkbuf([0.1, 0.1, 0.1, 0.1])
            let (me, other, _) = MeetingCapture.tracks(mic: mic, other: [0.2, 0.2])
            check(arr(me).count == 4 && arr(other).count == 4, "side tracks are the microphone's length")
            check(near(arr(other), [0.2, 0.2, 0.0, 0.0]), "missing system samples are silence, aligned to the front")
            check(near(arr(mic), [0.3, 0.3, 0.1, 0.1]), "mix uses system where present, mic alone after")
        }

        print(fails == 0 ? "\nALL PASSED" : "\n\(fails) FAILED")
        exit(fails == 0 ? 0 : 1)
    }
}
