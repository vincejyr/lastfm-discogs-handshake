let collection = [];
let searchScope = "collection"; // "collection" | "discogs"
let searchDebounceTimer = null;

const grid = document.getElementById("grid");
const status = document.getElementById("status");
const search = document.getElementById("search");
const scopeCollectionBtn = document.getElementById("scope-collection");
const scopeDiscogsBtn = document.getElementById("scope-discogs");
const refreshBtn = document.getElementById("refresh-btn");
const modalBackdrop = document.getElementById("modal-backdrop");
const modalTitle = document.getElementById("modal-title");
const modalTracklist = document.getElementById("modal-tracklist");
const modalResult = document.getElementById("modal-result");
const dryRunCheckbox = document.getElementById("dry-run-checkbox");
const scrobbleBtn = document.getElementById("scrobble-btn");
const modalClose = document.getElementById("modal-close");
const lastfmBanner = document.getElementById("lastfm-banner");
const lastfmBannerText = document.getElementById("lastfm-banner-text");
const lastfmConnectBtn = document.getElementById("lastfm-connect-btn");

let currentReleaseId = null;
let lastfmConnected = false;
let pendingAuthUrl = null;

function updateLastfmUI() {
  if (lastfmConnected) {
    lastfmBanner.classList.add("hidden");
    dryRunCheckbox.disabled = false;
  } else {
    lastfmBanner.classList.remove("hidden");
    dryRunCheckbox.checked = true;
    dryRunCheckbox.disabled = true;
    if (pendingAuthUrl) {
      lastfmBannerText.textContent = "Waiting for you to approve access on the Last.fm page that opened…";
      lastfmConnectBtn.textContent = "I've allowed it — finish connecting";
    } else {
      lastfmBannerText.textContent = "Not connected to Last.fm — real scrobbles are disabled until you connect.";
      lastfmConnectBtn.textContent = "Connect to Last.fm";
    }
  }
}

async function checkLastfmStatus() {
  const res = await fetch("/api/lastfm/status");
  const data = await res.json();
  lastfmConnected = data.connected;
  updateLastfmUI();
}

async function handleLastfmConnectClick() {
  lastfmConnectBtn.disabled = true;
  try {
    if (!pendingAuthUrl) {
      const res = await fetch("/api/lastfm/start-auth", { method: "POST" });
      const data = await res.json();
      if (data.error) {
        lastfmBannerText.textContent = `Error: ${data.error}`;
        return;
      }
      pendingAuthUrl = data.auth_url;
      window.open(data.auth_url, "_blank");
      updateLastfmUI();
    } else {
      const res = await fetch("/api/lastfm/complete-auth", { method: "POST" });
      const data = await res.json();
      if (data.error) {
        lastfmBannerText.textContent = `Error: ${data.error}`;
        return;
      }
      lastfmConnected = true;
      pendingAuthUrl = null;
      updateLastfmUI();
    }
  } finally {
    lastfmConnectBtn.disabled = false;
  }
}

function renderGrid(items) {
  grid.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <img src="${item.thumb || ''}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
      <div class="card-info">
        <div class="card-title">${escapeHtml(item.artist)} - ${escapeHtml(item.title)}</div>
        <div class="card-year">${item.year || ""}</div>
      </div>
    `;
    card.addEventListener("click", () => openModal(item.id));
    grid.appendChild(card);
  }
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function filterAndRender() {
  const q = search.value.trim().toLowerCase();
  const filtered = q
    ? collection.filter(i => i.artist.toLowerCase().includes(q) || i.title.toLowerCase().includes(q))
    : collection;
  renderGrid(filtered);
  status.textContent = `${filtered.length} of ${collection.length} releases`;
}

async function loadCollection() {
  const res = await fetch("/api/collection");
  collection = await res.json();
  if (searchScope === "collection") {
    filterAndRender();
  }
}

async function refreshCollection() {
  refreshBtn.disabled = true;
  const previousStatus = status.textContent;
  status.textContent = "Refreshing your collection from Discogs…";
  try {
    const res = await fetch("/api/collection/refresh", { method: "POST" });
    const data = await res.json();
    if (data.error) {
      status.textContent = data.error;
      return;
    }
    await loadCollection();
    if (searchScope !== "collection") {
      status.textContent = `Collection refreshed (${collection.length} releases) — ${previousStatus}`;
    }
  } catch (err) {
    status.textContent = `Refresh failed: ${err}`;
  } finally {
    refreshBtn.disabled = false;
  }
}

async function searchDiscogs(query) {
  status.textContent = "Searching Discogs…";
  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    if (data.error) {
      status.textContent = data.error;
      renderGrid([]);
      return;
    }
    renderGrid(data);
    status.textContent = `${data.length} results from Discogs`;
  } catch (err) {
    status.textContent = `Search failed: ${err}`;
  }
}

function handleSearchInput() {
  if (searchScope === "collection") {
    filterAndRender();
    return;
  }

  clearTimeout(searchDebounceTimer);
  const query = search.value.trim();
  if (query.length < 2) {
    renderGrid([]);
    status.textContent = "Type at least 2 characters to search Discogs.";
    return;
  }
  status.textContent = "Searching Discogs…";
  searchDebounceTimer = setTimeout(() => searchDiscogs(query), 400);
}

function setSearchScope(scope) {
  searchScope = scope;
  scopeCollectionBtn.classList.toggle("active", scope === "collection");
  scopeDiscogsBtn.classList.toggle("active", scope === "discogs");
  search.placeholder = scope === "collection"
    ? "Search your collection (artist or album)…"
    : "Search all of Discogs (artist or album)…";
  handleSearchInput();
}

async function openModal(releaseId) {
  currentReleaseId = releaseId;
  modalResult.textContent = "";
  modalTitle.textContent = "Loading tracklist…";
  modalTracklist.innerHTML = "";
  scrobbleBtn.disabled = false;
  dryRunCheckbox.checked = true;
  modalBackdrop.classList.remove("hidden");

  const res = await fetch(`/api/release/${releaseId}`);
  const data = await res.json();
  if (data.error) {
    modalTitle.textContent = "Error";
    modalResult.textContent = data.error;
    return;
  }

  modalTitle.textContent = `${data.artist} - ${data.title}`;
  modalTracklist.innerHTML = data.tracks.map(t => `
    <li>${escapeHtml(t.artist)} - ${escapeHtml(t.title)}
      <span class="track-duration">(${formatDuration(t.duration)})</span>
    </li>
  `).join("");
}

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

async function submitScrobble() {
  const dryRun = dryRunCheckbox.checked;
  scrobbleBtn.disabled = true;
  modalResult.textContent = dryRun ? "Previewing…" : "Scrobbling…";

  try {
    const res = await fetch("/api/scrobble", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ release_id: currentReleaseId, dry_run: dryRun }),
    });
    const data = await res.json();

    if (data.error) {
      modalResult.textContent = `Error: ${data.error}`;
    } else if (dryRun) {
      const lines = data.planned.map(t => {
        const when = new Date(t.timestamp * 1000).toLocaleTimeString();
        return `[${when}] ${t.artist} - ${t.title}`;
      });
      modalResult.textContent = `Would scrobble ${data.planned.length} tracks:\n` + lines.join("\n");
    } else {
      modalResult.textContent = `Scrobbled ${data.planned.length} tracks to Last.fm.`;
    }
  } catch (err) {
    modalResult.textContent = `Error: ${err}`;
  } finally {
    scrobbleBtn.disabled = false;
  }
}

search.addEventListener("input", handleSearchInput);
scopeCollectionBtn.addEventListener("click", () => setSearchScope("collection"));
scopeDiscogsBtn.addEventListener("click", () => setSearchScope("discogs"));
refreshBtn.addEventListener("click", refreshCollection);
scrobbleBtn.addEventListener("click", submitScrobble);
modalClose.addEventListener("click", () => modalBackdrop.classList.add("hidden"));
modalBackdrop.addEventListener("click", (e) => {
  if (e.target === modalBackdrop) modalBackdrop.classList.add("hidden");
});
lastfmConnectBtn.addEventListener("click", handleLastfmConnectClick);

loadCollection();
checkLastfmStatus();
