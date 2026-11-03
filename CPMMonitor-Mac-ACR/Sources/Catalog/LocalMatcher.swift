import Foundation

/// Identifica canciones comparando un fingerprint de consulta contra el catálogo local.
/// Todo el matching ocurre en memoria — sin red, sin latencia de red.
///
/// Algoritmo: ventana deslizante de Hamming sobre arrays Int32 + verificación posicional.
///
/// La verificación posicional es clave para eliminar falsos positivos:
/// divide el query en dos mitades y comprueba que sus mejores offsets en el catálogo
/// sean consecutivos (±tolerancia). Un match real siempre produce offsets coherentes;
/// un falso positivo tiene offsets aleatorios en cada mitad.
final class LocalMatcher {
    static let shared = LocalMatcher()

    struct MatchResult {
        let id:          Int
        let artista:     String
        let titulo:      String
        let isrc:        String
        let durationSeg: Double
        let score:       Float
        let inCatalog:   Bool   // active=true → track en ciclo de pagos vigente
        let isPromovida: Bool   // true si es una canción actualmente promovida
    }

    // MARK: - Índice en memoria
    private struct Entry {
        let id:          Int
        let artista:     String
        let titulo:      String
        let isrc:        String
        let durationSeg: Double
        let fp:          [Int32]
        let active:      Bool
        let isPromovida: Bool
    }

    private var index:          [Entry] = []
    private var indexPromovidas: [Entry] = []  // subíndice: solo canciones promovidas
    /// Threshold principal de score (ventana completa).
    private let threshold: Float = 0.70
    /// Threshold mínimo que debe cumplir CADA mitad en la verificación posicional.
    private let halfThreshold: Float = 0.62
    /// Tolerancia del gap entre offsets de las dos mitades (±50% del halfLen).
    private let gapToleranceFactor: Int = 2
    private let queue = DispatchQueue(label: "sumartered.matcher", qos: .userInitiated)

    private init() {}

    // MARK: - Cargar / recargar índice
    func reload() {
        let rows = CatalogStore.shared.loadAll()
        let entries = rows.map { row in
            Entry(id: row.id, artista: row.artista, titulo: row.titulo,
                  isrc: row.isrc, durationSeg: row.durationSeg,
                  fp: row.fp, active: row.active, isPromovida: row.isPromovida)
        }
        let promos = entries.filter { $0.isPromovida }
        queue.sync {
            self.index           = entries
            self.indexPromovidas = promos
        }
        print("[LocalMatcher] Índice cargado: \(entries.count) tracks (\(promos.count) promovidas)")
    }

    var trackCount: Int { queue.sync { index.count } }

    // MARK: - Match
    /// Busca el mejor match para `query` en el catálogo local.
    /// Fase 1: revisa primero las canciones promovidas (subíndice pequeño y rápido).
    /// Fase 2: si no hay match, revisa el catálogo completo.
    /// Llamar desde un hilo background (puede tomar 50-200ms para 4500 tracks).
    func match(query: [Int32]) -> MatchResult? {
        guard !query.isEmpty else { return nil }

        // Fase 1: promovidas primero (rápido — pocas canciones)
        if let result = searchInIndex(query: query, entries: indexPromovidas, label: "promovidas") {
            print("[LocalMatcher] ⭐ Promovida: \(result.artista) - \(result.titulo) (score=\(String(format: "%.3f", result.score)))")
            return result
        }

        // Fase 2: catálogo completo
        if let result = searchInIndex(query: query, entries: index, label: "completo") {
            print("[LocalMatcher] ✅ \(result.artista) - \(result.titulo) (score=\(String(format: "%.3f", result.score)), active=\(result.inCatalog))")
            return result
        }

        return nil
    }

    /// Búsqueda interna sobre un subíndice dado.
    private func searchInIndex(query: [Int32], entries: [Entry], label: String) -> MatchResult? {
        guard !entries.isEmpty else { return nil }

        var bestScore: Float = 0
        var bestEntry: Entry?
        var bestOffset: Int = 0

        queue.sync {
            for entry in entries {
                let (score, offset) = slidingScoreAndOffset(query: query, ref: entry.fp)
                if score > bestScore {
                    bestScore = score
                    bestEntry = entry
                    bestOffset = offset
                    if bestScore > 0.92 { return }  // excelente — salir temprano
                }
            }
        }

        guard bestScore >= threshold, let entry = bestEntry else {
            if bestScore > 0.50 {
                print("[LocalMatcher] Sin match en \(label) (mejor score: \(String(format: "%.3f", bestScore)))")
            }
            return nil
        }

        // Verificación posicional: las dos mitades del query deben coincidir con
        // secciones CONSECUTIVAS del catálogo. Filtra falsos positivos donde una
        // sola ventana afortunada infla el score pero las mitades apuntan a
        // posiciones aleatorias e inconsistentes.
        guard positionalConsistency(query: query, ref: entry.fp) else {
            print("[LocalMatcher] ⚠️ Rechazado (\(label), offsets inconsistentes): \(entry.artista) - \(entry.titulo) (score=\(String(format: "%.3f", bestScore)), offset=\(bestOffset))")
            return nil
        }

        return MatchResult(
            id:          entry.id,
            artista:     entry.artista,
            titulo:      entry.titulo,
            isrc:        entry.isrc,
            durationSeg: entry.durationSeg,
            score:       bestScore,
            inCatalog:   entry.active,
            isPromovida: entry.isPromovida
        )
    }

    // MARK: - Verificación posicional
    /// Divide el query en dos mitades y verifica que sus mejores offsets en `ref`
    /// estén separados por ≈ halfLen (con tolerancia).
    ///
    /// Para un match real:
    ///   primera mitad → offset X   (ej. 200)
    ///   segunda mitad  → offset X + halfLen (ej. 270)
    ///   gap = 70 ≈ halfLen ✅
    ///
    /// Para un falso positivo:
    ///   primera mitad → offset X   (ej. 50)
    ///   segunda mitad  → offset Y   (ej. 600)   (aleatorio)
    ///   gap = 550 ≠ halfLen ❌ → rechazado
    private func positionalConsistency(query: [Int32], ref: [Int32]) -> Bool {
        let halfLen = query.count / 2
        // Si el query es demasiado corto para dividir (~< 10s cada mitad), omitir la verificación
        guard halfLen >= 35, ref.count >= halfLen * 2 else { return true }

        let firstHalf  = Array(query[0..<halfLen])
        let secondHalf = Array(query[halfLen...])

        let (s1, off1) = slidingScoreAndOffset(query: firstHalf,  ref: ref)
        let (s2, off2) = slidingScoreAndOffset(query: secondHalf, ref: ref)

        // Ambas mitades deben superar el halfThreshold
        guard s1 >= halfThreshold, s2 >= halfThreshold else {
            print("[LocalMatcher] Consistency: s1=\(String(format:"%.3f",s1)) s2=\(String(format:"%.3f",s2)) — mitad débil")
            return false
        }

        // El gap entre offsets debe ser ≈ halfLen (la segunda mitad viene justo después)
        let actualGap   = off2 - off1
        let tolerance   = halfLen / gapToleranceFactor   // ±50%
        let gapOk       = abs(actualGap - halfLen) <= tolerance

        print("[LocalMatcher] Consistency: off1=\(off1) off2=\(off2) gap=\(actualGap) expected=\(halfLen) tol=\(tolerance) s1=\(String(format:"%.3f",s1)) s2=\(String(format:"%.3f",s2)) → \(gapOk ? "✅" : "❌")")
        return gapOk
    }

    // MARK: - Ventana deslizante de Hamming (devuelve score + offset)
    /// Desliza `query` sobre `ref` buscando la mejor alineación.
    /// Retorna (score, offset_del_mejor_match).
    /// Score = 1 − (bits_diferentes / bits_totales), rango 0–1.
    private func slidingScoreAndOffset(query: [Int32], ref: [Int32]) -> (Float, Int) {
        let qLen = query.count
        let rLen = ref.count
        guard qLen > 0, rLen >= qLen else { return (0, 0) }

        // Paso fino para clips cortos (≤120 valores ≈ 20s):
        // revisar cada posición para no perder el encaje real.
        // Para fingerprints largos (> 120), saltar qLen/8 posiciones.
        let step = qLen <= 120 ? 1 : max(1, qLen / 8)
        var best: Float = 0
        var bestOff: Int = 0

        var offset = 0
        while offset <= rLen - qLen {
            var diffBits = 0
            for i in 0..<qLen {
                // XOR bit a bit: bits distintos = 1, iguales = 0
                diffBits += (query[i] ^ ref[offset + i]).nonzeroBitCount
            }
            let score = 1.0 - Float(diffBits) / Float(qLen * 32)
            if score > best {
                best = score
                bestOff = offset
                if best > 0.92 { break }
            }
            offset += step
        }
        return (best, bestOff)
    }
}
