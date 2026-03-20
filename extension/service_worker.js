const API_URL = "http://localhost:8765";
const TRANSCRIBE_TIMEOUT = 300000; // 5 minutes
const MAX_RETRIES = 1;

const PRECISION_PRESETS = [
	{ beam_size: 1, best_of: 1, temperature: [0.0], patience: 1.0 },
	{ beam_size: 5, best_of: 5, temperature: [0.0], patience: 1.0 },
	{ beam_size: 10, best_of: 10, temperature: [0.0, 0.2, 0.4, 0.6, 0.8, 1.0], patience: 2.0 },
];

chrome.runtime.onMessage.addListener(async (request, sender) => {
	const { id, audioBase64 } = request;
	if (!id || !audioBase64) return;

	// Health check first
	try {
		const ctrl = new AbortController();
		const timeout = setTimeout(() => ctrl.abort(), 2000);
		const healthResp = await fetch(`${API_URL}/health`, { signal: ctrl.signal });
		clearTimeout(timeout);
		if (!healthResp.ok) throw new Error("unhealthy");
	} catch (e) {
		const record = {
			transcription: "Whats GPU não está rodando. Inicie o app para transcrever.",
			error: true,
			errorType: "network",
		};
		chrome.tabs.sendMessage(sender.tab.id, { id, record });
		return;
	}

	// Decode base64 to blob
	const binaryStr = atob(audioBase64);
	const bytes = new Uint8Array(binaryStr.length);
	for (let i = 0; i < binaryStr.length; i++) {
		bytes[i] = binaryStr.charCodeAt(i);
	}
	const blob = new Blob([bytes], { type: "audio/ogg" });

	// Read precision setting
	let precisionParams = PRECISION_PRESETS[1]; // default: Balanceado
	try {
		const stored = await chrome.storage.local.get("precisionLevel");
		const level = stored.precisionLevel != null ? stored.precisionLevel : 1;
		precisionParams = PRECISION_PRESETS[level] || PRECISION_PRESETS[1];
	} catch (e) {
		// use default
	}

	// Transcribe with retry
	let lastError = null;
	for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
		try {
			const ctrl = new AbortController();
			const timeout = setTimeout(() => ctrl.abort(), TRANSCRIBE_TIMEOUT);

			const formData = new FormData();
			formData.append("file", blob, "audio.ogg");
			formData.append("precision", JSON.stringify(precisionParams));

			const resp = await fetch(`${API_URL}/transcribe`, {
				method: "POST",
				body: formData,
				signal: ctrl.signal,
			});
			clearTimeout(timeout);

			const data = await resp.json();

			// OOM with retry hint - retry if we have attempts left
			if (resp.status === 503 && data.retry && attempt < MAX_RETRIES) {
				lastError = data.error || "GPU sem memória";
				await new Promise((r) => setTimeout(r, 2000));
				continue;
			}

			const transcription = data.text || data.error || "Erro desconhecido";
			const error = !data.text;
			let errorType = null;
			if (error && resp.status === 503) errorType = "oom";
			else if (error) errorType = "server";

			const record = { transcription, error, errorType };
			chrome.tabs.sendMessage(sender.tab.id, { id, record });

			if (!error) {
				chrome.storage.local.set({ [id]: record });
			}
			return;
		} catch (e) {
			lastError = e;
			if (e.name === "AbortError") {
				const record = {
					transcription: "Timeout: áudio muito longo ou servidor travado.",
					error: true,
					errorType: "timeout",
				};
				chrome.tabs.sendMessage(sender.tab.id, { id, record });
				return;
			}
			// Network error - retry if possible
			if (attempt < MAX_RETRIES) {
				await new Promise((r) => setTimeout(r, 2000));
				continue;
			}
		}
	}

	// All retries exhausted
	const record = {
		transcription: `Erro ao transcrever: ${lastError?.message || lastError || "erro desconhecido"}`,
		error: true,
		errorType: "network",
	};
	chrome.tabs.sendMessage(sender.tab.id, { id, record });
});
