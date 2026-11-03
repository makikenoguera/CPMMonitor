import SwiftUI

struct MonitoreoView: View {
    let history: [PlayRecord]
    @State private var filtro: Filtro = .todas

    enum Filtro: CaseIterable {
        case todas, pagadas, noPagadas
    }

    private var pagadas:   [PlayRecord] { history.filter {  $0.ganodinero } }
    private var noPagadas: [PlayRecord] { history.filter { !$0.ganodinero } }
    private var mostrar:   [PlayRecord] {
        switch filtro {
        case .todas:     return history
        case .pagadas:   return pagadas
        case .noPagadas: return noPagadas
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            filtroBar
            Divider().overlay(SRColor.border)
            if mostrar.isEmpty {
                emptyState
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(mostrar) { r in
                            fila(r)
                            Divider().overlay(SRColor.border).padding(.leading, 14)
                        }
                    }
                }
                .background(SRColor.pageBg)
            }
        }
    }

    // MARK: - Filter bar
    private var filtroBar: some View {
        HStack(spacing: 0) {
            filtroBtn(.todas,     label: "Todas (\(history.count))")
            sepV
            filtroBtn(.pagadas,   label: "\(pagadas.count) Pagadas")
            sepV
            filtroBtn(.noPagadas, label: "\(noPagadas.count) No pagadas")
        }
        .background(SRColor.pageBg)
    }

    private var sepV: some View {
        Rectangle().fill(SRColor.border).frame(width: 1, height: 16)
    }

    private func filtroBtn(_ f: Filtro, label: String) -> some View {
        let active = filtro == f
        return Button { filtro = f } label: {
            VStack(spacing: 0) {
                Text(label)
                    .font(.system(size: 11, weight: active ? .semibold : .regular))
                    .foregroundColor(active ? SRColor.textPrimary : SRColor.textSecond)
                    .padding(.vertical, 9)
                    .frame(maxWidth: .infinity)
                Rectangle()
                    .fill(active ? SRColor.brand : Color.clear)
                    .frame(height: 2)
            }
        }
        .buttonStyle(.plain)
    }

    // MARK: - Row (2 líneas)
    private func fila(_ r: PlayRecord) -> some View {
        let paying    = r.ganodinero
        let accentClr: Color = paying
            ? SRColor.srGreen
            : Color(red: 0.72, green: 0.42, blue: 0.42)
        let rowBg: Color = paying
            ? SRColor.srGreen.opacity(0.07)
            : Color(red: 0.98, green: 0.94, blue: 0.94)

        let pctStr = (r.porcentaje >= 80 ? "+" : "") + String(format: "%.0f%%", r.porcentaje)

        return HStack(alignment: .center, spacing: 10) {

            // Fecha + hora
            VStack(alignment: .center, spacing: 1) {
                Text(r.fechaCorta)
                    .font(.system(size: 9))
                    .foregroundColor(SRColor.textLabel)
                Text(r.horaFormatted)
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundColor(paying ? SRColor.textSecond : SRColor.textLabel)
            }
            .frame(width: 38, alignment: .center)

            // Acento vertical
            RoundedRectangle(cornerRadius: 1)
                .fill(accentClr.opacity(paying ? 0.85 : 0.38))
                .frame(width: 2, height: 38)

            // Info canción — 2 líneas
            VStack(alignment: .leading, spacing: 4) {
                // Línea 1: título · porcentaje
                HStack(spacing: 6) {
                    Text(r.titulo.isEmpty ? r.contenido : r.titulo)
                        .font(.system(size: 12, weight: paying ? .semibold : .medium))
                        .foregroundColor(paying ? SRColor.textPrimary : SRColor.textSecond)
                        .lineLimit(1)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Text(pctStr)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(paying ? SRColor.srGreen : SRColor.textLabel)
                }
                // Línea 2: artista · ISRC | ⏱ duración / ≋ escuchado
                HStack(spacing: 4) {
                    if !r.artista.isEmpty {
                        Text(r.artista)
                            .font(.system(size: 10))
                            .foregroundColor(SRColor.textLabel)
                            .lineLimit(1)
                    }
                    if !r.isrc.isEmpty {
                        Text("·").font(.system(size: 10)).foregroundColor(SRColor.textLabel)
                        Text(r.isrc)
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundColor(SRColor.textLabel.opacity(0.65))
                            .lineLimit(1)
                    }
                    Spacer()
                    Image(systemName: "clock")
                        .font(.system(size: 8))
                        .foregroundColor(SRColor.textLabel)
                    Text(r.duracionFormatted)
                        .font(.system(size: 10))
                        .foregroundColor(SRColor.textLabel)
                    Text("/")
                        .font(.system(size: 10))
                        .foregroundColor(SRColor.textLabel.opacity(0.5))
                    Image(systemName: "waveform")
                        .font(.system(size: 8))
                        .foregroundColor(SRColor.textLabel)
                    Text(fmtSeg(r.segundosEscuchados))
                        .font(.system(size: 10))
                        .foregroundColor(SRColor.textLabel.opacity(paying ? 1 : 0.6))
                }
            }

            // Círculo indicador (sutil)
            ZStack {
                Circle()
                    .fill(paying
                          ? SRColor.srGreen.opacity(0.85)
                          : Color(red: 0.72, green: 0.52, blue: 0.52).opacity(0.28))
                    .frame(width: 18, height: 18)
                Image(systemName: paying ? "checkmark" : "xmark")
                    .font(.system(size: paying ? 7 : 6,
                                  weight: paying ? .bold : .thin))
                    .foregroundColor(paying
                                     ? .white
                                     : Color(red: 0.50, green: 0.30, blue: 0.30).opacity(0.6))
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
        .background(rowBg)
    }

    // MARK: - Empty
    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "waveform.and.magnifyingglass")
                .font(.system(size: 32))
                .foregroundColor(SRColor.textLabel)
            Text("Sin reproducciones")
                .font(.subheadline)
                .foregroundColor(SRColor.textSecond)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.top, 40)
    }

    private func fmtSeg(_ s: Double) -> String {
        String(format: "%d:%02d", Int(s) / 60, Int(s) % 60)
    }
}
