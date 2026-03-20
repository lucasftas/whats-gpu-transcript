import Foundation
import Speech
import AVFoundation

// WhatsGPU macOS - Transcription helper using SFSpeechRecognizer
// Usage: ./transcribe <audio_file_path> [locale]
// Output: JSON to stdout {"text": "...", "duration": 5.2, "error": null}

func transcribe(filePath: String, locale: String = "pt-BR") {
    let url = URL(fileURLWithPath: filePath)

    guard FileManager.default.fileExists(atPath: filePath) else {
        let result: [String: Any] = ["text": "", "duration": 0, "error": "Arquivo não encontrado: \(filePath)"]
        printJSON(result)
        exit(1)
    }

    // Get audio duration
    var duration: Double = 0
    do {
        let audioFile = try AVAudioFile(forReading: url)
        duration = Double(audioFile.length) / audioFile.fileFormat.sampleRate
    } catch {
        // Duration detection failed, continue anyway
    }

    let speechLocale = Locale(identifier: locale)

    guard let recognizer = SFSpeechRecognizer(locale: speechLocale) else {
        let result: [String: Any] = ["text": "", "duration": duration, "error": "SFSpeechRecognizer não disponível para locale: \(locale)"]
        printJSON(result)
        exit(1)
    }

    guard recognizer.isAvailable else {
        let result: [String: Any] = ["text": "", "duration": duration, "error": "Reconhecimento de fala não disponível. Verifique as configurações do sistema."]
        printJSON(result)
        exit(1)
    }

    // Request authorization
    let semaphore = DispatchSemaphore(value: 0)
    var authorized = false

    SFSpeechRecognizer.requestAuthorization { status in
        authorized = (status == .authorized)
        semaphore.signal()
    }
    semaphore.wait()

    guard authorized else {
        let result: [String: Any] = ["text": "", "duration": duration, "error": "Permissão de reconhecimento de fala negada. Vá em Configurações > Privacidade > Reconhecimento de Fala."]
        printJSON(result)
        exit(1)
    }

    // Create recognition request
    let request = SFSpeechURLRecognitionRequest(url: url)
    request.shouldReportPartialResults = false

    // Prefer on-device recognition (macOS 13+)
    if #available(macOS 13, *) {
        request.requiresOnDeviceRecognition = true
    }

    // Perform recognition
    let resultSemaphore = DispatchSemaphore(value: 0)
    var transcribedText = ""
    var errorMessage: String? = nil

    recognizer.recognitionTask(with: request) { result, error in
        if let error = error {
            errorMessage = error.localizedDescription
            resultSemaphore.signal()
            return
        }

        if let result = result, result.isFinal {
            transcribedText = result.bestTranscription.formattedString
            resultSemaphore.signal()
        }
    }

    // Wait for result (timeout: 5 minutes)
    let timeout = DispatchTime.now() + .seconds(300)
    if resultSemaphore.wait(timeout: timeout) == .timedOut {
        errorMessage = "Timeout: transcrição demorou mais de 5 minutos"
    }

    let output: [String: Any] = [
        "text": transcribedText,
        "duration": duration,
        "error": errorMessage as Any
    ]
    printJSON(output)

    if errorMessage != nil {
        exit(1)
    }
}

func printJSON(_ dict: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: dict, options: []),
       let jsonString = String(data: data, encoding: .utf8) {
        print(jsonString)
    }
}

// Main
let args = CommandLine.arguments
guard args.count >= 2 else {
    let result: [String: Any] = ["text": "", "duration": 0, "error": "Uso: ./transcribe <arquivo_audio> [locale]"]
    printJSON(result)
    exit(1)
}

let filePath = args[1]
let locale = args.count >= 3 ? args[2] : "pt-BR"
transcribe(filePath: filePath, locale: locale)
