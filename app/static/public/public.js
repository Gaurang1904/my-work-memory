const thread = document.getElementById("chat-thread");
const questionInput = document.getElementById("public-question");
const reportPanel = document.getElementById("report-panel");
const chatHistory = [];

const MAX_HISTORY_MESSAGES = 6;

function addUserMessage(text) {
  const wrapper = document.createElement("article");
  wrapper.className = "message user";
  wrapper.innerHTML = `<div class="bubble"><p>${escapeHtml(text)}</p></div>`;
  thread.appendChild(wrapper);
  scrollThread();
}

function addAssistantStatus(label) {
  const wrapper = document.createElement("article");
  wrapper.className = "message assistant";
  wrapper.innerHTML = `
    <div class="assistant-block">
      <div class="bubble">
        <span class="status-inline">${escapeHtml(label)}</span>
        <p>Working on response...</p>
      </div>
    </div>
  `;
  thread.appendChild(wrapper);
  scrollThread();
  return wrapper;
}

function replaceWithAnswer(node, payload) {
  node.innerHTML = `
    <div class="assistant-block">
      <div class="bubble">
        <h3>Answer</h3>
        <div class="answer-text">${formatAnswerText(payload.answer || "No answer returned.")}</div>
      </div>
    </div>
  `;
  scrollThread();
}

function replaceWithReport(node, payload) {
  node.innerHTML = `
    <div class="assistant-block">
      <div class="bubble">
        <h3>${escapeHtml(payload.title || "Generated report")}</h3>
        <div class="answer-text">${formatAnswerText(payload.report || "No report returned.")}</div>
      </div>
    </div>
  `;
  scrollThread();
}

function replaceWithError(node, title, message) {
  node.innerHTML = `
    <div class="assistant-block">
      <div class="bubble error-box">
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(message)}</p>
      </div>
    </div>
  `;
  scrollThread();
}

async function publicRequest(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();

  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }

  if (!response.ok) {
    throw new Error(payload.detail || payload.error || payload.raw || `Request failed with status ${response.status}`);
  }

  return payload;
}

document.getElementById("toggle-report").addEventListener("click", () => {
  reportPanel.classList.toggle("hidden");
});

document.getElementById("public-ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question) {
    return;
  }

  addUserMessage(question);
  appendHistory("user", question);
  questionInput.value = "";
  const statusNode = addAssistantStatus("Searching reports");

  try {
    const payload = await publicRequest("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: buildHistoryForRequest() }),
    });
    replaceWithAnswer(statusNode, payload);
    appendHistory("assistant", payload.answer || "");
  } catch (error) {
    replaceWithError(statusNode, "Question failed", error.message);
  }
});

document.getElementById("public-report-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const reportType = document.getElementById("public-report-type").value.trim();
  const topic = document.getElementById("public-report-topic").value.trim();
  if (!reportType || !topic) {
    return;
  }

  addUserMessage(`Generate report: ${topic}`);
  const statusNode = addAssistantStatus("Generating report");

  try {
    const payload = await publicRequest("/generate-report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report_type: reportType, topic }),
    });
    replaceWithReport(statusNode, payload);
  } catch (error) {
    replaceWithError(statusNode, "Report failed", error.message);
  }
});

document.querySelectorAll(".preset-question").forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.question || "";
    questionInput.focus();
  });
});

function scrollThread() {
  thread.scrollTop = thread.scrollHeight;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatAnswerText(value) {
  const lines = String(value).split("\n");
  let html = "";
  let inList = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      continue;
    }

    if (line.startsWith("- ")) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${escapeHtml(line.slice(2))}</li>`;
      continue;
    }

    if (inList) {
      html += "</ul>";
      inList = false;
    }

    html += `<p>${escapeHtml(line)}</p>`;
  }

  if (inList) {
    html += "</ul>";
  }

  return html;
}

function appendHistory(role, content) {
  chatHistory.push({ role, content });
  if (chatHistory.length > MAX_HISTORY_MESSAGES) {
    chatHistory.splice(0, chatHistory.length - MAX_HISTORY_MESSAGES);
  }
}

function buildHistoryForRequest() {
  return chatHistory.slice(0, -1);
}
