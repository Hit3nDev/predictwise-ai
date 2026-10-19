import axios from "axios";

export const api = axios.create({ baseURL: "http://localhost:8000" });

const detail = (err, fallback) => {
  // The backend answered with a specific reason (bad file, bad request, etc.) — use it.
  if (err?.response?.data?.detail) return err.response.data.detail;
  // The request went out but nothing came back — almost always means the
  // backend isn't running, is on the wrong port, or CORS is blocking it.
  // This is NOT the same situation as "the file was bad" and saying so
  // avoids sending someone down the wrong troubleshooting path entirely.
  if (err?.request) {
    return "Can't reach the backend server. Make sure it's running (uvicorn main:app --reload) at http://localhost:8000.";
  }
  return fallback;
};

export async function uploadDataset(file) {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await api.post("/upload", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export const listDatasets = () => api.get("/datasets").then((r) => r.data);

export const cleanDataset = (id, options) =>
  api.post(`/datasets/${id}/clean`, options).then((r) => r.data);

export const getEDA = (id, useCleaned = true) =>
  api.get(`/datasets/${id}/eda`, { params: { use_cleaned: useCleaned } }).then((r) => r.data);

export const trainModels = (id, body) =>
  api.post(`/datasets/${id}/train`, body).then((r) => r.data);

export const predict = (modelId, rows, explain = true) =>
  api.post(`/models/${modelId}/predict`, { rows, explain }).then((r) => r.data);

export const whatIf = (modelId, row, feature, targetClass) =>
  api.post(`/models/${modelId}/whatif`, { row, feature, target_class: targetClass ?? null }).then((r) => r.data);

export const fairnessOptions = (modelId) =>
  api.get(`/models/${modelId}/fairness/options`).then((r) => r.data.columns);

export const runFairness = (modelId, group) =>
  api.get(`/models/${modelId}/fairness`, { params: { group } }).then((r) => r.data);

export const getMonitoring = (modelId) =>
  api.get(`/models/${modelId}/monitoring`).then((r) => r.data);

// A plain URL, not an API call: the report is a page you open, print or save as PDF.
export const reportUrl = (modelId, audience = "simple", group = "") =>
  `${api.defaults.baseURL}/models/${modelId}/report?audience=${audience}${group ? `&group=${encodeURIComponent(group)}` : ""}`;

export { detail };

export const getQuestionTemplates = (id) =>
  api.get(`/datasets/${id}/question-templates`).then((r) => r.data);

export const askQuestion = (id, body) =>
  api.post(`/datasets/${id}/ask`, body).then((r) => r.data);

export const chatWithDataset = (id, message, history, lang = "en", priv = false, shop = "") =>
  api.post(`/datasets/${id}/chat`, { message, history, lang, private: priv, shop }).then((r) => r.data);

export const getToolkit = (id) => api.get(`/datasets/${id}/toolkit`).then((r) => r.data);

export const getPlaybook = (id) => api.get(`/datasets/${id}/playbook`).then((r) => r.data);

export const llmStatus = () => api.get("/health/llm").then((r) => r.data);

/* ---- insights ---- */
export const listSamples = () => api.get("/samples").then((r) => r.data);
export const loadSample = (name) => api.post(`/samples/${name}/load`).then((r) => r.data);
export const getBriefing = (id) => api.get(`/datasets/${id}/briefing`).then((r) => r.data);
export const getTrend = (id, params = {}) => api.get(`/datasets/${id}/trend`, { params }).then((r) => r.data);
export const getSegments = (id) => api.get(`/datasets/${id}/segments`).then((r) => r.data);
export const getAnomalies = (id) => api.get(`/datasets/${id}/anomalies`).then((r) => r.data);

/* ---- actions ---- */
export const rankRows = (modelId, top = 10, direction = "most") =>
  api.get(`/models/${modelId}/rank`, { params: { top, direction } }).then((r) => r.data);
export const getLevers = (modelId, row) =>
  api.post(`/models/${modelId}/levers`, { row }).then((r) => r.data.levers);
export const scoreFile = (modelId, file) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post(`/models/${modelId}/score-file`, fd).then((r) => r.data);
};

/* Downloads need the file's bytes, so fetch as a blob and hand it to the browser. */
const saveBlob = (blob, name) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
export const downloadCleaned = async (id, fileName = "data") => {
  const r = await api.get(`/datasets/${id}/download`, { responseType: "blob" });
  saveBlob(r.data, fileName.replace(/\.[^.]+$/, "") + "_cleaned.csv");
};
export const downloadScored = async (modelId, file) => {
  const fd = new FormData();
  fd.append("file", file);
  const r = await api.post(`/models/${modelId}/score-file`, fd, { params: { format: "csv" }, responseType: "blob" });
  saveBlob(r.data, file.name.replace(/\.[^.]+$/, "") + "_scored.csv");
};

export const getDigest = (id) => api.get(`/datasets/${id}/digest`).then((r) => r.data);
export const compareFiles = (id, otherId) => api.get(`/datasets/${id}/compare/${otherId}`).then((r) => r.data);
