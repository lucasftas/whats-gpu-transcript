const API = "http://localhost:8765";

const dot = document.getElementById("dot");
const statusText = document.getElementById("status-text");
const statusModel = document.getElementById("status-model");
const engineInfo = document.getElementById("engine-info");
const engineName = document.getElementById("engine-name");
const chipName = document.getElementById("chip-name");
const progressContainer = document.getElementById("progress-container");
const progressLabel = document.getElementById("progress-label");
const progressFill = document.getElementById("progress-fill");
const progressDetail = document.getElementById("progress-detail");
const logArea = document.getElementById("log-area");

function addLog(msg, level = "info") {
	const time = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
	const entry = document.createElement("div");
	entry.className = `log-entry ${level}`;
	entry.textContent = `[${time}] ${msg}`;
	logArea.prepend(entry);
	logArea.classList.add("visible");
	// Keep max 20 entries
	while (logArea.children.length > 20) {
		logArea.removeChild(logArea.lastChild);
	}
}

async function checkHealth() {
	try {
		const res = await fetch(`${API}/health`, { signal: AbortSignal.timeout(3000) });
		const data = await res.json();

		dot.className = "status-dot online";
		statusText.textContent = "WhatsGPU rodando";
		statusModel.textContent = `Engine: ${data.engine || "SFSpeechRecognizer"}`;

		// Show engine info
		engineInfo.style.display = "block";
		engineName.textContent = data.engine || "SFSpeechRecognizer";
		chipName.textContent = data.chip || "Apple Silicon";

		return true;
	} catch {
		dot.className = "status-dot offline";
		statusText.textContent = "WhatsGPU não detectado";
		statusModel.textContent = "Execute o app WhatsGPU primeiro";
		engineInfo.style.display = "none";
		return false;
	}
}

async function pollStatus() {
	try {
		const res = await fetch(`${API}/status`, { signal: AbortSignal.timeout(3000) });
		const data = await res.json();

		const stage = data.stage;
		const detail = data.detail || {};

		if (stage === "transcribing") {
			dot.className = "status-dot loading";
			statusText.textContent = "Transcrevendo...";

			if (typeof detail === "object" && detail.progress_pct !== undefined) {
				progressContainer.classList.add("visible");
				progressLabel.textContent = "Transcrevendo áudio...";
				progressFill.style.width = `${detail.progress_pct}%`;
				const processed = detail.processed_s || 0;
				const total = detail.total_s || 0;
				progressDetail.textContent = total > 0
					? `${processed}s / ${total}s (${detail.progress_pct}%)`
					: `${detail.progress_pct}%`;
			}
		} else if (stage === "done") {
			dot.className = "status-dot online";
			statusText.textContent = "Transcrição concluída";
			progressContainer.classList.remove("visible");
			addLog("Transcrição concluída", "success");
		} else {
			dot.className = "status-dot online";
			statusText.textContent = "Pronto para transcrever";
			progressContainer.classList.remove("visible");
		}
	} catch {
		// Server not responding — will be caught by health check
	}
}

// Initial check
checkHealth().then((ok) => {
	if (ok) addLog("Servidor conectado", "success");
	else addLog("Servidor não detectado", "error");
});

// Poll every 2 seconds
setInterval(async () => {
	const ok = await checkHealth();
	if (ok) await pollStatus();
}, 2000);
