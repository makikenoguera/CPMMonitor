import Foundation

/// Genera una huella acústica Chromaprint a partir de datos PCM usando `fpcalc`.
/// `fpcalc` es el CLI oficial de Chromaprint (brew install chromaprint).
/// Para builds de producción, incluir `fpcalc` dentro del bundle en Contents/Helpers/.
struct FingerprintEngine {

    struct Fingerprint {
        let value:    String   // string Chromaprint (base64url) — para envío al servidor
        let duration: Int      // duración en segundos detectada por fpcalc
    }

    struct RawFingerprint {
        let values:   [Int32]  // int32 descomprimidos — para matching local
        let duration: Int
    }

    // MARK: - Localizar fpcalc
    /// Busca fpcalc en: bundle de la app → Homebrew Apple Silicon → Homebrew Intel
    static var fpcalcPath: String? {
        let candidates: [String] = [
            // Bundleado en la app (producción)
            Bundle.main.bundlePath + "/Contents/Helpers/fpcalc",
            // Homebrew Apple Silicon
            "/opt/homebrew/bin/fpcalc",
            // Homebrew Intel
            "/usr/local/bin/fpcalc",
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    static var isAvailable: Bool { fpcalcPath != nil }

    // MARK: - Generar fingerprint (raw int32 — matching local)
    /// Usa fpcalc con `-raw` → devuelve [Int32] descomprimidos.
    /// Este es el formato que usa LocalMatcher para comparar contra el catálogo local.
    static func generateRaw(from pcmData: Data,
                            sampleRate: Int = 16000,
                            channels: Int   = 1,
                            maxSeconds: Int = 20) -> RawFingerprint? {
        guard let output = runFpcalc(
            pcmData: pcmData, sampleRate: sampleRate, channels: channels,
            maxSeconds: maxSeconds, raw: true
        ) else { return nil }
        return parseRaw(fpcalcOutput: output)
    }

    /// Genera fingerprint en formato base64url (para envío al servidor legacy).
    static func generate(from pcmData: Data,
                         sampleRate: Int = 16000,
                         channels: Int   = 1,
                         maxSeconds: Int = 20) -> Fingerprint? {
        guard let output = runFpcalc(
            pcmData: pcmData, sampleRate: sampleRate, channels: channels,
            maxSeconds: maxSeconds, raw: false
        ) else { return nil }
        return parse(fpcalcOutput: output)
    }

    // MARK: - Núcleo compartido
    private static func runFpcalc(pcmData: Data,
                                   sampleRate: Int,
                                   channels: Int,
                                   maxSeconds: Int,
                                   raw: Bool) -> String? {
        guard let fpcalc = fpcalcPath else {
            print("[Fingerprint] fpcalc no encontrado. Instalar: brew install chromaprint")
            return nil
        }
        guard !pcmData.isEmpty else { return nil }

        let tempDir  = FileManager.default.temporaryDirectory
        let tempFile = tempDir.appendingPathComponent(
            "sr_audio_\(UInt64(Date().timeIntervalSince1970 * 1000)).raw"
        )
        do { try pcmData.write(to: tempFile) } catch { return nil }
        defer { try? FileManager.default.removeItem(at: tempFile) }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: fpcalc)
        var args = [
            "-rate",     "\(sampleRate)",
            "-channels", "\(channels)",
            "-format",   "s16le",
            "-length",   "\(maxSeconds)",
        ]
        if raw { args.append("-raw") }
        args.append(tempFile.path)
        process.arguments = args

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError  = stderr

        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            print("[Fingerprint] Error ejecutando fpcalc: \(error)")
            return nil
        }

        guard process.terminationStatus == 0 else {
            let err = String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            print("[Fingerprint] fpcalc error: \(err)")
            return nil
        }

        return String(data: stdout.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)
    }

    // MARK: - Parsear salida base64url
    /// DURATION=214 / FINGERPRINT=AQADtJmibcmS...
    private static func parse(fpcalcOutput: String) -> Fingerprint? {
        var duration: Int?
        var fingerprint: String?
        for line in fpcalcOutput.components(separatedBy: "\n") {
            let t = line.trimmingCharacters(in: .whitespaces)
            if t.hasPrefix("DURATION=")    { duration    = Int(t.dropFirst(9)) }
            else if t.hasPrefix("FINGERPRINT=") { fingerprint = String(t.dropFirst(12)) }
        }
        guard let d = duration, let fp = fingerprint, !fp.isEmpty else { return nil }
        return Fingerprint(value: fp, duration: d)
    }

    // MARK: - Parsear salida raw int32
    /// DURATION=214 / FINGERPRINT=12345678,-9012345,...
    private static func parseRaw(fpcalcOutput: String) -> RawFingerprint? {
        var duration: Int?
        var values: [Int32] = []
        for line in fpcalcOutput.components(separatedBy: "\n") {
            let t = line.trimmingCharacters(in: .whitespaces)
            if t.hasPrefix("DURATION=") {
                duration = Int(t.dropFirst(9))
            } else if t.hasPrefix("FINGERPRINT=") {
                let raw = String(t.dropFirst(12))
                values = raw.split(separator: ",").compactMap { Int32($0.trimmingCharacters(in: .whitespaces)) }
            }
        }
        guard let d = duration, values.count >= 10 else { return nil }
        return RawFingerprint(values: values, duration: d)
    }
}
