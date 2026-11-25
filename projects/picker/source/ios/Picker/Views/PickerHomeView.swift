import PhotosUI
import SwiftUI

@MainActor
struct PickerHomeView: View {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var session = PickerSession()
    @State private var selection: PhotosPickerItem?
    @State private var work: Task<Void, Never>?
    @State private var importing = false
    @State private var errorMessage: String?
    private let ocr = LocalOCRService()

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Form filling without the data trail.").font(.title2)
                    Text("Picker helps you use information from a photo or screenshot to complete forms.")
                    Text("Picker only uses your information for the current task. Picker does not save your source documents or extracted personal information.")
                    Text("This prototype keeps OCR in the app. Returning values to the keyboard is not implemented.")
                        .font(.footnote)
                }
                Section("Keyboard: Needs Setup / Verification") {
                    Text("Picker cannot verify whether its keyboard is enabled. If you have already enabled it, test it in a text field.")
                    Text("Open Settings → General → Keyboard → Keyboards → Add New Keyboard → Picker. Leave Allow Full Access off. In a regular text field, use the globe key to choose Picker.")
                }
                Section("Local OCR") {
                    PhotosPicker(selection: $selection, matching: .images, preferredItemEncoding: .current) {
                        Label("Select Image", systemImage: "photo")
                    }
                    .disabled(importing || session.state == .processing || session.cleanupFailed)
                    Text("Use an image already downloaded to this device. Cloud-only photos may be downloaded by the system Photos picker; Picker itself makes no network requests.")
                        .font(.footnote)
                    if importing || session.state == .processing {
                        ProgressView(importing ? "Loading image…" : "Recognizing locally…")
                    }
                    if let errorMessage { Text(errorMessage).foregroundStyle(.red) }
                    if session.cleanupFailed {
                        Text("Temporary cleanup failed. Close Picker and retry before using sensitive images.")
                            .foregroundStyle(.red)
                    }
                    if session.state == .completed || session.state == .cancelled {
                        Text("Session ended. Picker released its source and OCR references.")
                    }
                }
                if session.state == .reviewing {
                    Section("Temporary Review") {
                        if session.observations.isEmpty { Text("No text found. Try a clearer image.") }
                        ForEach(session.observations) { item in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(item.text)
                                Text("Confidence: \(item.confidence, format: .percent.precision(.fractionLength(0)))")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Button("Complete and Delete Session") { endSession(completed: true) }
                    }
                }
                if importing || [.sourceSelected, .processing, .reviewing].contains(session.state) {
                    Button("Cancel and Delete Session", role: .destructive) { endSession() }
                }
            }
            .navigationTitle("Picker")
            .privacySensitive()
            .overlay {
                if scenePhase != .active {
                    Color(.systemBackground).ignoresSafeArea().overlay(Text("Picker • Private Session"))
                }
            }
        }
        .onChange(of: selection) { _, item in
            guard let item else { return }
            importImage(item)
        }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { endSession() }
        }
        .onDisappear { endSession() }
    }

    private func importImage(_ item: PhotosPickerItem) {
        work?.cancel()
        let token = session.begin()
        importing = true
        errorMessage = nil
        work = Task { @MainActor in
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else {
                    throw LocalOCRError.unsupportedImage
                }
                try Task.checkCancellation()
                guard session.id == token else { return }
                session.selectSource(data, for: token)
                session.startProcessing(for: token)
                importing = false
                selection = nil
                let items = try await ocr.recognize(data)
                try Task.checkCancellation()
                session.review(items, for: token)
            } catch {
                guard session.id == token else { return }
                session.cancel()
                importing = false
                selection = nil
                if !(error is CancellationError) {
                    errorMessage = "The image could not be processed. Try a smaller, clear image stored on this device."
                }
            }
            work = nil
        }
    }

    private func endSession(completed: Bool = false) {
        work?.cancel()
        work = nil
        selection = nil
        importing = false
        errorMessage = nil
        if completed { session.complete() } else { session.cancel() }
    }
}
