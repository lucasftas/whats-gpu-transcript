(() => {
	let Msg;
	let getOrCreateURL;

	const TRANSCRIBE_TIMEOUT = 300000; // 5 min

	const BUTTON_STYLE = `
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 4px 10px;
		margin-top: 6px;
		border: none;
		border-radius: 16px;
		background: #008069;
		color: white;
		font-size: 12px;
		font-family: inherit;
		cursor: pointer;
		transition: background 0.2s;
	`;

	const STATUS_STYLE = `
		font-size: 11px;
		color: #8696a0;
		padding: 2px 10px;
		margin-top: 2px;
	`;

	const PROGRESS_BAR_STYLE = `
		height: 3px;
		background: #1a262d;
		border-radius: 2px;
		margin: 4px 10px 0;
		overflow: hidden;
	`;

	const PROGRESS_FILL_STYLE = `
		height: 100%;
		background: #008069;
		border-radius: 2px;
		width: 0%;
		transition: width 0.5s ease;
	`;

	const BUTTON_HOVER = "#006e5a";
	const BUTTON_LOADING = "#999";

	const STAGE_LABELS = {
		loading_model: "Subindo modelo na GPU...",
		model_ready: "Modelo pronto",
		transcribing: "Transcrevendo áudio...",
		done: "Finalizando...",
		oom_error: "Erro: GPU sem memória",
	};

	const ERROR_MESSAGES = {
		network: "Whats GPU não está rodando. Inicie o app.",
		oom: "GPU sem memória. Clique em Limpar GPU no popup e tente novamente.",
		timeout: "Áudio muito longo ou servidor travado. Tente um áudio mais curto.",
	};

	// Wait for WhatsApp Web to load
	const interval = setInterval(() => {
		if (!document.querySelector("#side")) return;
		clearInterval(interval);

		Msg = require("WAWebCollections").Msg;
		getOrCreateURL = require("WAWebMediaInMemoryBlobCache").InMemoryMediaBlobCache.getOrCreateURL;

		const observer = new MutationObserver(mutationsHandler);
		observer.observe(document.body, {
			childList: true,
			subtree: true,
		});
	}, 100);

	function mutationsHandler() {
		[...document.querySelectorAll("title")]
			.filter((el) => {
				const text = el.textContent.trim();
				return text === "ic-play-arrow-filled" || text === "ic-pause-filled";
			})
			.forEach((audio) => {
				if (audio.parentNode.classList.contains("WhatsTranscript")) return;
				audio.parentNode.classList.add("WhatsTranscript");

				const msgEl = audio.closest("[data-id]");
				if (!msgEl) return;

				const id = msgEl.dataset.id;
				const el =
					audio.closest("._amk6._amlo") ||
					audio.closest("._ak49._ak48") ||
					audio.closest("._ak4a._ak48");

				if (!el) return;
				injectButton(id, el);
			});
	}

	function injectButton(id, el) {
		if (el.querySelector(".wt-transcribe-btn")) return;

		const btn = document.createElement("button");
		btn.className = "wt-transcribe-btn";
		btn.style.cssText = BUTTON_STYLE;
		btn.innerHTML = "&#127908; Transcrever";
		btn.title = "Transcrever áudio localmente (GPU)";

		btn.addEventListener("mouseenter", () => {
			if (!btn.disabled) btn.style.background = BUTTON_HOVER;
		});
		btn.addEventListener("mouseleave", () => {
			if (!btn.disabled) btn.style.background = "#008069";
		});

		btn.addEventListener("click", () => onTranscribeClick(id, el, btn));
		el.appendChild(btn);
	}

	// ---------------------------------------------------------------------------
	// Mini-status below button during transcription
	// ---------------------------------------------------------------------------
	function createStatusDiv(el) {
		let container = el.querySelector(".wt-status-container");
		if (!container) {
			container = document.createElement("div");
			container.className = "wt-status-container";

			const statusDiv = document.createElement("div");
			statusDiv.className = "wt-status";
			statusDiv.style.cssText = STATUS_STYLE;

			const progressBar = document.createElement("div");
			progressBar.className = "wt-progress-bar";
			progressBar.style.cssText = PROGRESS_BAR_STYLE;

			const progressFill = document.createElement("div");
			progressFill.className = "wt-progress-fill";
			progressFill.style.cssText = PROGRESS_FILL_STYLE;

			progressBar.appendChild(progressFill);
			container.appendChild(statusDiv);
			container.appendChild(progressBar);
			el.appendChild(container);
		}
		return {
			statusDiv: container.querySelector(".wt-status"),
			progressFill: container.querySelector(".wt-progress-fill"),
		};
	}

	function removeStatusDiv(el) {
		const c = el.querySelector(".wt-status-container");
		if (c) c.remove();
	}

	function startStatusPolling(el, btn) {
		const { statusDiv, progressFill } = createStatusDiv(el);

		const timer = setInterval(() => {
			// Request status via content.js bridge (avoids CSP block)
			window.dispatchEvent(new CustomEvent("AudioToText:statusRequest"));
		}, 1500);

		// Listen for status responses from content.js
		function onStatusResponse(event) {
			const data = event.detail;
			if (!data) return;

			let label = STAGE_LABELS[data.stage];
			let pct = 0;

			if (data.stage === "transcribing" && data.detail) {
				pct = data.detail.progress_pct || 0;
				label = `Transcrevendo... ${pct}% (${data.detail.processed_s || 0}s de ${data.detail.total_s || "?"}s)`;
			} else if (data.stage === "loading_model") {
				label = "Subindo modelo na GPU...";
			}

			if (label) statusDiv.textContent = label;
			progressFill.style.width = pct + "%";

			// Update button text with percentage
			if (data.stage === "transcribing" && pct > 0) {
				btn.innerHTML = `&#9203; ${pct}%`;
			}
		}

		window.addEventListener("AudioToText:statusResponse", onStatusResponse);

		return () => {
			clearInterval(timer);
			window.removeEventListener("AudioToText:statusResponse", onStatusResponse);
			removeStatusDiv(el);
		};
	}

	// ---------------------------------------------------------------------------
	// Transcription click handler
	// ---------------------------------------------------------------------------
	async function onTranscribeClick(id, el, btn) {
		btn.disabled = true;
		btn.style.background = BUTTON_LOADING;
		btn.style.cursor = "wait";
		btn.innerHTML = "&#9203; Transcrevendo...";

		// Start status polling
		const stopPolling = startStatusPolling(el, btn);

		try {
			// Check cache first
			const cached = await checkCache(id);
			if (cached) {
				stopPolling();
				appendText(el, cached);
				btn.remove();
				return;
			}

			// Get message and ensure media is downloaded
			const msg = Msg.get(id);
			if (!msg) {
				stopPolling();
				showError(el, btn, "Mensagem não encontrada");
				return;
			}

			// Download media if not resolved
			if (msg.mediaData.mediaStage !== "RESOLVED") {
				msg.downloadMedia({
					downloadEvenIfExpensive: true,
					isUserInitiated: true,
					rmrReason: 1,
				});

				const resolved = await waitForMedia(msg, 30000);
				if (!resolved) {
					stopPolling();
					showError(el, btn, "Timeout ao baixar áudio");
					return;
				}
			}

			// Get blob and convert to base64
			const blobURL = getOrCreateURL(msg.filehash);
			const response = await fetch(blobURL);
			const blob = await response.blob();
			const audioBase64 = await blobToBase64(blob);

			// Send for transcription via content.js bridge with timeout
			const record = await Promise.race([
				new Promise((resolve) => {
					window.addEventListener(
						`AudioToText:${id}`,
						(event) => resolve(event.detail),
						{ once: true }
					);
					window.dispatchEvent(
						new CustomEvent("AudioToText:transcript", {
							detail: { id, audioBase64 },
						})
					);
				}),
				new Promise((_, reject) =>
					setTimeout(() => reject(new Error("TIMEOUT")), TRANSCRIBE_TIMEOUT)
				),
			]);

			stopPolling();

			if (record.error && record.errorType) {
				const friendlyMsg = ERROR_MESSAGES[record.errorType] || record.transcription;
				showError(el, btn, friendlyMsg);
			} else {
				appendText(el, record);
				btn.remove();
			}
		} catch (e) {
			stopPolling();
			if (e.message === "TIMEOUT") {
				showError(el, btn, ERROR_MESSAGES.timeout);
			} else {
				showError(el, btn, `Erro: ${e.message}`);
			}
		}
	}

	function checkCache(id) {
		return new Promise((resolve) => {
			window.addEventListener(
				`AudioToText:${id}`,
				(event) => resolve(event.detail),
				{ once: true }
			);
			window.dispatchEvent(
				new CustomEvent("AudioToText:cache", { detail: id })
			);
		});
	}

	function waitForMedia(msg, timeout) {
		return new Promise((resolve) => {
			const start = Date.now();
			const check = setInterval(() => {
				if (msg.mediaData.mediaStage === "RESOLVED") {
					clearInterval(check);
					resolve(true);
				} else if (Date.now() - start > timeout) {
					clearInterval(check);
					resolve(false);
				}
			}, 100);
		});
	}

	function blobToBase64(blob) {
		return new Promise((resolve, reject) => {
			const reader = new FileReader();
			reader.onloadend = () => {
				const base64 = reader.result.split(",")[1];
				resolve(base64);
			};
			reader.onerror = reject;
			reader.readAsDataURL(blob);
		});
	}

	function appendText(el, record) {
		if (el.querySelector(".wt-transcription")) return;

		const txt = document.createElement("div");
		txt.className = "wt-transcription selectable-text copyable-text";
		txt.innerText = record.transcription;

		if (record.error) {
			txt.style.cssText = `max-width: ${el.clientWidth}px; overflow: hidden; padding: 10px 20px; color: #ef4146; font-size: 12px; font-weight: bold;`;
		} else {
			txt.style.cssText = `max-width: ${el.clientWidth}px; overflow: hidden; padding: 10px 20px; font-size: 13px; color: inherit;`;
		}

		el.appendChild(txt);
	}

	function showError(el, btn, message) {
		btn.disabled = false;
		btn.style.background = "#008069";
		btn.style.cursor = "pointer";
		btn.innerHTML = "&#127908; Transcrever";

		const errDiv = document.createElement("div");
		errDiv.style.cssText = "padding: 6px 20px; color: #ef4146; font-size: 12px;";
		errDiv.innerText = message;
		el.appendChild(errDiv);

		setTimeout(() => errDiv.remove(), 5000);
	}
})();
