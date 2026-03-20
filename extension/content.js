// Bridge between page.js (MAIN world) and service_worker.js (extension context)

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

// service_worker responds with transcription result
chrome.runtime.onMessage.addListener((request) => {
	const { id, record } = request;
	window.dispatchEvent(
		new CustomEvent(`AudioToText:${id}`, {
			detail: record,
		})
	);
});
