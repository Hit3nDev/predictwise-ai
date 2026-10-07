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

export const predict = (modelId, rows) =>
  api.post(`/models/${modelId}/predict`, { rows }).then((r) => r.data);

export { detail };

export const getQuestionTemplates = (id) =>
  api.get(`/datasets/${id}/question-templates`).then((r) => r.data);

export const askQuestion = (id, body) =>
  api.post(`/datasets/${id}/ask`, body).then((r) => r.data);

export const chatWithDataset = (id, message, history) =>
  api.post(`/datasets/${id}/chat`, { message, history }).then((r) => r.data);
