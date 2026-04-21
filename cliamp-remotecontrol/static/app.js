function send(cmd) {
    fetch('/api/' + cmd, { cache: 'no-store' }).then(update);
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

    // 👉 fetch hostname first
    let hostname = "";
    try {
        const res = await fetch('/api/status', { cache: 'no-store' });
        const data = await res.json();
        hostname = String(data.hostname || "").toUpperCase();
    } catch (e) {
        hostname = "UNKNOWN";
    }

    const lines = [
        "[boot] cliamp remote control",
        "[init] loading core modules...",
        "[init] audio interface ready",
        "[init] ui renderer ready",
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

startSequence();
setInterval(update, 2000);
