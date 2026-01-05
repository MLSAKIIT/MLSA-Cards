const connectBtn = document.getElementById("connectBtn");
const signinBtn = document.getElementById("signinBtn");
const mintBtn = document.getElementById("mintBtn");
const walletEl = document.getElementById("wallet");
const chainIdEl = document.getElementById("chainId");
const networkNameEl = document.getElementById("networkName");
const connectionInfoEl = document.getElementById("connectionInfo");
const statusEl = document.getElementById("status");
const navPointsEl = document.getElementById("navPoints");
const storeGrid = document.getElementById("storeGrid");
const storeInfo = document.getElementById("storeInfo");
const mintResult = document.getElementById("mintResult");
const mintPreview = document.getElementById("mintPreview");
const previewName = document.getElementById("previewName");
const previewDesc = document.getElementById("previewDesc");
const previewImage = document.getElementById("previewImage");
const nameInput = document.getElementById("name");
const descInput = document.getElementById("desc");
const imageInput = document.getElementById("image");

let provider;
let signer;
let wallet;
let token;
let currentChainId;
let providerEventsBound = false;

const networkNames = {
  "31337": "Hardhat (Localhost)",
  "11155111": "Sepolia Testnet",
  "80002": "Polygon Amoy",
  "137": "Polygon Mainnet",
  "1": "Ethereum Mainnet",
};

function showStatus(message, type = "info") {
  const badge = document.createElement("div");
  badge.className = `status-badge status-${type}`;
  badge.textContent = message;
  statusEl.innerHTML = "";
  statusEl.appendChild(badge);
}

function applyNetworkDisplay(chainIdValue) {
  currentChainId = chainIdValue;
  chainIdEl.textContent = currentChainId;
  networkNameEl.textContent = networkNames[currentChainId] || "Unknown Network";
}

function bindProviderEvents() {
  if (!window.ethereum || providerEventsBound) return;
  // Keep UI in sync with MetaMask changes.
  window.ethereum.on("chainChanged", (chainIdHex) => {
    const parsed = parseInt(chainIdHex, 16).toString();
    applyNetworkDisplay(parsed);
    // Full reload guarantees fresh provider/signer/token state.
    window.location.reload();
  });

  window.ethereum.on("accountsChanged", (accounts) => {
    if (!accounts || !accounts.length) {
      wallet = undefined;
      walletEl.textContent = "Not connected";
      signinBtn.disabled = true;
      mintBtn.disabled = true;
      showStatus("Please connect MetaMask", "error");
      return;
    }
    wallet = accounts[0];
    walletEl.textContent = wallet;
    // Token remains tied to the prior account; require fresh sign-in.
    token = undefined;
    signinBtn.disabled = false;
    mintBtn.disabled = true;
    showStatus("Account changed. Please sign in again.", "info");
  });

  providerEventsBound = true;
}

function updateMintPreview() {
  const name = nameInput.value;
  const desc = descInput.value;
  const image = imageInput.value;
  if (name || desc || image) {
    previewName.textContent = name || "(empty)";
    previewDesc.textContent = desc || "(empty)";
    previewImage.textContent = image ? "📷 Provided" : "(none)";
    mintPreview.style.display = "block";
  } else {
    mintPreview.style.display = "none";
  }
}

async function connect() {
  try {
    if (!window.ethereum) {
      showStatus("MetaMask not found", "error");
      return;
    }
    bindProviderEvents();
    provider = new ethers.BrowserProvider(window.ethereum);
    const accounts = await provider.send("eth_requestAccounts", []);
    wallet = accounts[0];
    signer = await provider.getSigner();

    const network = await provider.getNetwork();
    applyNetworkDisplay(network.chainId.toString());
    walletEl.textContent = wallet;
    connectionInfoEl.style.display = "grid";
    signinBtn.disabled = false;
    showStatus("Wallet connected", "connected");
  } catch (err) {
    showStatus(`Error: ${err.message}`, "error");
  }
}

async function signIn() {
  try {
    const nonceResp = await fetch("/auth/nonce", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wallet }),
    });
    const nonceJson = await nonceResp.json();
    const signature = await signer.signMessage(nonceJson.message);
    const verifyResp = await fetch("/auth/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wallet, signature }),
    });
    const verifyJson = await verifyResp.json();
    token = verifyJson.token;
    showStatus("Signed in", "success");
    mintBtn.disabled = false;
    await refreshPoints();
    await loadStore();
  } catch (err) {
    showStatus(`Sign in error: ${err.message}`, "error");
  }
}

async function authFetch(url, options = {}) {
  return fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
}

async function refreshPoints() {
  try {
    const resp = await authFetch("/game/points");
    const json = await resp.json();
    const pts = json.points ?? 0;
    navPointsEl.textContent = `Points: ${pts}`;
  } catch (err) {
    navPointsEl.textContent = "Points: ?";
    console.error("Error refreshing points:", err);
  }
}

function renderStore(items = []) {
  storeGrid.innerHTML = "";
  if (!items.length) {
    storeGrid.innerHTML = "<div style='color:#94a3b8;'>No items available.</div>";
    return;
  }
  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "card";
    card.style.borderColor = item.color || "#1f2937";
    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <h3>${item.name}</h3>
        <span class="badge" style="background:${item.color || '#111827'}; color:#0b1323;">${item.rarity}</span>
      </div>
      <p>${item.description}</p>
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
        <span class="pill pill-amber">${item.price} pts</span>
        <button class="btn-primary" data-item="${item.id}">Buy</button>
      </div>
    `;
    const btn = card.querySelector("button");
    btn.onclick = () => purchaseItem(item.id);
    storeGrid.appendChild(card);
  });
}

async function loadStore() {
  try {
    const resp = await authFetch("/game/store/items");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = await resp.json();
    renderStore(json.items || []);
    storeInfo.textContent = `Wallet: ${json.wallet}`;
  } catch (err) {
    storeInfo.textContent = `Store error: ${err.message}`;
  }
}

async function purchaseItem(itemId) {
  try {
    const resp = await authFetch("/game/store/purchase", {
      method: "POST",
      body: JSON.stringify({ item_id: itemId }),
    });
    const json = await resp.json();
    if (!resp.ok) {
      showStatus(json.detail || "Purchase failed", "error");
      return;
    }
    showStatus(json.message || "Purchased", "success");
    await refreshPoints();
  } catch (err) {
    showStatus(`Purchase error: ${err.message}`, "error");
  }
}

async function mint() {
  try {
    if (!nameInput.value.trim() || !descInput.value.trim()) {
      showStatus("Name and Description are required", "error");
      return;
    }

    mintResult.textContent = "⏳ Minting...";
    const name = nameInput.value;
    const description = descInput.value;
    const image_url = imageInput.value || null;

    const resp = await authFetch("/game/mint", {
      method: "POST",
      body: JSON.stringify({ name, description, image_url }),
    });
    const json = await resp.json();

    if (!resp.ok) {
      mintResult.innerHTML = `<div class="error-box"><strong>Mint Failed:</strong><br>${JSON.stringify(json, null, 2)}</div>`;
      showStatus("Mint failed", "error");
      return;
    }

    const txHash = json.transactionHash || json.tx_hash || "unknown";
    const tokenId = json.tokenId || json.token_id || json.id || "minted";
    mintResult.innerHTML = `
      <div style="color: #34d399;">
        <strong>✅ NFT Minted!</strong><br>
        Token ID: <strong>${tokenId}</strong><br>
        Transaction: <code>${txHash.substring(0, 20)}...</code><br>
        <a href="http://127.0.0.1:8545" class="tx-link">View on Hardhat Node</a>
      </div>`;

    showStatus("Mint successful", "success");
    await refreshPoints();
    nameInput.value = "MLSA Collectible";
    descInput.value = "Unlocked collectible";
    imageInput.value = "";
    updateMintPreview();
  } catch (err) {
    mintResult.innerHTML = `<div class="error-box"><strong>Error:</strong> ${err.message}</div>`;
    showStatus(`Mint error: ${err.message}`, "error");
  }
}

connectBtn.onclick = connect;
signinBtn.onclick = signIn;
mintBtn.onclick = mint;
nameInput.oninput = updateMintPreview;
descInput.oninput = updateMintPreview;
imageInput.oninput = updateMintPreview;

updateMintPreview();
