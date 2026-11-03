import Foundation

struct AppleMusicScanner {

    static func currentTrack() -> TrackInfo? {
        guard AppleScriptRunner.isRunning("Music") else { return nil }

        let script = """
        tell application "Music"
            try
                set t to current track
                set pos to player position
                set playing to (player state is playing)
                try
                    set isrcVal to (get ISRC of t)
                on error
                    set isrcVal to ""
                end try
                return (artist of t) & "|||" & (name of t) & "|||" & (duration of t) & "|||" & isrcVal & "|||" & pos & "|||" & playing
            end try
        end tell
        """
        guard let raw = AppleScriptRunner.run(script), !raw.isEmpty else { return nil }

        let parts = raw.components(separatedBy: "|||")
        guard parts.count >= 6 else { return nil }

        let artista   = parts[0].trimmingCharacters(in: .whitespaces)
        let titulo    = parts[1].trimmingCharacters(in: .whitespaces)
        let durSeg    = Double(parts[2].trimmingCharacters(in: .whitespaces)) ?? 0
        let isrc      = parts[3].trimmingCharacters(in: .whitespaces)
        let position  = Double(parts[4].trimmingCharacters(in: .whitespaces)) ?? 0
        let isPlaying = parts[5].trimmingCharacters(in: .whitespaces) == "true"

        guard !artista.isEmpty, !titulo.isEmpty, durSeg > 0 else { return nil }

        return TrackInfo(
            fuente:         "applemusic",
            artista:        artista,
            titulo:         titulo,
            duracionSeg:    durSeg,
            isrc:           isrc,
            isPlaying:      isPlaying,
            playerPosition: position
        )
    }
}
