import Foundation
import ImageIO
import Vision

enum LocalOCRError: Error {
    case unsupportedImage
}

/// Actor isolation keeps image decoding and Vision work off the main actor.
actor LocalOCRService {
    func recognize(_ data: Data) async throws -> [RecognizedTextItem] {
        try Task.checkCancellation()
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            throw LocalOCRError.unsupportedImage
        }
        let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
        let rawOrientation = (properties?[kCGImagePropertyOrientation] as? NSNumber)?.uint32Value ?? 1
        let orientation = CGImagePropertyOrientation(rawValue: rawOrientation) ?? .up
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        return try await withTaskCancellationHandler {
            try Task.checkCancellation()
            try VNImageRequestHandler(cgImage: image, orientation: orientation).perform([request])
            try Task.checkCancellation()
            return (request.results ?? []).compactMap { observation in
                guard let candidate = observation.topCandidates(1).first else { return nil }
                let box = observation.boundingBox
                return RecognizedTextItem(
                    text: candidate.string,
                    confidence: candidate.confidence,
                    boundingBox: TextBoundingBox(x: Double(box.minX), y: Double(box.minY),
                                                width: Double(box.width), height: Double(box.height))
                )
            }
        } onCancel: {
            request.cancel()
        }
    }
}
