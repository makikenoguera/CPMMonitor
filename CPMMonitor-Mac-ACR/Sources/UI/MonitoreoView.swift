import SwiftUI

struct MonitoreoView: View {
    let history: [PlayRecord]

    var body: some View {
        if history.isEmpty {
            VStack(spacing: 12) {
                Image(systemName: "waveform.and.magnifyingglass")
                    .font(.system(size: 36)).foregroundColor(SRColor.textLabel)
                Text("Sin reproducciones registradas")
                    .font(.subheadline).foregroundColor(SRColor.textSecond)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity).padding(.top, 40)
        } else {
            ScrollView {
                LazyVStack(spacing: 0) {
                    // Summary bar
                    let efectivos   = history.filter { $0.ganodinero }.count
                    let promovidas  = history.filter { $0.inCatalog }.count
                    let noPromov    = history.count - promovidas
                    HStack(spacing: 0) {
                        HStack(spacing: 4) {
                            Image(systemName: "star.fill")
                                .font(.system(size: 9))
                                .foregroundColor(efectivos > 0 ? SRColor.srGreen : SRColor.brand)
                            Text("\(efectivos) pagadas")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundColor(efectivos > 0 ? SRColor.srGreen : SRColor.textSecond)
                        }
                        Text("  ·  ").font(.system(size: 11)).foregroundColor(SRColor.textLabel)
                        Text("\(promovidas) promovidas")
                            .font(.system(size: 11))
                            .foregroundColor(SRColor.brand)
                        if noPromov > 0 {
                            Text("  ·  ").font(.system(size: 11)).foregroundColor(SRColor.textLabel)
                            Text("\(noPromov) otras")
                                .font(.system(size: 11))
                                .foregroundColor(SRColor.textSecond)
                        }
                        Spacer()
                        Text("\(history.count) total")
                            .font(.system(size: 11)).foregroundColor(SRColor.textSecond)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 8)
                    .background(SRColor.pageBg)

                    Divider().overlay(SRColor.border)

                    ForEach(history) { record in
                        monitoreoRow(record)
                        Divider().overlay(SRColor.border).padding(.leading, 14)
                    }
                }
            }
            .background(SRColor.pageBg)
        }
    }

    private func monitoreoRow(_ r: PlayRecord) -> some View {
        let qualifying   = r.ganodinero                        // promovida + ≥80% → SE PAGA
        let enProgreso   = r.isPromovida && !qualifying        // promovida pero aún no llega al umbral
        let partial      = r.porcentaje >= 50 && !qualifying

        let rowBg: Color = qualifying  ? SRColor.srGreen.opacity(0.07)
                         : enProgreso  ? SRColor.brand.opacity(0.05)
                         :               SRColor.cardBg

        return VStack(alignment: .leading, spacing: 0) {
            // Line 1: hora · fuente · promoBadge · título · % · status icon
            HStack(spacing: 6) {
                Text(r.horaFormatted)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(SRColor.textLabel)
                    .frame(width: 40, alignment: .leading)

                fuenteBadge(r.fuente)

                // Badge promovida (estrella dorada) solo para canciones promovidas
                if r.isPromovida {
                    Image(systemName: "star.fill")
                        .font(.system(size: 9))
                        .foregroundColor(qualifying ? SRColor.srGreen : SRColor.brand)
                }

                Text(r.titulo.isEmpty ? r.contenido : r.titulo)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(SRColor.textPrimary)
                    .lineLimit(1)
                    .frame(maxWidth: .infinity, alignment: .leading)

                Text(r.porcentajeFormatted)
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(qualifying ? SRColor.srGreen : partial ? SRColor.venueOrange : SRColor.textSecond)
                    .frame(width: 44, alignment: .trailing)

                statusIcon(r).frame(width: 22, alignment: .center)
            }
            .padding(.horizontal, 14).padding(.top, 8)

            // Line 2: artista · ISRC · estado pago · duración · tiempo
            HStack(spacing: 8) {
                if !r.artista.isEmpty {
                    Text(r.artista)
                        .font(.system(size: 10))
                        .foregroundColor(SRColor.textSecond)
                        .lineLimit(1)
                }
                if !r.isrc.isEmpty {
                    Text("·").foregroundColor(SRColor.textLabel).font(.system(size: 10))
                    Text(r.isrc)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundColor(SRColor.textSecond)
                }
                // Etiqueta de estado de pago
                if qualifying {
                    Text("· pagada")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(SRColor.srGreen)
                } else if enProgreso {
                    Text("· promovida")
                        .font(.system(size: 10))
                        .foregroundColor(SRColor.brand.opacity(0.8))
                } else {
                    Text("· no promovida")
                        .font(.system(size: 10))
                        .foregroundColor(SRColor.textLabel)
                }
                Spacer()
                if !r.duracion.isEmpty {
                    HStack(spacing: 2) {
                        Image(systemName: "timer").font(.system(size: 9))
                        Text(r.duracion)
                    }
                    .font(.system(size: 10))
                    .foregroundColor(SRColor.textLabel)
                }
                HStack(spacing: 2) {
                    Image(systemName: "ear").font(.system(size: 9))
                    Text(formatSeconds(r.segundosEscuchados))
                }
                .font(.system(size: 10))
                .foregroundColor(SRColor.textLabel)
            }
            .padding(.horizontal, 14).padding(.bottom, 8)
        }
        .background(rowBg)
    }

    @ViewBuilder
    private func fuenteBadge(_ f: String) -> some View {
        let (label, color): (String, Color) = {
            let lower = f.lowercased()
            if lower.contains("spotify")  { return ("Spotify",  Color(red: 0.11, green: 0.73, blue: 0.33)) }
            if lower.contains("youtube")  { return ("YouTube",  .red) }
            if lower.contains("local")    { return ("Local",    Color(red: 0.45, green: 0.30, blue: 0.75)) }
            return ("Sistema", SRColor.brand)
        }()
        Text(label)
            .font(.system(size: 9, weight: .semibold))
            .foregroundColor(color)
            .padding(.horizontal, 5).padding(.vertical, 2)
            .background(color.opacity(0.12))
            .cornerRadius(4)
            .frame(width: 52, alignment: .leading)
    }

    @ViewBuilder
    private func statusIcon(_ r: PlayRecord) -> some View {
        if r.ganodinero {
            // Promovida + ≥80% → pagada
            Image(systemName: r.enviado ? "checkmark.circle.fill" : "clock.arrow.circlepath")
                .font(.system(size: 13))
                .foregroundColor(r.enviado ? SRColor.srGreen : SRColor.venueOrange)
        } else if r.inCatalog {
            // Promovida pero aún no alcanza el umbral → en progreso
            Image(systemName: "star.leadinghalf.filled")
                .font(.system(size: 12))
                .foregroundColor(SRColor.brand.opacity(0.8))
        } else {
            // No está en el catálogo de promovidas
            Image(systemName: "music.note.slash")
                .font(.system(size: 12)).foregroundColor(SRColor.textLabel)
        }
    }

    private func formatSeconds(_ s: Double) -> String {
        let min = Int(s) / 60; let sec = Int(s) % 60
        return min > 0 ? "\(min)m \(sec)s" : "\(sec)s"
    }
}
