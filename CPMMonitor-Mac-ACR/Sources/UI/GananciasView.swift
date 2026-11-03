import SwiftUI

// MARK: - Periodo

private enum PeriodType: String, CaseIterable {
    case today  = "Hoy"
    case week   = "Esta semana"
    case month  = "Este mes"
    case custom = "Personalizado"
}

// MARK: - Modelo agrupado por canción promovida

private struct PromoGroup: Identifiable {
    let id: String          // ISRC o "artista|titulo"
    let titulo: String
    let artista: String
    let tarifaVenue: Double
    var plays: [PlayRecord] // ordenados desc

    var count: Int      { plays.count }
    var earnings: Double { Double(count) * tarifaVenue }
    var lastDate: Date? {
        plays.first.map { Date(timeIntervalSince1970: $0.createdAt) }
    }
}

// MARK: - Vista principal

struct GananciasView: View {
    @StateObject private var config = ConfigManager.shared

    // Periodo
    @State private var periodType: PeriodType = .month
    @State private var startDate: Date = Calendar.current.startOfMonth()
    @State private var endDate: Date   = Date()
    @State private var showCustomPicker = false

    // Datos
    @State private var promovidas: [PromovidaRemota] = []
    @State private var allPlays:   [PlayRecord]      = []
    @State private var isLoading                      = false

    // MARK: Computed — sólo plays que coinciden con una promovida y son efectivos
    private var promoGroups: [PromoGroup] {
        guard !promovidas.isEmpty else { return [] }

        // Índice de promovidas: ISRC → promovida (primero), luego título normalizado
        var byISRC:  [String: PromovidaRemota] = [:]
        var byTitle: [String: PromovidaRemota] = [:]
        for p in promovidas where p.activa {
            if !p.isrc.isEmpty { byISRC[p.isrc.uppercased()] = p }
            byTitle[normalizeTitle(p.titulo)] = p
        }

        // Para cada play efectivo (≥80%), busca si coincide con una promovida.
        // Se usa porcentaje directamente (no ganodinero) porque una promovida puede
        // no estar en el catálogo local pero sí ser detectada por ACR.
        var groups: [String: PromoGroup] = [:]
        for play in allPlays where play.porcentaje >= 80 {
            let promo: PromovidaRemota?
            let isrcKey = play.isrc.uppercased()
            if !play.isrc.isEmpty, let p = byISRC[isrcKey] {
                promo = p
            } else {
                promo = byTitle[normalizeTitle(play.titulo)]
            }
            guard let p = promo else { continue }

            let groupId = !p.isrc.isEmpty ? p.isrc.uppercased()
                        : "\(p.artistaNombre)|\(p.titulo)"
            if groups[groupId] == nil {
                groups[groupId] = PromoGroup(
                    id:          groupId,
                    titulo:      p.titulo,
                    artista:     p.artistaNombre,
                    tarifaVenue: p.tarifaVenue,
                    plays:       []
                )
            }
            groups[groupId]?.plays.append(play)
        }
        // Ordenar por earnings desc, luego por título (sort estable — evita flickering
        // cuando varias canciones tienen la misma ganancia y ContentView redibuja frecuente)
        return groups.values.sorted {
            if $0.earnings != $1.earnings { return $0.earnings > $1.earnings }
            return $0.titulo < $1.titulo
        }
    }

    private var totalPlays:    Int    { promoGroups.reduce(0) { $0 + $1.count } }
    private var totalEarnings: Double { promoGroups.reduce(0) { $0 + $1.earnings } }

    // MARK: Body

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {

                // ── Métricas ────────────────────────────────────────────────
                HStack(spacing: 10) {
                    metricCard(
                        value:  "\(totalPlays)",
                        label:  "REPRODUCCIONES PROMOVIDAS",
                        color:  SRColor.srGreen,
                        icon:   "star.fill"
                    )
                    incomeCard(
                        amount: totalEarnings,
                        label:  "TU INGRESO",
                        color:  SRColor.srGreen
                    )
                }
                .padding(.horizontal, 14)
                .padding(.top, 14)
                .padding(.bottom, 12)

                Divider().overlay(SRColor.border).padding(.horizontal, 14)

                // ── Período ─────────────────────────────────────────────────
                VStack(alignment: .leading, spacing: 8) {
                    // Selector mes / personalizado
                    HStack(spacing: 0) {
                        ForEach(PeriodType.allCases, id: \.self) { pt in
                            Button {
                                periodType = pt
                                showCustomPicker = false
                                switch pt {
                                case .today:
                                    startDate = Calendar.current.startOfDay(for: Date())
                                    endDate   = Date()
                                    load()
                                case .week:
                                    startDate = Calendar.current.startOfWeek()
                                    endDate   = Date()
                                    load()
                                case .month:
                                    startDate = Calendar.current.startOfMonth()
                                    endDate   = Date()
                                    load()
                                case .custom:
                                    showCustomPicker = true
                                }
                            } label: {
                                Text(pt.rawValue)
                                    .font(.system(size: 11, weight: periodType == pt ? .semibold : .regular))
                                    .foregroundColor(periodType == pt ? SRColor.brand : SRColor.textSecond)
                                    .padding(.horizontal, 14)
                                    .padding(.vertical, 6)
                                    .background(periodType == pt ? SRColor.brand.opacity(0.10) : Color.clear)
                                    .cornerRadius(6)
                            }
                            .buttonStyle(.plain)
                        }
                        Spacer()
                        Text(periodLabel)
                            .font(.system(size: 11))
                            .foregroundColor(SRColor.textSecond)
                            .padding(.trailing, 14)
                    }
                    .padding(.leading, 14)
                    .padding(.top, 12)

                    // Pickers personalizados
                    if showCustomPicker {
                        HStack(spacing: 12) {
                            DatePicker("Desde", selection: $startDate, displayedComponents: .date)
                                .font(.system(size: 12))
                                .labelsHidden()
                            Text("→").foregroundColor(SRColor.textSecond)
                            DatePicker("Hasta", selection: $endDate, displayedComponents: .date)
                                .font(.system(size: 12))
                                .labelsHidden()
                            Button("Aplicar") { load() }
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundColor(.white)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 5)
                                .background(SRColor.brand)
                                .cornerRadius(6)
                                .buttonStyle(.plain)
                        }
                        .padding(.horizontal, 14)
                        .padding(.bottom, 4)
                        .onChange(of: startDate) { _ in }
                        .onChange(of: endDate)   { _ in }
                    }
                }

                Divider().overlay(SRColor.border).padding(.horizontal, 14).padding(.top, 4)

                // ── Tabla de promovidas ──────────────────────────────────────
                if isLoading {
                    HStack { Spacer(); ProgressView().scaleEffect(0.7); Spacer() }
                        .padding(.vertical, 30)
                } else if promoGroups.isEmpty {
                    emptyState
                } else {
                    promoTable
                }

                Spacer(minLength: 14)
            }
        }
        .background(SRColor.pageBg)
        .onAppear { load() }
    }

    // MARK: - Tabla

    private var promoTable: some View {
        VStack(spacing: 0) {
            // Header de tabla
            HStack(spacing: 0) {
                Text("CANCIÓN")
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text("SONÓ")
                    .frame(width: 50, alignment: .center)
                Text("ÚLTIMA VEZ")
                    .frame(width: 90, alignment: .center)
                Text("GANANCIA")
                    .frame(width: 100, alignment: .trailing)
            }
            .font(.system(size: 9, weight: .semibold))
            .foregroundColor(SRColor.textLabel)
            .kerning(0.3)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)

            Divider().overlay(SRColor.border).padding(.horizontal, 14)

            ForEach(promoGroups) { group in
                promoRow(group)
                Divider().overlay(SRColor.border).padding(.leading, 14)
            }

            // Totales
            HStack(spacing: 0) {
                Text("TOTAL")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(SRColor.textLabel)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text("\(totalPlays)")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(SRColor.srGreen)
                    .frame(width: 50, alignment: .center)
                Spacer().frame(width: 90)
                Text(formatCOP(totalEarnings))
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(SRColor.srGreen)
                    .frame(width: 100, alignment: .trailing)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(SRColor.srGreen.opacity(0.05))
        }
        .padding(.top, 4)
    }

    private func promoRow(_ group: PromoGroup) -> some View {
        HStack(spacing: 0) {
            // Canción
            VStack(alignment: .leading, spacing: 2) {
                Text(group.titulo)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(SRColor.textPrimary)
                    .lineLimit(1)
                Text(group.artista)
                    .font(.system(size: 10))
                    .foregroundColor(SRColor.textSecond)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // Plays
            Text("\(group.count)")
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(SRColor.brand)
                .frame(width: 50, alignment: .center)

            // Última vez
            Text(group.lastDate.map { shortDateTime($0) } ?? "—")
                .font(.system(size: 10))
                .foregroundColor(SRColor.textSecond)
                .multilineTextAlignment(.center)
                .frame(width: 90, alignment: .center)

            // Ganancia
            Text(formatCOP(group.earnings))
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(SRColor.srGreen)
                .frame(width: 100, alignment: .trailing)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(SRColor.cardBg)
    }

    // MARK: - Empty state

    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "star.slash")
                .font(.system(size: 32))
                .foregroundColor(SRColor.textLabel)
            Text(promovidas.isEmpty ? "Sin canciones promovidas" : "Sin reproducciones promovidas en el período")
                .font(.system(size: 13))
                .foregroundColor(SRColor.textSecond)
            if !promovidas.isEmpty {
                Text("Las canciones promovidas generan ingresos cuando se detectan con ≥80% de coincidencia")
                    .font(.system(size: 11))
                    .foregroundColor(SRColor.textLabel)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 30)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }

    // MARK: - Components

    private func metricCard(value: String, label: String, color: Color, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Rectangle().fill(color).frame(height: 2).cornerRadius(1)
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(label)
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(SRColor.textLabel)
                        .kerning(0.3)
                    Text(value)
                        .font(.system(size: 28, weight: .bold))
                        .foregroundColor(color)
                }
                Spacer()
                Image(systemName: icon)
                    .font(.system(size: 18))
                    .foregroundColor(color.opacity(0.25))
            }
            .padding(.horizontal, 12).padding(.bottom, 12)
        }
        .background(SRColor.cardBg)
        .cornerRadius(8)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(SRColor.border, lineWidth: 1))
    }

    private func incomeCard(amount: Double, label: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Rectangle().fill(color).frame(height: 2).cornerRadius(1)
            VStack(alignment: .leading, spacing: 4) {
                Text(label)
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(SRColor.textLabel)
                    .kerning(0.3)
                Text(formatCOP(amount))
                    .font(.system(size: 24, weight: .bold))
                    .foregroundColor(color)
                    .minimumScaleFactor(0.7)
                    .lineLimit(1)
                Text("por plays promovidos efectivos")
                    .font(.system(size: 9))
                    .foregroundColor(SRColor.textSecond)
            }
            .padding(.horizontal, 12).padding(.bottom, 12)
        }
        .background(SRColor.cardBg)
        .cornerRadius(8)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(SRColor.border, lineWidth: 1))
    }

    // MARK: - Data

    private func load() {
        isLoading = true
        allPlays = DatabaseManager.shared.fetchPlaysInRange(from: startDate, to: endDate)
        loadPromovidas()
    }

    private func loadPromovidas() {
        guard !config.config.serverURL.isEmpty else {
            isLoading = false
            return
        }
        guard let url = URL(string: "\(config.config.serverURL)/v1/promovidas") else {
            isLoading = false
            return
        }
        var req = URLRequest(url: url, timeoutInterval: 15)
        if !config.config.apiKey.isEmpty {
            req.setValue(config.config.apiKey, forHTTPHeaderField: "X-API-Key")
        }
        URLSession.shared.dataTask(with: req) { data, _, _ in
            DispatchQueue.main.async {
                if let data = data,
                   let list = try? JSONDecoder().decode([PromovidaRemota].self, from: data) {
                    promovidas = list.filter { $0.activa }
                }
                isLoading = false
            }
        }.resume()
    }

    // MARK: - Helpers

    /// Normaliza un título para matching flexible:
    /// quita número de pista al inicio, minúsculas, elimina acentos.
    private func normalizeTitle(_ title: String) -> String {
        var t = title.trimmingCharacters(in: .whitespaces)
        // Quitar número de pista: "16 Título", "01. Título", "Track 3 - Título"
        if let range = t.range(of: #"^(?:track\s*)?\d+[\s\.\-\)]+"#,
                                options: [.regularExpression, .caseInsensitive]) {
            t = String(t[range.upperBound...])
        }
        // Minúsculas y sin acentos
        return t.lowercased().folding(options: .diacriticInsensitive, locale: .current)
            .trimmingCharacters(in: .whitespaces)
    }

    private var periodLabel: String {
        switch periodType {
        case .today:  return "Hoy, \(dayFmt(Date()))"
        case .week:   let f = DateFormatter(); f.dateFormat = "dd MMM"; return "\(f.string(from: startDate)) – \(f.string(from: endDate))"
        case .month:  let f = DateFormatter(); f.dateFormat = "MMMM yyyy"; return f.string(from: Date())
        case .custom: let f = DateFormatter(); f.dateFormat = "dd MMM"; return "\(f.string(from: startDate)) – \(f.string(from: endDate))"
        }
    }
    private func dayFmt(_ d: Date) -> String {
        let f = DateFormatter(); f.dateFormat = "dd MMM yyyy"; return f.string(from: d)
    }

    private func shortDateTime(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "dd/MM\nHH:mm"
        return f.string(from: date)
    }

    private func formatCOP(_ amount: Double) -> String {
        let f = NumberFormatter()
        f.numberStyle          = .decimal
        f.maximumFractionDigits = 0
        f.groupingSeparator    = "."
        return "$\(f.string(from: NSNumber(value: amount)) ?? "\(Int(amount))") COP"
    }
}

// MARK: - Calendar helper

private extension Calendar {
    func startOfMonth() -> Date {
        let c = dateComponents([.year, .month], from: Date())
        return date(from: c) ?? Date()
    }
    func startOfWeek() -> Date {
        let c = dateComponents([.yearForWeekOfYear, .weekOfYear], from: Date())
        return date(from: c) ?? Date()
    }
}
