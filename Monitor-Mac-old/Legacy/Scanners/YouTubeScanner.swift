import Foundation

/// Detecta reproducción de YouTube en CUALQUIER pestaña de Chrome o Safari,
/// incluso si la pestaña no está activa (video en background).
/// — Con Chrome JS habilitado: obtiene posición y duración reales del <video>
/// — Sin Chrome JS: fallback a título de pestaña + tiempo acumulado
struct YouTubeScanner {

    static func currentTrack() -> TrackInfo? {
        if let track = fromChrome() { return track }
        if let track = fromSafari() { return track }
        return nil
    }

    // MARK: - Chrome
    private static func fromChrome() -> TrackInfo? {
        guard AppleScriptRunner.isRunning("Google Chrome") else { return nil }

        // Busca en TODAS las ventanas y pestañas.
        // Intenta JS para obtener posición real; si JS está desactivado,
        // retorna solo el título (modo fallback).
        let script = """
        tell application "Google Chrome"
            try
                repeat with w in every window
                    repeat with t in every tab of w
                        if URL of t contains "youtube.com/watch" then
                            set tabTitle to name of t
                            try
                                set jsData to execute t javascript "var v=document.querySelector('video');v&&v.readyState>=2&&v.duration>0?(v.currentTime+'|||'+v.duration+'|||'+(!v.paused)):''"
                                if jsData is not "" and jsData is not missing value then
                                    return "JS|||" & jsData & "|||" & tabTitle
                                else
                                    return "TITLE|||" & tabTitle
                                end if
                            on error
                                return "TITLE|||" & tabTitle
                            end try
                        end if
                    end repeat
                end repeat
            end try
        end tell
        """
        guard let raw = AppleScriptRunner.run(script), !raw.isEmpty else { return nil }
        return parseChromeResult(raw)
    }

    // MARK: - Safari (todas las pestañas, fallback a título)
    private static func fromSafari() -> TrackInfo? {
        guard AppleScriptRunner.isRunning("Safari") else { return nil }

        let script = """
        tell application "Safari"
            try
                repeat with w in every window
                    repeat with t in tabs of w
                        if URL of t contains "youtube.com/watch" then
                            return name of t
                        end if
                    end repeat
                end repeat
            end try
        end tell
        """
        guard let title = AppleScriptRunner.run(script), !title.isEmpty else { return nil }
        return buildTrack(rawTitle: title, currentTime: nil, duration: 0, isPlaying: true)
    }

    // MARK: - Parsear resultado de Chrome
    private static func parseChromeResult(_ raw: String) -> TrackInfo? {
        if raw.hasPrefix("JS|||") {
            // "JS|||currentTime|||duration|||isPlaying|||Titulo del tab"
            let body  = String(raw.dropFirst(5))
            let parts = body.components(separatedBy: "|||")
            guard parts.count >= 4 else { return nil }

            let currentTime = Double(parts[0].trimmingCharacters(in: .whitespaces)) ?? 0
            let duration    = Double(parts[1].trimmingCharacters(in: .whitespaces)) ?? 0
            let isPlaying   = parts[2].trimmingCharacters(in: .whitespaces) == "true"
            let rawTitle    = parts[3...].joined(separator: "|||")

            guard duration > 0 else { return nil }
            return buildTrack(rawTitle: rawTitle, currentTime: currentTime,
                              duration: duration, isPlaying: isPlaying)

        } else if raw.hasPrefix("TITLE|||") {
            // Modo fallback: solo título, sin posición ni duración
            let rawTitle = String(raw.dropFirst(8))
            return buildTrack(rawTitle: rawTitle, currentTime: nil, duration: 0, isPlaying: true)
        }
        return nil
    }

    // MARK: - Construir TrackInfo
    private static func buildTrack(rawTitle: String,
                                   currentTime: Double?,
                                   duration: Double,
                                   isPlaying: Bool) -> TrackInfo? {
        // Quitar sufijo " - YouTube"
        var cleaned = rawTitle
        if let range = cleaned.range(of: " - YouTube", options: .backwards) {
            cleaned = String(cleaned[..<range.lowerBound])
        }
        // Quitar contadores de notificación "(42) Titulo"
        cleaned = cleaned.replacingOccurrences(of: #"^\(\d+\)\s*"#, with: "",
                                               options: .regularExpression)
        cleaned = cleaned.trimmingCharacters(in: .whitespaces)
        guard !cleaned.isEmpty else { return nil }

        let (artista, titulo) = splitArtistTitle(cleaned)

        return TrackInfo(
            fuente:         "youtube",
            artista:        artista,
            titulo:         titulo.isEmpty ? cleaned : titulo,
            duracionSeg:    duration,
            isrc:           "",
            isPlaying:      isPlaying,
            playerPosition: currentTime
        )
    }

    private static func splitArtistTitle(_ raw: String) -> (String, String) {
        let parts = raw.components(separatedBy: " - ")
        if parts.count >= 2 {
            return (parts[0].trimmingCharacters(in: .whitespaces),
                    parts.dropFirst().joined(separator: " - ").trimmingCharacters(in: .whitespaces))
        }
        return ("", raw.trimmingCharacters(in: .whitespaces))
    }
}
