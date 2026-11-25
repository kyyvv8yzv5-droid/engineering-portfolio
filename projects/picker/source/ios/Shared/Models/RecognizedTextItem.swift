import Foundation

/// Vision coordinates are normalized, with the origin at the bottom left.
struct TextBoundingBox: Equatable, Sendable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

/// Intentionally not Codable: OCR results are never serialized by this prototype.
struct RecognizedTextItem: Identifiable, Equatable, Sendable {
    let id: UUID
    let text: String
    let confidence: Float
    let boundingBox: TextBoundingBox?

    init(id: UUID = UUID(), text: String, confidence: Float, boundingBox: TextBoundingBox? = nil) {
        self.id = id
        self.text = text
        self.confidence = confidence
        self.boundingBox = boundingBox
    }
}
