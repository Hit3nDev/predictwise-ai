import axios from "axios";

export const api = axios.create({ baseURL: "http://localhost:8000" });

const detail = (err, fallback) =>
  err?.response?.data?.detail || fallback;

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
