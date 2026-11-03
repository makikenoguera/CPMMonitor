import Foundation

struct SpotifyScanner {

    static func currentTrack() -> TrackInfo? {
        guard AppleScriptRunner.isRunning("Spotify") else { return nil }

        // Obtenemos la pista SIEMPRE (pausada o reproduciendo) + posición actual
        let script = """
        tell application "Spotify"
            try
                set t to current track
                set pos to player position
                set playing to (player state is playing)
                return (artist of t) & "|||" & (name of t) & "|||" & (duration of t) & "|||" & (id of t) & "|||" & pos & "|||" & playing
            end try
        end tell
        """
        guard let raw = AppleScriptRunner.run(script), !raw.isEmpty else { return nil }

        let parts = raw.components(separatedBy: "|||")
        guard parts.count >= 6 else { return nil }

        let artista   = parts[0].trimmingCharacters(in: .whitespaces)
        let titulo    = parts[1].trimmingCharacters(in: .whitespaces)
        // Spotify devuelve duración en milisegundos
        let durMs     = Double(parts[2].trimmingCharacters(in: .whitespaces)) ?? 0
        let durSeg    = durMs / 1000.0
        let spotifyId = parts[3].trimmingCharacters(in: .whitespaces)
        let position  = Double(parts[4].trimmingCharacters(in: .whitespaces)) ?? 0
        let isPlaying = parts[5].trimmingCharacters(in: .whitespaces) == "true"

        guard !artista.isEmpty, !titulo.isEmpty, durSeg > 0 else { return nil }

        return TrackInfo(
            fuente:         "spotify",
            artista:        artista,
            titulo:         titulo,
            duracionSeg:    durSeg,
            isrc:           spotifyId,
            isPlaying:      isPlaying,
            playerPosition: position
        )
    }
}
