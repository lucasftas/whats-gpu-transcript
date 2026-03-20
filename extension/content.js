// Bridge between page.js (MAIN world) and service_worker.js (extension context)

const API_URL = "http://localhost:8765";

// page.js asks for cached transcription
window.addEventListener("AudioToText:cache", async (event) => {
	const id = event.detail;
	const record = await chrome.storage.local.get(id);
	window.dispatchEvent(
		new CustomEvent(`AudioToText:${id}`, {
			detail: record[id] || null,
		})
	);
});

// page.js sends audio data for transcription
window.addEventListener("AudioToText:transcript", (event) => {
	const { id, audioBase64 } = event.detail;
	chrome.runtime.sendMessage({ id, audioBase64 });
});

// page.js requests status polling (content script can bypass page CSP)
window.addEventListener("AudioToText:statusRequest", async () => {
	try {
		const ctrl = new AbortController();
		const timeout = setTimeout(() => ctrl.abort(), 2000);
		const resp = await fetch(`${API_URL}/status`, { signal: ctrl.signal });
		clearTimeout(timeout);
		if (!resp.ok) return;
		const data = await resp.json();
		window.dispatchEvent(
			new CustomEvent("AudioToText:statusResponse", { detail: data })
		);
	} catch (e) {
		// Ignore polling errors
	}
});

// service_worker responds with transcription result
chrome.runtime.onMessage.addListener((request) => {
	const { id, record } = request;
	window.dispatchEvent(
		new CustomEvent(`AudioToText:${id}`, {
			detail: record,
		})
	);
});
