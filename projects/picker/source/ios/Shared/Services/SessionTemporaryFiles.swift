import Foundation

/// Reserved namespace only. Phase 1's Data-based import never writes image files.
struct SessionTemporaryFiles {
    let root: URL

    init(temporaryDirectory: URL = FileManager.default.temporaryDirectory) {
        root = temporaryDirectory.appendingPathComponent("PickerEphemeralSessions", isDirectory: true)
    }

    func removeAbandonedFiles() throws {
        let manager = FileManager.default
        guard manager.fileExists(atPath: root.path) else { return }
        // Only remove Picker's dedicated directory, never the system temp root.
        try manager.removeItem(at: root)
    }
}
