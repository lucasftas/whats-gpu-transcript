const API_URL = "http://localhost:8765";

const dot = document.getElementById("dot");
const statusText = document.getElementById("status-text");
const statusModel = document.getElementById("status-model");
const btnLoad = document.getElementById("btn-load");
const btnUnload = document.getElementById("btn-unload");
const btnRefresh = document.getElementById("btn-refresh");
const logArea = document.getElementById("log-area");
const modelsList = document.getElementById("models-list");
const progressContainer = document.getElementById("progress-container");
const progressLabel = document.getElementById("progress-label");
const progressFill = document.getElementById("progress-fill");
const progressDetail = document.getElementById("progress-detail");

const btnClearCache = document.getElementById("btn-clear-cache");

const precisionSlider = document.getElementById("precision-slider");
const precisionValue = document.getElementById("precision-value");
const precisionDesc = document.getElementById("precision-desc");
const precisionWarn = document.getElementById("precision-warn");

let pollTimer = null;
let healthTimer = null;
let lastStage = null;
let lastLogStage = null;
let selectedModel = null;
let currentModels = [];
let cachedModelsData = null;

// ---------------------------------------------------------------------------
// Precision presets
// ---------------------------------------------------------------------------
const PRECISION_PRESETS = [
	{
		name: "Rápido",
		beam_size: 1,
		best_of: 1,
		temperature: [0.0],
		patience: 1.0,
		desc: "beam=1 · best_of=1 — Velocidade máxima, precisão básica",
	},
	{
		name: "Balanceado",
		beam_size: 5,
		best_of: 5,
		temperature: [0.0],
		patience: 1.0,
		desc: "beam=5 · best_of=5 — Bom equilíbrio entre velocidade e precisão",
	},
	{
		name: "Máxima",
		beam_size: 10,
		best_of: 10,
		temperature: [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
		patience: 2.0,
		desc: "beam=10 · best_of=10 · fallback temp — Precisão máxima, mais lento",
	},
];

// Small models that should warn when using max precision
const SMALL_MODELS = ["tiny", "base", "small"];

// ---------------------------------------------------------------------------
// Log
// ---------------------------------------------------------------------------
function addLog(text, css = "info") {
	const ts = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
	const entry = document.createElement("div");
	entry.className = `log-entry ${css}`;
	entry.textContent = `[${ts}] ${text}`;
	logArea.appendChild(entry);
	logArea.scrollTop = logArea.scrollHeight;
	logArea.classList.add("visible");
}

// ---------------------------------------------------------------------------
// Progress bar
// ---------------------------------------------------------------------------
function updateProgressBar(stage, detail) {
	const active = ["loading_model", "transcribing", "downloading_model"].includes(stage);
	progressContainer.classList.toggle("visible", active);

	if (!active) {
		progressFill.style.width = "0%";
		return;
	}

	const pct = (detail && detail.progress_pct) || 0;
	progressFill.style.width = pct + "%";

	if (stage === "downloading_model") {
		const model = (detail && detail.model) || "modelo";
		progressLabel.textContent = `Baixando ${model}... ${pct}%`;
		const mbText = detail && detail.downloaded_mb != null
			? `${detail.downloaded_mb} MB de ${detail.total_mb} MB`
			: "";
		const statusText = detail && detail.status ? ` | ${detail.status}` : "";
		progressDetail.textContent = mbText + statusText;
	} else if (stage === "loading_model") {
		progressLabel.textContent = `Carregando modelo...`;
		progressDetail.textContent = typeof detail === "string" ? detail : (detail && detail.message) || "";
	} else if (stage === "transcribing") {
		progressLabel.textContent = `Transcrevendo... ${pct}%`;
		progressDetail.textContent = detail && detail.processed_s != null
			? `${detail.processed_s}s de ${detail.total_s}s`
			: "";
	}
}

// ---------------------------------------------------------------------------
// Models list
// ---------------------------------------------------------------------------
async function fetchModels() {
	try {
		const resp = await fetch(`${API_URL}/models`);
		if (!resp.ok) return;
		const data = await resp.json();
		currentModels = data.models;
		cachedModelsData = data;
		renderModels(data);
	} catch (e) {
		modelsList.innerHTML = `<div class="model-item" style="color:#ef4146;">Erro ao carregar modelos</div>`;
	}
}

function renderModels(data) {
	modelsList.innerHTML = "";
	const isDownloading = data.is_downloading;
	const downloadingName = data.downloading_model;

	for (const m of data.models) {
		const item = document.createElement("div");
		item.className = "model-item" + (m.name === selectedModel ? " selected" : "");
		if (m.downloaded) item.style.cursor = "pointer";

		const statusIcon = m.downloaded ? "\u2705" : (isDownloading && m.name === downloadingName ? "\u23F3" : "\u2B07\uFE0F");
		const badge = m.recommended ? `<span class="badge badge-rec">Recomendado</span>` : "";
		const sizeText = m.size_mb >= 1000 ? `${(m.size_mb / 1000).toFixed(1)} GB` : `${m.size_mb} MB`;

		let actionBtns = "";
		if (m.downloaded) {
			actionBtns = `<button class="model-btn model-btn-delete" data-action="delete" data-model="${m.name}" title="Remover">\u2716</button>`;
		} else if (isDownloading && m.name === downloadingName) {
			actionBtns = `<button class="model-btn model-btn-cancel" data-action="cancel" title="Cancelar download">\u2716</button>`;
		} else {
			actionBtns = `
				<a class="model-btn model-btn-link" href="${m.url}" target="_blank" title="Baixar via navegador">\u2197</a>
				<button class="model-btn model-btn-download" data-action="download" data-model="${m.name}" ${isDownloading ? "disabled" : ""}>Baixar</button>
			`;
		}

		item.title = `${m.name} (${sizeText}) - ${m.precision}\n${m.description}\nVRAM mínima: ${m.min_vram_gb} GB`;
		item.innerHTML = `
			<span class="model-status">${statusIcon}</span>
			<div class="model-info">
				<div class="model-name">${m.name} ${badge}</div>
				<div class="model-desc">${m.precision} - ${m.description}</div>
			</div>
			<span class="model-size">${sizeText}</span>
			${actionBtns}
		`;

		// Click to select model (only downloaded ones)
		item.addEventListener("click", (e) => {
			if (e.target.closest(".model-btn") || e.target.closest(".model-btn-link")) return;
			if (!m.downloaded) return;
			selectedModel = m.name;
			renderModels(data);
			updateButtons(false, "idle"); // refresh button state
			updatePrecisionUI(parseInt(precisionSlider.value)); // refresh warning
		});

		modelsList.appendChild(item);
	}

	// Wire up action buttons
	modelsList.querySelectorAll("[data-action]").forEach((btn) => {
		btn.addEventListener("click", async (e) => {
			e.stopPropagation();
			const action = btn.dataset.action;
			const model = btn.dataset.model;
			if (action === "download") await downloadModel(model);
			if (action === "delete") await deleteModel(model);
			if (action === "cancel") await cancelDownload();
		});
	});

	// Auto-select first downloaded or current
	if (!selectedModel) {
		const current = data.current_model;
		const downloaded = data.models.filter((m) => m.downloaded);
		if (downloaded.find((m) => m.name === current)) {
			selectedModel = current;
		} else if (downloaded.length > 0) {
			selectedModel = downloaded[0].name;
		}
	}
}

async function downloadModel(name) {
	addLog(`Iniciando download: ${name}...`, "info");
	try {
		const resp = await fetch(`${API_URL}/models/${name}/download`, { method: "POST" });
		const data = await resp.json();
		if (!resp.ok) {
			addLog(`Erro: ${data.error}`, "error");
			return;
		}
		startPolling();
	} catch (e) {
		addLog("Erro: servidor não responde", "error");
	}
}

async function cancelDownload() {
	addLog("Cancelando download...", "warn");
	try {
		await fetch(`${API_URL}/models/cancel`, { method: "POST" });
	} catch (e) {
		addLog("Erro ao cancelar", "error");
	}
}

async function deleteModel(name) {
	try {
		const resp = await fetch(`${API_URL}/models/${name}`, { method: "DELETE" });
		const data = await resp.json();
		if (!resp.ok) {
			addLog(`Erro: ${data.error}`, "error");
			return;
		}
		addLog(`Modelo ${name} removido`, "success");
		if (selectedModel === name) selectedModel = null;
		await fetchModels();
	} catch (e) {
		addLog("Erro: servidor não responde", "error");
	}
}

// ---------------------------------------------------------------------------
// Button state
// ---------------------------------------------------------------------------
function updateButtons(modelLoaded, stage, currentModelName) {
	const busy = ["loading_model", "downloading_model", "transcribing"].includes(stage);
	const hasSelected = selectedModel && currentModels.some((m) => m.name === selectedModel && m.downloaded);
	const wantsSwap = modelLoaded && selectedModel && selectedModel !== currentModelName;

	if (stage === "loading_model") {
		btnLoad.disabled = true;
		btnLoad.textContent = "Carregando...";
		btnUnload.disabled = true;
	} else if (wantsSwap) {
		// Model loaded but user selected a different one
		btnLoad.disabled = busy;
		btnLoad.textContent = "Trocar Modelo";
		btnUnload.disabled = busy;
	} else if (modelLoaded) {
		btnLoad.disabled = true;
		btnLoad.textContent = "Modelo na GPU";
		btnUnload.disabled = busy;
	} else {
		btnLoad.disabled = !hasSelected || busy;
		btnLoad.textContent = "Subir Modelo na GPU";
		btnUnload.disabled = true;
	}
}

// ---------------------------------------------------------------------------
// Health check
// ---------------------------------------------------------------------------
async function checkHealth() {
	try {
		const ctrl = new AbortController();
		const timeout = setTimeout(() => ctrl.abort(), 2000);
		const resp = await fetch(`${API_URL}/health`, { signal: ctrl.signal });
		clearTimeout(timeout);
		if (!resp.ok) throw new Error("not ok");

		const data = await resp.json();
		const busy = ["loading_model", "transcribing", "downloading_model"].includes(data.current_stage);
		dot.className = "status-dot " + (busy ? "loading" : "online");
		statusText.textContent = "Whats GPU rodando";
		const gpuLabel = data.gpu ? `${data.gpu_name} (${data.vram_gb}GB)` : "CPU";
		const loadedLabel = data.model_loaded ? `${data.model} carregado` : "Nenhum modelo carregado";
		statusModel.textContent = `${gpuLabel} | ${loadedLabel}`;
		updateButtons(data.model_loaded, data.current_stage, data.model);
		return true;
	} catch (e) {
		dot.className = "status-dot offline";
		statusText.textContent = "Whats GPU offline";
		statusModel.textContent = "Inicie o Whats GPU.exe";
		updateButtons(false, "idle", null);
		return false;
	}
}

// ---------------------------------------------------------------------------
// Status polling
// ---------------------------------------------------------------------------
const STAGE_LABELS = {
	loading_model:    { text: "Subindo modelo na GPU...", css: "warn" },
	model_ready:      { text: "Modelo pronto", css: "success" },
	transcribing:     { text: "Transcrevendo...", css: "info" },
	done:             { text: "Transcrição concluída", css: "success" },
	oom_error:        { text: "Erro: GPU sem memória", css: "error" },
	unloading:        { text: "Descarregando modelo...", css: "warn" },
	unloaded:         { text: "GPU liberada", css: "success" },
	downloading_model:{ text: "Baixando modelo...", css: "warn" },
	download_complete:{ text: "Download concluído", css: "success" },
	download_error:   { text: "Erro no download", css: "error" },
};

async function pollStatus() {
	try {
		const ctrl = new AbortController();
		const timeout = setTimeout(() => ctrl.abort(), 2000);
		const resp = await fetch(`${API_URL}/status`, { signal: ctrl.signal });
		clearTimeout(timeout);
		if (!resp.ok) return;

		const data = await resp.json();

		// Update progress bar always (even same stage, for progress updates)
		updateProgressBar(data.stage, data.detail);

		// Log stage changes (only when stage actually changes)
		if (data.stage !== lastLogStage && data.stage !== "idle") {
			const label = STAGE_LABELS[data.stage];
			if (label) {
				let text = label.text;
				if (data.stage === "downloading_model" && data.detail && data.detail.model) {
					text = `Baixando ${data.detail.model}...`;
				}
				if (data.stage === "download_error" && data.detail && data.detail.error) {
					text = `Erro no download: ${data.detail.error}`;
				}
				addLog(text, label.css);
			}
			lastLogStage = data.stage;
		}

		// Refresh model list on download complete/error/cancel
		if (data.stage !== lastStage) {
			if (["download_complete", "download_error", "idle"].includes(data.stage) && lastStage === "downloading_model") {
				await fetchModels();
			}
		}
		lastStage = data.stage;

		await checkHealth();
	} catch (e) {
		// Ignore
	}
}

function startPolling() {
	if (pollTimer) return;
	pollTimer = setInterval(pollStatus, 1500);
}

function stopPolling() {
	if (pollTimer) {
		clearInterval(pollTimer);
		pollTimer = null;
	}
}

// ---------------------------------------------------------------------------
// Button handlers
// ---------------------------------------------------------------------------
btnLoad.addEventListener("click", async () => {
	if (!selectedModel) return;
	btnLoad.disabled = true;
	btnLoad.textContent = "Carregando...";
	dot.className = "status-dot loading";
	addLog(`Carregando ${selectedModel} na GPU...`, "info");

	try {
		await fetch(`${API_URL}/model/load`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ model: selectedModel }),
		});
		startPolling();
	} catch (e) {
		addLog("Erro: servidor não responde", "error");
		await checkHealth();
	}
});

btnUnload.addEventListener("click", async () => {
	btnUnload.disabled = true;
	addLog("Liberando GPU...", "info");

	try {
		await fetch(`${API_URL}/model/unload`, { method: "POST" });
		addLog("GPU liberada", "success");
		await checkHealth();
	} catch (e) {
		addLog("Erro: servidor não responde", "error");
		await checkHealth();
	}
});

btnRefresh.addEventListener("click", async () => {
	btnRefresh.textContent = "\u23F3";
	await fetchModels();
	addLog("Lista de modelos atualizada", "info");
	btnRefresh.textContent = "\u21BB";
});

// ---------------------------------------------------------------------------
// Precision slider
// ---------------------------------------------------------------------------
function updatePrecisionUI(level) {
	const preset = PRECISION_PRESETS[level];
	precisionValue.textContent = preset.name;
	precisionDesc.textContent = preset.desc;

	// Warn if small model + max precision
	const loadedModel = selectedModel || "";
	if (level === 2 && SMALL_MODELS.includes(loadedModel)) {
		precisionWarn.textContent =
			`O modelo "${loadedModel}" é pequeno. Para precisão máxima, recomendamos o large-v3. ` +
			`A transcrição será mais lenta e o ganho de qualidade será limitado pelo modelo.`;
		precisionWarn.classList.add("visible");
	} else {
		precisionWarn.classList.remove("visible");
	}
}

precisionSlider.addEventListener("input", () => {
	const level = parseInt(precisionSlider.value);
	updatePrecisionUI(level);
	// Save to chrome.storage
	chrome.storage.local.set({ precisionLevel: level });
});

// Load saved precision level
chrome.storage.local.get("precisionLevel", (data) => {
	const level = data.precisionLevel != null ? data.precisionLevel : 1;
	precisionSlider.value = level;
	updatePrecisionUI(level);
});

// ---------------------------------------------------------------------------
// Clear transcription cache
// ---------------------------------------------------------------------------
btnClearCache.addEventListener("click", async () => {
	const all = await chrome.storage.local.get(null);
	const keysToRemove = Object.keys(all).filter((k) => k !== "precisionLevel");
	if (keysToRemove.length === 0) {
		addLog("Nenhuma transcrição em cache", "info");
		return;
	}
	await chrome.storage.local.remove(keysToRemove);
	addLog(`${keysToRemove.length} transcrição(ões) removida(s) do cache`, "success");
	addLog("Recarregue o WhatsApp Web para re-transcrever", "info");
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
(async () => {
	const online = await checkHealth();
	if (online) {
		await fetchModels();
		startPolling();
	}
	healthTimer = setInterval(async () => {
		const ok = await checkHealth();
		if (ok && !pollTimer) {
			await fetchModels();
			startPolling();
		}
		if (!ok) stopPolling();
	}, 5000);
})();
