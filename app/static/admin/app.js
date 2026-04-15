const output = document.getElementById("output");
const repoFilesContainer = document.getElementById("repo-files");

function renderOutput(label, payload) {
  output.textContent = `${label}\n\n${JSON.stringify(payload, null, 2)}`;
}

function appendOutput(label, payload) {
  output.textContent = `${output.textContent}\n\n${label}\n\n${JSON.stringify(payload, null, 2)}`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }

  if (!response.ok) {
    if (response.status === 401) {
      window.location.href = "/admin/login";
    }
    throw new Error(payload.detail || payload.raw || `Request failed with status ${response.status}`);
  }

  return payload;
}

async function loadRepoFiles() {
  repoFilesContainer.innerHTML = "<p class='muted'>Loading repo files...</p>";
  try {
    const files = await requestJson("/upload/repo-files");
    if (!files.length) {
      repoFilesContainer.innerHTML = "<p class='muted'>No supported files found in project-data/raw yet.</p>";
      return;
    }

    repoFilesContainer.innerHTML = "";
    files.forEach((file) => {
      const card = document.createElement("div");
      card.className = "repo-file";
      card.innerHTML = `
        <h3>${file.file_name}</h3>
        <p>${file.relative_path}</p>
        <p>${file.source_type.toUpperCase()} • ${file.size_bytes.toLocaleString()} bytes</p>
        <button type="button">Ingest This File</button>
      `;

      card.querySelector("button").addEventListener("click", async () => {
        try {
          renderOutput("Ingesting local file...", { file_name: file.file_name });
          const payload = await requestJson("/upload/ingest-local", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ file_name: file.file_name }),
          });
          appendOutput("Local ingest success", payload);
        } catch (error) {
          renderOutput("Local ingest failed", { error: error.message });
        }
      });

      repoFilesContainer.appendChild(card);
    });
  } catch (error) {
    repoFilesContainer.innerHTML = `<p class="muted">Failed to load repo files: ${error.message}</p>`;
  }
}

document.getElementById("refresh-files").addEventListener("click", loadRepoFiles);
document.getElementById("clear-output").addEventListener("click", () => {
  output.textContent = "Ready.";
});

document.getElementById("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);

  try {
    renderOutput("Uploading file...", { file: form.get("file")?.name || null });
    const response = await fetch("/upload", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Upload failed");
    }
    appendOutput("Upload success", payload);
    event.currentTarget.reset();
  } catch (error) {
    renderOutput("Upload failed", { error: error.message });
  }
});

document.getElementById("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = document.getElementById("question").value.trim();
  if (!question) {
    return;
  }

  try {
    renderOutput("Asking question...", { question });
    const payload = await requestJson("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    appendOutput("Answer", payload);
  } catch (error) {
    renderOutput("Question failed", { error: error.message });
  }
});

document.getElementById("report-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const reportType = document.getElementById("report-type").value.trim();
  const topic = document.getElementById("report-topic").value.trim();
  if (!reportType || !topic) {
    return;
  }

  try {
    renderOutput("Generating report...", { report_type: reportType, topic });
    const payload = await requestJson("/generate-report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report_type: reportType, topic }),
    });
    appendOutput("Report", payload);
  } catch (error) {
    renderOutput("Report generation failed", { error: error.message });
  }
});

loadRepoFiles();
