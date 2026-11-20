/**
 * Helpbox Clinical Trial PDF Workspace Client
 */

(function () {
  "use strict";

  // Application State
  const state = {
    trials: [],
    selectedTrial: null,
    activeTab: "overview",
    documents: [],
    trialStatus: null,
    chatHistory: [], // In-memory only; cleared on trial switch or new chat
  };

  // DOM Elements
  const elements = {
    trialList: document.getElementById("trial-list"),
    trialSearch: document.getElementById("trial-search"),
    btnRefreshTrials: document.getElementById("btn-refresh-trials"),
    noTrialSelected: document.getElementById("no-trial-selected"),
    trialWorkspace: document.getElementById("trial-workspace"),
    breadcrumbTrialName: document.getElementById("breadcrumb-trial-name"),
    selectedTrialTitle: document.getElementById("selected-trial-title"),
    trialStatusPill: document.getElementById("trial-status-pill"),
    btnRescanTrial: document.getElementById("btn-rescan-trial"),
    tabButtons: document.querySelectorAll(".tab-btn"),
    tabDocCount: document.getElementById("tab-doc-count"),
    // Overview elements
    metaFolderName: document.getElementById("meta-folder-name"),
    metaPdfCount: document.getElementById("meta-pdf-count"),
    summaryDiscovered: document.getElementById("summary-discovered"),
    summaryReady: document.getElementById("summary-ready"),
    // Documents elements
    documentsTableBody: document.getElementById("documents-table-body"),
    // Assistant elements
    stripTrialName: document.getElementById("strip-trial-name"),
    stripStatusText: document.getElementById("strip-status-text"),
    btnNewChat: document.getElementById("btn-new-chat"),
    btnRefreshAssistant: document.getElementById("btn-refresh-assistant"),
    chatTranscript: document.getElementById("chat-transcript"),
    chatForm: document.getElementById("chat-form"),
    chatInput: document.getElementById("chat-input"),
    btnSendChat: document.getElementById("btn-send-chat"),
  };

  // Format bytes to human readable string
  function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  // Format ISO timestamp
  function formatDateTime(isoStr) {
    if (!isoStr) return "—";
    try {
      const d = new Date(isoStr);
      return d.toISOString().replace("T", " ").substring(0, 19);
    } catch {
      return isoStr;
    }
  }

  // Fetch trial folders from server
  async function loadTrials() {
    try {
      elements.trialList.innerHTML = '<li class="empty-state-item">Scanning trial folders...</li>';
      const res = await fetch("/api/trials");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.trials = data.trials || [];
      renderTrialList(state.trials);

      // If current selected trial is no longer in list, deselect
      if (state.selectedTrial && !state.trials.includes(state.selectedTrial)) {
        deselectTrial();
      }
    } catch (err) {
      elements.trialList.innerHTML = `<li class="empty-state-item">Error loading trials: ${err.message}</li>`;
    }
  }

  // Render trial list in sidebar
  function renderTrialList(trials) {
    if (!trials.length) {
      elements.trialList.innerHTML = '<li class="empty-state-item">No trial folders found in data/trials/</li>';
      return;
    }

    elements.trialList.innerHTML = "";
    trials.forEach((trialName) => {
      const li = document.createElement("li");
      li.className = `trial-list-item ${state.selectedTrial === trialName ? "active" : ""}`;
      li.dataset.trial = trialName;

      const spanName = document.createElement("span");
      spanName.textContent = trialName;

      li.appendChild(spanName);
      li.addEventListener("click", () => selectTrial(trialName));
      elements.trialList.appendChild(li);
    });
  }

  // Deselect trial
  function deselectTrial() {
    state.selectedTrial = null;
    state.chatHistory = [];
    elements.noTrialSelected.classList.remove("hidden");
    elements.trialWorkspace.classList.add("hidden");
    renderTrialList(state.trials);
  }

  // Select a trial and load its workspace
  async function selectTrial(trialName) {
    // If switching trial, immediately clear chat history and active conversation
    if (state.selectedTrial !== trialName) {
      state.selectedTrial = trialName;
      state.chatHistory = [];
      resetChatTranscript(trialName);
    }

    elements.breadcrumbTrialName.textContent = trialName;
    elements.selectedTrialTitle.textContent = trialName;
    elements.metaFolderName = trialName;

    elements.noTrialSelected.classList.add("hidden");
    elements.trialWorkspace.classList.remove("hidden");

    renderTrialList(state.trials);

    // Fetch documents and status for this trial
    await loadTrialData(trialName);

    // Switch to current active tab
    switchTab(state.activeTab);
  }

  // Load trial documents and status
  async function loadTrialData(trialName) {
    try {
      elements.trialStatusPill.className = "status-pill pill-neutral";
      elements.trialStatusPill.textContent = "Scanning";

      const [docsRes, statusRes] = await Promise.all([
        fetch(`/api/trials/${encodeURIComponent(trialName)}/documents`),
        fetch(`/api/trials/${encodeURIComponent(trialName)}/status`),
      ]);

      if (!docsRes.ok) throw new Error(`Documents HTTP ${docsRes.status}`);
      if (!statusRes.ok) throw new Error(`Status HTTP ${statusRes.status}`);

      const docsData = await docsRes.json();
      const statusData = await statusRes.json();

      state.documents = docsData.documents || [];
      state.trialStatus = statusData;

      renderOverview(trialName, state.documents, state.trialStatus);
      renderDocuments(state.documents);
      updateAssistantStrip(trialName, state.documents, state.trialStatus);
    } catch (err) {
      elements.trialStatusPill.className = "status-pill pill-neutral";
      elements.trialStatusPill.textContent = "Error";
      console.error("Failed to load trial data:", err);
    }
  }

  // Render Overview Tab
  function renderOverview(trialName, documents, trialStatus) {
    const metaFolder = document.getElementById("meta-folder-name");
    if (metaFolder) metaFolder.textContent = trialName;
    if (elements.metaPdfCount) elements.metaPdfCount.textContent = documents.length;
    if (elements.tabDocCount) elements.tabDocCount.textContent = documents.length;

    if (elements.summaryDiscovered) elements.summaryDiscovered.textContent = documents.length;
    if (elements.summaryReady) elements.summaryReady.textContent = trialStatus.ready_documents || 0;

    if (documents.length === 0) {
      elements.trialStatusPill.className = "status-pill pill-neutral";
      elements.trialStatusPill.textContent = "Empty";
    } else {
      elements.trialStatusPill.className = "status-pill pill-ready";
      elements.trialStatusPill.textContent = `${documents.length} PDF${documents.length > 1 ? "s" : ""}`;
    }
  }

  // Render Documents Tab Table
  function renderDocuments(documents) {
    if (!documents.length) {
      elements.documentsTableBody.innerHTML =
        '<tr><td colspan="4" class="empty-cell">No PDF documents placed in this trial folder yet.</td></tr>';
      return;
    }

    elements.documentsTableBody.innerHTML = "";
    documents.forEach((doc) => {
      const tr = document.createElement("tr");

      const tdName = document.createElement("td");
      tdName.textContent = doc.filename;
      tdName.style.fontWeight = "600";

      const tdSize = document.createElement("td");
      tdSize.textContent = formatBytes(doc.size_bytes);

      const tdTime = document.createElement("td");
      tdTime.textContent = formatDateTime(doc.modified_at);

      const tdStatus = document.createElement("td");
      tdStatus.textContent = doc.status || "DISCOVERED";

      tr.appendChild(tdName);
      tr.appendChild(tdSize);
      tr.appendChild(tdTime);
      tr.appendChild(tdStatus);
      elements.documentsTableBody.appendChild(tr);
    });
  }

  // Update AI Assistant Context Strip
  function updateAssistantStrip(trialName, documents, trialStatus) {
    if (elements.stripTrialName) elements.stripTrialName.textContent = trialName;
    if (elements.stripStatusText) {
      if (documents.length === 0) {
        elements.stripStatusText.textContent = "No PDFs in this trial folder";
      } else {
        const readyCount = trialStatus ? trialStatus.ready_documents : 0;
        elements.stripStatusText.textContent = `${documents.length} source PDF${documents.length > 1 ? "s" : ""} detected (${readyCount} indexed)`;
      }
    }
  }

  // Switch workspace tab
  function switchTab(tabKey) {
    state.activeTab = tabKey;

    // Update tab button styles
    elements.tabButtons.forEach((btn) => {
      const isTarget = btn.dataset.tab === tabKey;
      btn.classList.toggle("active", isTarget);
      btn.setAttribute("aria-selected", isTarget ? "true" : "false");
    });

    // Update panel visibility
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      const isTarget = panel.id === `tab-${tabKey}`;
      panel.classList.toggle("hidden", !isTarget);
      panel.classList.toggle("active", isTarget);
    });

    // Specific behavior when opening AI Assistant tab
    if (tabKey === "assistant" && state.selectedTrial) {
      onOpenAssistantTab(state.selectedTrial);
    }
  }

  // Assistant tab open handler: runs incremental refresh check and updates vectors state
  async function onOpenAssistantTab(trialName) {
    try {
      if (elements.stripStatusText) {
        elements.stripStatusText.textContent = "Verifying document hashes and index...";
      }

      const res = await fetch(`/api/trials/${encodeURIComponent(trialName)}/refresh`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.documents = data.documents || [];

      updateAssistantStrip(trialName, state.documents, state.trialStatus);
    } catch (err) {
      if (elements.stripStatusText) {
        elements.stripStatusText.textContent = `Refresh check: ${err.message}`;
      }
    }
  }

  // Reset chat transcript for a trial
  function resetChatTranscript(trialName) {
    elements.chatTranscript.innerHTML = `
      <div class="system-message">
        <div class="system-bubble">
          <p><strong>Trial Assistant Active for ${escapeHtml(trialName)}.</strong></p>
          <p>Questions asked here are answered strictly using documents belonging to this trial. Switching trials will clear the visible chat and redirect retrieval scope.</p>
        </div>
      </div>
    `;
  }

  // Escape HTML helper
  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Append a chat message to the transcript
  function appendChatMessage(role, content, citations, metrics) {
    const turnDiv = document.createElement("div");
    turnDiv.className = `chat-turn ${role}`;

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    const contentDiv = document.createElement("div");
    contentDiv.className = "bubble-text";
    contentDiv.textContent = content;
    bubble.appendChild(contentDiv);

    // If citations present, render citations block
    if (citations && citations.length > 0) {
      renderCitationsBox(bubble, citations);
    }

    if (metrics && metrics.total_response_ms) {
      renderMetricsStrip(bubble, metrics);
    }

    turnDiv.appendChild(bubble);
    elements.chatTranscript.appendChild(turnDiv);
    elements.chatTranscript.scrollTop = elements.chatTranscript.scrollHeight;
    return { turnDiv, bubble, contentDiv };
  }

  function renderCitationsBox(container, citations) {
    const citeBox = document.createElement("div");
    citeBox.className = "citations-box";

    const citeHeader = document.createElement("div");
    citeHeader.className = "citations-header";
    citeHeader.textContent = "Source Evidence Citations";
    citeBox.appendChild(citeHeader);

    citations.forEach((cite) => {
      const item = document.createElement("div");
      item.className = "citation-item";

      const meta = document.createElement("div");
      meta.className = "citation-meta";
      meta.textContent = `[${cite.id}] ${cite.filename} — Page ${cite.page}`;
      item.appendChild(meta);

      if (cite.excerpt) {
        const excerpt = document.createElement("div");
        excerpt.className = "citation-excerpt";
        excerpt.textContent = `"${cite.excerpt}"`;
        item.appendChild(excerpt);
      }

      citeBox.appendChild(item);
    });

    container.appendChild(citeBox);
  }

  function renderMetricsStrip(container, metrics) {
    const details = document.createElement("details");
    details.className = "performance-details";

    const totalSec = (metrics.total_response_ms / 1000).toFixed(2);
    const summary = document.createElement("summary");
    summary.className = "performance-summary";
    summary.innerHTML = `Performance Details — Total: ${totalSec}s | Retrieval: ${metrics.retrieval_ms || 0}ms | Model: ${metrics.model || "default"}`;
    details.appendChild(summary);

    const body = document.createElement("div");
    body.className = "performance-body";

    const addRow = (label, val) => {
      const row = document.createElement("div");
      row.className = "perf-row";
      row.innerHTML = `<span class="perf-label">${label}:</span> <span class="perf-val">${val}</span>`;
      body.appendChild(row);
    };

    addRow("LLM Provider / Model", `${metrics.provider || "ollama"} / ${metrics.model || "qwen3.5:2b-q4_K_M"}`);
    if (metrics.query_embedding_ms !== undefined) {
      addRow("Query Embedding Time", `${metrics.query_embedding_ms} ms`);
    }
    if (metrics.vector_search_ms !== undefined) {
      addRow("pgvector Cosine Search", `${metrics.vector_search_ms} ms`);
    }
    addRow("Total Retrieval Latency", `${metrics.retrieval_ms || 0} ms (${metrics.chunks_retrieved || 0} chunks)`);
    if (metrics.first_token_ms) {
      addRow("Time to First Token", `${(metrics.first_token_ms / 1000).toFixed(2)} s`);
    }
    if (metrics.generation_ms) {
      addRow("Generation Duration", `${(metrics.generation_ms / 1000).toFixed(2)} s`);
    }
    if (metrics.tokens_per_second) {
      addRow("Generation Throughput", `${metrics.tokens_per_second} tok/s (${metrics.token_count || 0} tokens)`);
    }
    addRow("Total Roundtrip Time", `${totalSec} s`);

    details.appendChild(body);
    container.appendChild(details);
  }

  // Submit chat question with real-time SSE streaming
  async function submitChat(e) {
    e.preventDefault();
    const question = elements.chatInput.value.trim();
    if (!question || !state.selectedTrial) return;

    elements.chatInput.value = "";
    elements.btnSendChat.disabled = true;

    // Display user question
    appendChatMessage("user", question, null);
    state.chatHistory.push({ role: "user", content: question });

    // Create assistant streaming placeholder
    const turnDiv = document.createElement("div");
    turnDiv.className = "chat-turn assistant";

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    const contentDiv = document.createElement("div");
    contentDiv.className = "bubble-text";

    const cursor = document.createElement("span");
    cursor.className = "typing-cursor";

    bubble.appendChild(contentDiv);
    bubble.appendChild(cursor);
    turnDiv.appendChild(bubble);
    elements.chatTranscript.appendChild(turnDiv);
    elements.chatTranscript.scrollTop = elements.chatTranscript.scrollHeight;

    let fullAnswer = "";
    let finalCitations = [];
    let finalMetrics = null;

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trial_name: state.selectedTrial,
          question: question,
          chat_history: state.chatHistory.slice(-4),
        }),
      });

      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            try {
              const event = JSON.parse(trimmed.slice(6));
              if (event.type === "token") {
                fullAnswer += event.content;
                contentDiv.textContent = fullAnswer;
                elements.chatTranscript.scrollTop = elements.chatTranscript.scrollHeight;
              } else if (event.type === "done") {
                fullAnswer = event.answer || fullAnswer;
                contentDiv.textContent = fullAnswer;
                finalCitations = event.citations || [];
                finalMetrics = event.metrics || null;
              }
            } catch (err) {
              console.warn("Error parsing SSE event:", err);
            }
          }
        }
      }

      // Remove typing cursor
      if (cursor.parentNode) cursor.remove();

      // Render citations & metrics
      if (finalCitations && finalCitations.length > 0) {
        renderCitationsBox(bubble, finalCitations);
      }
      if (finalMetrics) {
        renderMetricsStrip(bubble, finalMetrics);
      }

      state.chatHistory.push({ role: "assistant", content: fullAnswer });
      elements.chatTranscript.scrollTop = elements.chatTranscript.scrollHeight;

    } catch (err) {
      if (cursor.parentNode) cursor.remove();
      contentDiv.textContent = `Unable to complete request: ${err.message}`;
    } finally {
      elements.btnSendChat.disabled = false;
      elements.chatInput.focus();
    }
  }

  // Event Listeners
  elements.btnRefreshTrials.addEventListener("click", loadTrials);

  elements.trialSearch.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    const filtered = state.trials.filter((t) => t.toLowerCase().includes(q));
    renderTrialList(filtered);
  });

  elements.tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  elements.btnRescanTrial.addEventListener("click", () => {
    if (state.selectedTrial) loadTrialData(state.selectedTrial);
  });

  elements.btnRefreshAssistant.addEventListener("click", () => {
    if (state.selectedTrial) onOpenAssistantTab(state.selectedTrial);
  });

  elements.btnNewChat.addEventListener("click", () => {
    if (state.selectedTrial) {
      state.chatHistory = [];
      resetChatTranscript(state.selectedTrial);
    }
  });

  elements.chatForm.addEventListener("submit", submitChat);

  // Keyboard shortcut: Ctrl+Enter to submit
  elements.chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      elements.chatForm.requestSubmit();
    }
  });

  // Continuous sync status checker
  async function checkSyncStatus() {
    try {
      const res = await fetch("/api/sync/status");
      if (!res.ok) return;
      const data = await res.json();
      const badge = document.getElementById("sync-badge");
      if (!badge) return;
      if (data.enabled && data.is_running) {
        badge.className = "sync-badge sync-active";
        badge.textContent = `Sync: Active (${data.interval_seconds}s)`;
        badge.title = `Continuous background scanner active. Cycles completed: ${data.scan_count}`;
      } else {
        badge.className = "sync-badge sync-inactive";
        badge.textContent = "Sync: Idle";
        badge.title = "Continuous synchronization is inactive.";
      }
    } catch {
      // Ignore network errors
    }
  }

  // Quiet background polling to update UI when background scanner indexes new/deleted files
  setInterval(async () => {
    if (state.selectedTrial) {
      try {
        const [docsRes, statusRes] = await Promise.all([
          fetch(`/api/trials/${encodeURIComponent(state.selectedTrial)}/documents`),
          fetch(`/api/trials/${encodeURIComponent(state.selectedTrial)}/status`),
        ]);
        if (docsRes.ok && statusRes.ok) {
          const docsData = await docsRes.json();
          const statusData = await statusRes.json();
          const newDocs = docsData.documents || [];
          const oldSign = state.documents.map((d) => `${d.filename}:${d.sha256}:${d.status}`).join(",");
          const newSign = newDocs.map((d) => `${d.filename}:${d.sha256}:${d.status}`).join(",");
          if (oldSign !== newSign) {
            state.documents = newDocs;
            state.trialStatus = statusData;
            renderOverview(state.selectedTrial, state.documents, state.trialStatus);
            renderDocuments(state.documents);
            updateAssistantStrip(state.selectedTrial, state.documents, state.trialStatus);
          }
        }
      } catch {
        // Quietly ignore background poll errors
      }
    }
  }, 15000);

  // Initial load
  loadTrials();
  checkSyncStatus();
  setInterval(checkSyncStatus, 25000);
})();
