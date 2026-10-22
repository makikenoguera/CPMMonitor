import Foundation

/// Genera una huella acústica Chromaprint a partir de datos PCM usando `fpcalc`.
/// `fpcalc` es el CLI oficial de Chromaprint (brew install chromaprint).
/// Para builds de producción, incluir `fpcalc` dentro del bundle en Contents/Helpers/.
struct FingerprintEngine {

    struct Fingerprint {
        let value:    String   // string Chromaprint (base64url)
        let duration: Int      // duración en segundos detectada por fpcalc
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

    // MARK: - Generar fingerprint
    /// Input: PCM s16le, 16000 Hz, 1 canal (mono).
    /// Escribe a archivo temporal → ejecuta fpcalc → parsea salida → borra archivo.
    static func generate(from pcmData: Data,
                         sampleRate: Int = 16000,
                         channels: Int   = 1) -> Fingerprint? {
        guard let fpcalc = fpcalcPath else {
            print("[Fingerprint] fpcalc no encontrado. Instalar: brew install chromaprint")
            return nil
        }
        guard pcmData.count > 0 else { return nil }

        // Archivo temporal
        let tempDir = FileManager.default.temporaryDirectory
        let tempFile = tempDir.appendingPathComponent("cpm_audio_\(UInt64(Date().timeIntervalSince1970 * 1000)).raw")

        do {
            try pcmData.write(to: tempFile)
        } catch {
            print("[Fingerprint] Error escribiendo temp: \(error)")
            return nil
        }
        defer { try? FileManager.default.removeItem(at: tempFile) }

        // Ejecutar fpcalc con PCM raw
        let process = Process()
        process.executableURL = URL(fileURLWithPath: fpcalc)
        process.arguments = [
            // NO usar -raw: ese flag hace que fpcalc emita enteros separados por coma
            // (formato no comprimido) en lugar de base64url Chromaprint comprimido.
            // Sin -raw, fpcalc sigue leyendo el PCM crudo gracias a -format s16le,
            // pero emite el fingerprint en formato estándar base64url que el servidor puede decodificar.
            "-rate",     "\(sampleRate)",
            "-channels", "\(channels)",
            "-format",   "s16le",
            "-length",   "12",      // máx 12s para el fingerprint
            tempFile.path
        ]

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
            print("[Fingerprint] fpcalc terminó con error: \(err)")
            return nil
        }

        let output = String(data: stdout.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        return parse(fpcalcOutput: output)
    }

    // MARK: - Parsear salida de fpcalc
    /// Formato esperado:
    ///   DURATION=214
    ///   FINGERPRINT=AQADtJmibcmS...
    private static func parse(fpcalcOutput: String) -> Fingerprint? {
        var duration: Int?
        var fingerprint: String?

        for line in fpcalcOutput.components(separatedBy: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("DURATION=") {
                duration = Int(trimmed.dropFirst("DURATION=".count))
            } else if trimmed.hasPrefix("FINGERPRINT=") {
                fingerprint = String(trimmed.dropFirst("FINGERPRINT=".count))
            }
        }

        guard let d = duration, let fp = fingerprint, !fp.isEmpty else { return nil }
        return Fingerprint(value: fp, duration: d)
    }
}
