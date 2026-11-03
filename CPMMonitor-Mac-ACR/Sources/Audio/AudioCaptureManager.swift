import Foundation
import ScreenCaptureKit
import AVFoundation
import Combine

/// Captura el audio de salida del sistema via ScreenCaptureKit (macOS 13+).
/// Mantiene un buffer circular de los últimos ~25 segundos de PCM Float32.
/// Publica el nivel RMS actual para detección de silencio / actividad.
///
/// NOTA DE PERMISOS:
/// En DESARROLLO (firma ad-hoc) el permiso de "Grabación de pantalla" se vincula
/// a la firma del proceso, que cambia con cada build. Solución de desarrollo:
///   tccutil reset ScreenCapture com.sumartered.monitor
/// En PRODUCCIÓN (Developer ID), la firma es constante → el permiso se otorga
/// una vez en el venue y persiste indefinidamente en todas las actualizaciones.
///
class AudioCaptureManager: NSObject, ObservableObject {
    static let shared = AudioCaptureManager()

    // MARK: - Publicado
    @Published var isCapturing = false
    @Published var currentRMS: Float = 0
    @Published var permissionStatus: PermStatus = .unknown

    enum PermStatus { case unknown, granted, denied }

    // MARK: - Config
    let sampleRate = 16000
    let channels   = 1
    private let maxBufferSeconds = 25

    private(set) var actualSampleRate: Int = 16000

    // MARK: - Internals
    private var stream: SCStream?
    private var pcmBuffer = [Float]()
    private let bufferLock = NSLock()
    private let captureQueue = DispatchQueue(label: "sr.audio.capture", qos: .userInitiated)

    private var lastAudioTime: Date = .distantPast
    private var watchdogTimer: Timer?

    /// true si TCC tiene el permiso pero el proceso actual aún no puede usarlo
    /// (caso habitual en macOS 14+ cuando se otorga el permiso con la app ya abierta).
    @Published var needsRestart: Bool = false

    private override init() {}

    func clearBuffer() {
        bufferLock.lock(); pcmBuffer.removeAll(); bufferLock.unlock()
        print("[Audio] Buffer limpiado")
    }

    // MARK: - Permisos

    /// Comprueba el estado actual sin mostrar diálogos.
    /// En macOS 14+ detecta el caso "permiso concedido pero proceso necesita reinicio".
    func checkPermission() async -> Bool {
        // Intento silencioso de SCShareableContent — si falla con error de permiso
        // sabemos exactamente qué ocurre sin depender de CGPreflightScreenCaptureAccess
        // (que no distingue entre "denegado" y "proceso necesita reinicio").
        do {
            _ = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
            await MainActor.run { permissionStatus = .granted; needsRestart = false }
            return true
        } catch {
            let code = (error as NSError).code
            // Código 5 = SCStreamError.userDeclined (denied or restricted)
            // Código -3801 / otros = podría ser "necesita reinicio"
            let preflight = CGPreflightScreenCaptureAccess()
            await MainActor.run {
                if preflight {
                    // TCC dice que está concedido, pero SCKit falla → necesita reinicio
                    permissionStatus = .granted
                    needsRestart = true
                } else {
                    permissionStatus = .denied
                    needsRestart = false
                }
            }
            print("[Audio] checkPermission error (code \(code)): \(error.localizedDescription)")
            return false
        }
    }

    /// Abre el diálogo / System Settings y luego reintenta la captura.
    func requestPermissionAndStart() {
        // CGRequestScreenCaptureAccess en macOS 14+ abre System Settings directamente.
        // En macOS 13 muestra el diálogo nativo. En cualquier caso, tras esta llamada
        // el usuario debe activar el toggle y la app relanzarse para que SCKit lo tome.
        CGRequestScreenCaptureAccess()

        // Damos 2 s para que el usuario active el toggle en System Settings,
        // luego verificamos si ya podemos capturar sin reiniciar.
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            Task {
                let ok = await self.checkPermission()
                if ok {
                    ACRScanner.shared.forceRestart()
                }
                // Si needsRestart quedó en true, la UI mostrará "Reiniciar app".
            }
        }
    }

    func openPrivacySettings() {
        NSWorkspace.shared.open(
            URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")!
        )
    }

    /// Relanza el proceso para que el nuevo proceso herede el permiso TCC ya otorgado.
    func relaunchApp() {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        task.arguments = ["-n", Bundle.main.bundlePath]
        try? task.run()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { NSApp.terminate(nil) }
    }

    // MARK: - Captura

    func startCapture() async throws {
        guard !isCapturing else { return }

        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else { throw CaptureError.noDisplay }

        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])

        let config = SCStreamConfiguration()
        config.capturesAudio               = true
        config.sampleRate                  = sampleRate
        config.channelCount                = channels
        config.excludesCurrentProcessAudio = false
        config.width                       = 2
        config.height                      = 2
        config.minimumFrameInterval        = CMTime(value: 1, timescale: 1)

        let s = SCStream(filter: filter, configuration: config, delegate: self)
        try s.addStreamOutput(self, type: .audio, sampleHandlerQueue: captureQueue)
        try await s.startCapture()

        stream = s
        await MainActor.run {
            isCapturing    = true
            permissionStatus = .granted
            needsRestart   = false
            lastAudioTime  = Date()
            startWatchdog()
        }
        print("[Audio] ✅ Captura de sistema iniciada — \(sampleRate) Hz mono")
    }

    func stopCapture() async {
        watchdogTimer?.invalidate(); watchdogTimer = nil
        guard isCapturing, let s = stream else { return }
        try? await s.stopCapture()
        stream = nil
        bufferLock.lock(); pcmBuffer.removeAll(); bufferLock.unlock()
        await MainActor.run { isCapturing = false; currentRMS = 0 }
        print("[Audio] Captura detenida")
    }

    // MARK: - Watchdog
    private func startWatchdog() {
        watchdogTimer?.invalidate()
        watchdogTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            guard let self = self, self.isCapturing else { return }
            if Date().timeIntervalSince(self.lastAudioTime) > 90 {
                print("[Audio] ⚠️ Watchdog — reiniciando stream…")
                Task { await self.restartCapture() }
            }
        }
        RunLoop.main.add(watchdogTimer!, forMode: .common)
    }

    private func restartCapture() async {
        if let s = stream { try? await s.stopCapture(); stream = nil }
        await MainActor.run { isCapturing = false; currentRMS = 0 }
        do    { try await startCapture(); print("[Audio] ✅ Stream reiniciado") }
        catch { print("[Audio] ❌ Error al reiniciar: \(error)") }
    }

    // MARK: - Sample para fingerprint
    func captureSample(seconds: Double) -> Data? {
        let rate    = actualSampleRate
        let needed  = Int(Double(rate) * seconds)
        let minimum = Int(Double(rate) * 5)

        bufferLock.lock(); let snapshot = pcmBuffer; bufferLock.unlock()
        guard snapshot.count >= minimum else { return nil }

        let slice = snapshot.suffix(needed)
        var int16Data = Data(capacity: slice.count * 2)
        for sample in slice {
            let int16 = Int16(max(-1, min(1, sample)) * Float(Int16.max))
            withUnsafeBytes(of: int16.littleEndian) { int16Data.append(contentsOf: $0) }
        }
        return int16Data
    }

    enum CaptureError: Error { case noDisplay, noPermission }
}

// MARK: - SCStreamDelegate
extension AudioCaptureManager: SCStreamDelegate {
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        print("[Audio] Stream error: \(error.localizedDescription)")
        DispatchQueue.main.async { self.isCapturing = false; self.currentRMS = 0 }
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
            guard ACRScanner.shared.isListening else { return }
            Task { await self.restartCapture() }
        }
    }
}

// MARK: - SCStreamOutput
extension AudioCaptureManager: SCStreamOutput {
    func stream(_ stream: SCStream,
                didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
                of type: SCStreamOutputType) {
        guard type == .audio,
              let blockBuffer = CMSampleBufferGetDataBuffer(sampleBuffer) else { return }

        var length = 0
        var ptr: UnsafeMutablePointer<Int8>?
        guard CMBlockBufferGetDataPointer(blockBuffer, atOffset: 0,
                                          lengthAtOffsetOut: nil,
                                          totalLengthOut: &length,
                                          dataPointerOut: &ptr) == kCMBlockBufferNoErr,
              let p = ptr, length > 0 else { return }

        let totalFloats   = length / MemoryLayout<Float>.size
        let floatPtr      = p.withMemoryRebound(to: Float.self, capacity: totalFloats) { $0 }
        var detectedCh    = 1
        var detectedRate  = Double(sampleRate)

        if let fmt = CMSampleBufferGetFormatDescription(sampleBuffer),
           let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fmt) {
            detectedCh   = Int(asbd.pointee.mChannelsPerFrame)
            if asbd.pointee.mSampleRate > 0 { detectedRate = asbd.pointee.mSampleRate }
        }
        if actualSampleRate != Int(detectedRate) {
            actualSampleRate = Int(detectedRate)
            print("[Audio] Rate real: \(actualSampleRate) Hz, \(detectedCh) ch")
        }

        let mono: [Float]
        if detectedCh == 2 {
            let frames = totalFloats / 2
            mono = (0..<frames).map { i in (floatPtr[i*2] + floatPtr[i*2+1]) * 0.5 }
        } else {
            mono = Array(UnsafeBufferPointer(start: floatPtr, count: totalFloats))
        }

        let rms = sqrt(mono.reduce(Float(0)) { $0 + $1*$1 } / Float(max(mono.count, 1)))
        lastAudioTime = Date()

        let maxSamples = actualSampleRate * maxBufferSeconds
        bufferLock.lock()
        pcmBuffer.append(contentsOf: mono)
        if pcmBuffer.count > maxSamples { pcmBuffer.removeFirst(pcmBuffer.count - maxSamples) }
        bufferLock.unlock()

        DispatchQueue.main.async { self.currentRMS = rms }
    }
}
