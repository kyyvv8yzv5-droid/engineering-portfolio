import Combine
import Foundation

enum PickerSessionState: String {
    case idle, sourceSelected, processing, reviewing, completed, cancelled
}

@MainActor
final class PickerSession: ObservableObject {
    @Published private(set) var id = UUID()
    @Published private(set) var state: PickerSessionState = .idle
    @Published private(set) var sourceImageData: Data?
    @Published private(set) var observations: [RecognizedTextItem] = []
    @Published private(set) var cleanupFailed = false
    private let temporaryFiles: SessionTemporaryFiles

    init(temporaryFiles: SessionTemporaryFiles = SessionTemporaryFiles()) {
        self.temporaryFiles = temporaryFiles
        do { try temporaryFiles.removeAbandonedFiles() }
        catch { cleanupFailed = true }
    }

    /// Invalidates outstanding imports, including those not yet providing image data.
    @discardableResult
    func begin() -> UUID {
        purge()
        id = UUID()
        state = .idle
        return id
    }

    func selectSource(_ data: Data, for token: UUID) {
        guard token == id, state == .idle else { return }
        sourceImageData = data
        state = .sourceSelected
    }

    func startProcessing(for token: UUID) {
        guard token == id, state == .sourceSelected else { return }
        state = .processing
    }

    func review(_ items: [RecognizedTextItem], for token: UUID) {
        guard token == id, state == .processing else { return }
        sourceImageData = nil
        observations = items
        state = .reviewing
    }

    func complete() {
        guard state == .reviewing else { return }
        purge()
        state = .completed
    }

    func cancel() {
        purge()
        state = .cancelled
    }

    /// Releases our references; does not promise physical memory zeroization.
    func purge() {
        id = UUID() // Late asynchronous results can no longer populate this session.
        sourceImageData = nil
        observations.removeAll(keepingCapacity: false)
        state = .idle
        do {
            try temporaryFiles.removeAbandonedFiles()
            cleanupFailed = false
        } catch {
            cleanupFailed = true
        }
    }
}
