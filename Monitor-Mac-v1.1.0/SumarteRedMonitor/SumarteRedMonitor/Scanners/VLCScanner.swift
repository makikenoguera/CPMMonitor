import Foundation

struct VLCScanner {

    static func currentTrack() -> TrackInfo? {
        guard AppleScriptRunner.isRunning("VLC") else { return nil }

        let script = """
        tell application "VLC"
            try
                if playing then
                    set t to current time
                    set n to name of current item
                    set d to duration of current item
                    return n & "||" & d & "||" & t
                end if
            end try
        end tell
        """
        guard let raw = AppleScriptRunner.run(script) else { return nil }
        let parts = raw.components(separatedBy: "||")
        guard parts.count >= 1 else { return nil }

        let rawName        = parts[0].trimmingCharacters(in: .whitespaces)
        let durSeg         = parts.count >= 2 ? (Double(parts[1].trimmingCharacters(in: .whitespaces)) ?? 0) : 0
        let playerPosition = parts.count >= 3 ? Double(parts[2].trimmingCharacters(in: .whitespaces)) : nil

        // VLC muestra el nombre del archivo o metadata "Artista - Titulo"
        let (artista, titulo) = splitArtistTitle(rawName)

        guard !titulo.isEmpty else { return nil }

        return TrackInfo(
            fuente:         "vlc",
            artista:        artista,
            titulo:         titulo,
            duracionSeg:    durSeg,
            isrc:           "",
            isPlaying:      true,
            playerPosition: playerPosition
        )
    }

    private static func splitArtistTitle(_ raw: String) -> (String, String) {
        // Quitar extensión si viene de path
        var name = raw
        if let last = name.split(separator: "/").last { name = String(last) }
        // Quitar extensión .mp3 .flac etc.
        let noExt = name.replacingOccurrences(of: #"\.\w{2,4}$"#, with: "",
                                              options: .regularExpression)
        let parts = noExt.components(separatedBy: " - ")
        if parts.count >= 2 {
            return (parts[0].trimmingCharacters(in: .whitespaces),
                    parts.dropFirst().joined(separator: " - ").trimmingCharacters(in: .whitespaces))
        }
        return ("", noExt.trimmingCharacters(in: .whitespaces))
    }
}
