function send(cmd) {
    fetch('/api/' + cmd, { cache: 'no-store' }).then(update);
}

let listenUrl = null;
let listenOpen = false;
let listenReason = "Listening unavailable for this track";
let listenVisible = true;

function getListenElements() {
    return {
        button: document.getElementById("listen-btn"),
        panel: document.getElementById("listen-panel"),
        audio: document.getElementById("listen-audio"),
        status: document.getElementById("listen-status"),
    };
}

function setListenButtonState(enabled) {
    const { button } = getListenElements();
    if (!button) return;

    button.disabled = !enabled;
    button.classList.toggle("is-active", enabled);
}

function setListenVisibility(visible) {
    const { button, panel, audio } = getListenElements();
    if (!button || !panel || !audio) return;

    listenVisible = Boolean(visible);
    button.hidden = !listenVisible;

    if (!listenVisible) {
        listenOpen = false;
        panel.hidden = true;
        if (!audio.paused) audio.pause();
        audio.removeAttribute("src");
        audio.load();
    }
}

function syncListenPanel() {
    const { button, panel, audio, status } = getListenElements();
    if (!button || !panel || !audio || !status) return;

    if (!listenVisible) {
        panel.hidden = true;
        return;
    }

    const available = Boolean(listenUrl);
    setListenButtonState(available);
    button.setAttribute("aria-expanded", listenOpen ? "true" : "false");

    if (!listenOpen) {
        panel.hidden = true;
        status.textContent = available
            ? "Open the panel to hear the current stream"
            : listenReason;
        if (!audio.paused) audio.pause();
        return;
    }

    panel.hidden = false;

    if (!available) {
        status.textContent = listenReason;
        audio.removeAttribute("src");
        audio.load();
        return;
    }

    status.textContent = "Streaming current playback";

    const resolvedListenUrl = new URL(listenUrl, window.location.href).href;
    if (audio.src !== resolvedListenUrl) {
        audio.src = listenUrl;
        audio.load();
    }
}

function setListenUrl(nextUrl) {
    const normalized = typeof nextUrl === "string" && nextUrl.trim() ? nextUrl.trim() : null;
    if (listenUrl === normalized) return;

    listenUrl = normalized;
    syncListenPanel();
}

function setListenReason(nextReason) {
    listenReason = typeof nextReason === "string" && nextReason.trim()
        ? nextReason.trim()
        : "Listening unavailable for this track";

    syncListenPanel();
}

function toggleListenPanel() {
    listenOpen = !listenOpen;
    syncListenPanel();
}

function closeListenPanel() {
    if (!listenOpen) return;
    listenOpen = false;
    syncListenPanel();
}

function setVisualizerState(stateName) {
    const visualizer = document.getElementById("header-visualizer");
    if (visualizer) {
        visualizer.className = "header-visualizer " + stateName;
    }
}

function setVisualizerLevel(volume) {
    const clamped = Math.max(-30, Math.min(6, Number(volume ?? -15)));
    const normalized = (clamped + 30) / 36;
    const glow = 0.10 + (normalized * 0.55);
    document.documentElement.style.setProperty("--viz-glow", glow.toFixed(3));
}

function syncVisualizerWidth() {
    const title = document.getElementById("brand-title");
    const visualizer = document.getElementById("header-visualizer");
    if (!title || !visualizer) return;

    const width = Math.ceil(title.getBoundingClientRect().width);
    visualizer.style.width = width + "px";
}

function update() {
    fetch('/api/status', { cache: 'no-store' })
        .then(r => r.json())
        .then(d => {
            const header = document.getElementById("now-playing-header");
            const hostname = (d.hostname || "").toUpperCase();

            if (header) {
                if (d.connected === false) {
                    header.innerText = "DISCONNECTED";
                    setVisualizerState("disconnected");
                } else {
                    const state = String(d.state || "").trim().toLowerCase();

                    if (state === "playing") {
                        header.innerText = hostname
                            ? `NOW PLAYING ON ${hostname}`
                            : "NOW PLAYING";
                        setVisualizerState("playing");
                    } else if (state === "paused") {
                        header.innerText = "PAUSED";
                        setVisualizerState("paused");
                    } else {
                        header.innerText = "STOPPED";
                        setVisualizerState("stopped");
                    }
                }

                header.style.display = "block";
            }

            const nowPlaying = document.getElementById("now-playing");
            if (nowPlaying) {
                nowPlaying.innerText =
                    d.artist ? d.artist + " - " + d.title : (d.title || "Nothing Playing");
            }

            const eq = document.getElementById("eq-inline");
            if (eq) eq.innerText = "[" + (d.eq_name || "FLAT") + "]";

            const shuffle = document.getElementById("shuffle-inline");
            if (shuffle) shuffle.innerText = d.shuffle ? "[ON]" : "[OFF]";

            const repeat = document.getElementById("repeat-inline");
            if (repeat) repeat.innerText = "[" + (d.repeat || "OFF") + "]";

            const volume = Number(d.volume ?? -15.0);
            let percent = ((volume + 30) / 36) * 100;
            percent = Math.max(0, Math.min(100, percent));

            const volFill = document.getElementById("vol-fill");
            if (volFill) volFill.style.width = percent + "%";

            const volText = document.getElementById("vol-text");
            if (volText) volText.innerText = volume.toFixed(1) + " dB";

            setListenVisibility(d.listen_visible !== false);
            setListenUrl(d.listen_url);
            setListenReason(d.listen_reason);
            setVisualizerLevel(volume);
            syncVisualizerWidth();
        })
        .catch(() => {
            const header = document.getElementById("now-playing-header");
            if (header) header.innerText = "DISCONNECTED";

            const nowPlaying = document.getElementById("now-playing");
            if (nowPlaying) nowPlaying.innerText = "Disconnected";

            setVisualizerState("disconnected");
            setVisualizerLevel(-30);
            setListenVisibility(true);
            setListenUrl(null);
            setListenReason("Remote disconnected");
        });
}

async function runPowerOn() {
    const power = document.getElementById("power");
    if (!power) return;

    power.classList.add("animate");
    await sleep(720);
    power.classList.add("hidden");
}

function createCursor() {
    const cursor = document.createElement("span");
    cursor.className = "boot-cursor";
    return cursor;
}

async function typeLine(el, text) {
    const line = document.createElement("div");
    line.className = "boot-line";

    const textSpan = document.createElement("span");
    const cursor = createCursor();

    line.appendChild(textSpan);
    line.appendChild(cursor);
    el.appendChild(line);

    for (const c of text) {
        textSpan.textContent += c;
        await sleep(8 + Math.random() * 28);
    }

    line.removeChild(cursor);
    await sleep(90 + Math.random() * 140);
}

async function runBoot() {
    const boot = document.getElementById("boot");
    const el = document.getElementById("boot-text");
    if (!boot || !el) return;

    boot.classList.add("visible");

    let statusData = null;
    let hostname = "";
    let audioInterfaceDetected = false;
    let audioInterfaceName = "";
    let audioBackendDetected = false;
    let audioBackendName = "pulseaudio/pipewire";

    try {
        const res = await fetch('/api/status', { cache: 'no-store' });
        statusData = await res.json();
        hostname = String(statusData.hostname || "").toUpperCase();
        audioInterfaceDetected = Boolean(statusData.audio_interface_detected);
        audioInterfaceName = String(statusData.audio_interface_name || "").trim();
        audioBackendDetected = Boolean(statusData.audio_backend_detected);
        audioBackendName = String(statusData.audio_backend_name || "pulseaudio/pipewire").trim();
    } catch (e) {
        hostname = "UNKNOWN";
    }

    const audioInterfaceLine = audioInterfaceDetected && audioInterfaceName
        ? `[ok  ] audio interface ${audioInterfaceName} detected`
        : "[failed] audio interface detection";

    const audioBackendLine = audioBackendDetected
        ? `[ok  ] ${audioBackendName} detected`
        : `[failed] ${audioBackendName} detection`;

    const lines = [
        "[boot] cliamp remote control",
        "[init] loading core modules...",
        audioInterfaceLine,
        audioBackendLine,
        "[ok  ] ui renderer ready",
        "[net ] resolving socket path",
        "[net ] ~/.config/cliamp/cliamp.sock",
        hostname
            ? `[conn] opening unix socket on ${hostname}...`
            : "[conn] opening unix socket...",
        "[conn] handshake established",
        "[sync] fetching player state",
        "[sync] volume / eq / playback",
        "[ok  ] cliamp remote ready"
    ];

    for (const line of lines) {
        await typeLine(el, line);
    }

    const finalLine = document.createElement("div");
    finalLine.className = "boot-line";
    finalLine.appendChild(createCursor());
    el.appendChild(finalLine);

    await sleep(420);

    boot.classList.remove("visible");
    boot.classList.add("hidden");
}

async function startSequence() {
    await runPowerOn();
    await runBoot();

    const ui = document.getElementById("ui");
    if (ui) ui.style.opacity = 1;

    syncVisualizerWidth();
    update();
}

function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

window.addEventListener("resize", syncVisualizerWidth);
document.getElementById("listen-btn")?.addEventListener("click", toggleListenPanel);
document.getElementById("listen-close")?.addEventListener("click", closeListenPanel);

startSequence();
setInterval(update, 2000);