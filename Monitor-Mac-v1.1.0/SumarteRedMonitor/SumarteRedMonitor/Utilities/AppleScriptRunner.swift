import Foundation
import AppKit

enum AppleScriptPermissionResult {
    case success
    case denied   // -1743 (errAEEventNotPermitted) o -10003 (unauthorized)
    case unknown
}

enum AppleScriptRunner {

    /// Ejecuta un script AppleScript y retorna el resultado como String.
    /// Retorna nil si hay error o si la app no está corriendo.
    @discardableResult
    static func run(_ script: String) -> String? {
        var error: NSDictionary?
        let appleScript = NSAppleScript(source: script)
        let result = appleScript?.executeAndReturnError(&error)
        if error != nil { return nil }
        return result?.stringValue
    }

    /// Ejecuta un script y retorna si fue exitoso o denegado por permisos.
    static func runCheckingError(_ script: String) -> AppleScriptPermissionResult {
        var error: NSDictionary?
        let appleScript = NSAppleScript(source: script)
        _ = appleScript?.executeAndReturnError(&error)
        guard let err = error else { return .success }
        let code = err[NSAppleScript.errorNumber] as? Int ?? 0
        // -1743 = errAEEventNotPermitted, -10003 = Acceso no autorizado
        if code == -1743 || code == -10003 {
            return .denied
        }
        // Otro error (app no responde, etc.) — no es de permisos
        return .unknown
    }

    /// Verifica si una aplicación está en ejecución por nombre de proceso.
    static func isRunning(_ appName: String) -> Bool {
        return NSWorkspace.shared.runningApplications
            .contains { $0.localizedName == appName }
    }
}
