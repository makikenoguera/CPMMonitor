import SwiftUI

/// Paleta oficial SumarteRed — extraída del dashboard monitor.sumartered.com/dashboard
enum SRColor {
    // MARK: - Brand  #E2530A (naranja corporativo, logo dashboard)
    static let brand        = Color(red: 0.886, green: 0.325, blue: 0.039)
    static let brandDark    = Color(red: 0.722, green: 0.259, blue: 0.027)  // hover / pressed
    static let brandBg      = Color(red: 0.886, green: 0.325, blue: 0.039).opacity(0.10)

    // MARK: - Income colors (dashboard)
    static let srGreen      = Color(red: 0.098, green: 0.643, blue: 0.298)  // #19A44C ingresos S.RED
    static let venueOrange  = Color(red: 0.859, green: 0.518, blue: 0.125)  // #DB8420 ingreso estab.

    // MARK: - Backgrounds (tema claro igual que el dashboard)
    static let pageBg       = Color(red: 0.961, green: 0.965, blue: 0.973)  // #F5F7F9
    static let cardBg       = Color.white
    static let headerBg     = Color.white

    // MARK: - Text
    static let textPrimary  = Color(red: 0.102, green: 0.102, blue: 0.102)  // #1A1A1A
    static let textSecond   = Color(red: 0.533, green: 0.533, blue: 0.533)  // #888
    static let textLabel    = Color(red: 0.600, green: 0.600, blue: 0.600)  // #999 uppercase labels

    // MARK: - Borders
    static let border       = Color(red: 0.910, green: 0.914, blue: 0.922)  // #E8E9EB
    static let divider      = Color(red: 0.925, green: 0.929, blue: 0.933)  // #ECEDEF

    // MARK: - Legacy aliases — para no romper código existente
    static let celeste      = brand
    static let celesteDark  = brandDark
    static let background   = pageBg
    static let headerBgLegacy = headerBg
}
