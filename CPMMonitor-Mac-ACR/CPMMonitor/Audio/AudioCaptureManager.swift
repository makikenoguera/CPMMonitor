import Foundation
import ScreenCaptureKit
import AVFoundation
import Combine

/// Captura el audio de salida del sistema via ScreenCaptureKit (macOS 13+).
/// Mantiene un buffer circular de los últimos ~12 segundos de PCM Float32.
/// Publica el nivel RMS actual para detección de silencio / actividad.
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
    private let maxBufferSeconds = 14   // ~14s de buffer circular

    // MARK: - Internals
    private var stream: SCStream?
    private var pcmBuffer = [Float]()
    private let bufferLock = NSLock()
    private let captureQueue = DispatchQueue(label: "cpm.audio.capture", qos: .userInitiated)

    private override init() {}

    /// Vacía el buffer PCM circular.
    /// Llamar al detectar el inicio de una nueva sesión de audio para evitar
    /// que el fingerprint incluya audio previo (ruido del sistema, canción anterior).
    func clearBuffer() {
        bufferLock.lock()
        pcmBuffer.removeAll()
        bufferLock.unlock()
        print("[Audio] Buffer limpiado — nueva sesión de captura")
    }

    // MARK: - Permisos

    /// true si TCC ya tiene el permiso concedido pero el proceso actual
    /// aún no puede usar SCShareableContent (necesita reinicio).
    @Published var needsRestart: Bool = false

    /// Lee el estado del permiso en TCC sin mostrar ningún diálogo.
    /// Solo se usa para actualizar la UI — la captura real se intenta en startCapture().
    func checkPermission() async -> Bool {
        let granted = CGPreflightScreenCaptureAccess()
        await MainActor.run {
            permissionStatus = granted ? .granted : .denied
            needsRestart = false
        }
        return granted
    }

    /// Muestra el diálogo del sistema (solo cuando el usuario lo pide explícitamente)
    /// y luego intenta iniciar la captura. Si el diálogo ya fue aceptado antes,
    /// startCapture() funcionará directamente sin mostrar nada.
    func requestPermissionAndStart() {
        CGRequestScreenCaptureAccess()
        // Dar tiempo al sistema para registrar el permiso antes de reintentar
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            ACRScanner.shared.start()
        }
    }

    /// Relanza la app para que el nuevo proceso herede el permiso de TCC.
    func relaunchApp() {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        task.arguments = ["-n", Bundle.main.bundlePath]
        try? task.run()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { NSApp.terminate(nil) }
    }

    func openPrivacySettings() {
        NSWorkspace.shared.open(
            URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")!
        )
    }

    // MARK: - Captura
    func startCapture() async throws {
        guard !isCapturing else { return }

        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else {
            throw CaptureError.noDisplay
        }

        // Filtro: todo el sistema (no excluimos ninguna app)
        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])

        let config = SCStreamConfiguration()
        config.capturesAudio              = true
        config.sampleRate                 = sampleRate
        config.channelCount               = channels
        config.excludesCurrentProcessAudio = false  // capturar TODO el audio del sistema
        // Video mínimo — solo necesitamos el stream de audio
        config.width                      = 2
        config.height                     = 2
        config.minimumFrameInterval       = CMTime(value: 1, timescale: 1)

        let s = SCStream(filter: filter, configuration: config, delegate: self)
        try s.addStreamOutput(self, type: .audio, sampleHandlerQueue: captureQueue)
        try await s.startCapture()

        stream = s
        await MainActor.run {
            isCapturing = true
            permissionStatus = .granted
        }
        print("[Audio] Captura iniciada — \(sampleRate)Hz mono")
    }

    func stopCapture() async {
        guard isCapturing, let s = stream else { return }
        try? await s.stopCapture()
        stream = nil
        bufferLock.lock(); pcmBuffer.removeAll(); bufferLock.unlock()
        await MainActor.run { isCapturing = false; currentRMS = 0 }
        print("[Audio] Captura detenida")
    }

    // MARK: - Muestra para fingerprint
    /// Devuelve los últimos `seconds` segundos como PCM Int16 little-endian.
    /// Retorna nil si no hay suficiente audio capturado.
    func captureSample(seconds: Double) -> Data? {
        let needed  = Int(Double(sampleRate) * seconds)
        let minimum = Int(Double(sampleRate) * 5)   // al menos 5s para un fingerprint válido

        bufferLock.lock()
        let snapshot = pcmBuffer
        bufferLock.unlock()

        guard snapshot.count >= minimum else { return nil }

        let slice = snapshot.suffix(needed)
        var int16Data = Data(capacity: slice.count * 2)
        for sample in slice {
            let clamped = max(-1.0, min(1.0, sample))
            let int16   = Int16(clamped * Float(Int16.max))
            withUnsafeBytes(of: int16.littleEndian) { int16Data.append(contentsOf: $0) }
        }
        return int16Data
    }

    // MARK: - Errors
    enum CaptureError: Error {
        case noDisplay
        case noPermission
    }
}

// MARK: - SCStreamDelegate
extension AudioCaptureManager: SCStreamDelegate {
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        print("[Audio] Stream detenido con error: \(error.localizedDescription)")
        DispatchQueue.main.async { self.isCapturing = false }
    }
}

// MARK: - SCStreamOutput
extension AudioCaptureManager: SCStreamOutput {
    func stream(_ stream: SCStream,
                didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
                of type: SCStreamOutputType) {
        guard type == .audio else { return }
        guard let blockBuffer = CMSampleBufferGetDataBuffer(sampleBuffer) else { return }

        var dataLength = 0
        var dataPointer: UnsafeMutablePointer<Int8>?
        let status = CMBlockBufferGetDataPointer(
            blockBuffer, atOffset: 0,
            lengthAtOffsetOut: nil,
            totalLengthOut: &dataLength,
            dataPointerOut: &dataPointer
        )
        guard status == kCMBlockBufferNoErr, let ptr = dataPointer, dataLength > 0 else { return }

        // El formato de salida de ScreenCaptureKit es Float32 interleaved
        let sampleCount = dataLength / MemoryLayout<Float>.size
        let floatPtr    = ptr.withMemoryRebound(to: Float.self, capacity: sampleCount) { $0 }
        let samples     = Array(UnsafeBufferPointer(start: floatPtr, count: sampleCount))

        // RMS para detección de actividad
        let sumSquares = samples.reduce(Float(0)) { $0 + $1 * $1 }
        let rms = sqrt(sumSquares / Float(max(samples.count, 1)))

        // Actualizar buffer circular
        let maxSamples = sampleRate * maxBufferSeconds
        bufferLock.lock()
        pcmBuffer.append(contentsOf: samples)
        if pcmBuffer.count > maxSamples {
            pcmBuffer.removeFirst(pcmBuffer.count - maxSamples)
        }
        bufferLock.unlock()

        DispatchQueue.main.async { self.currentRMS = rms }
    }
}
