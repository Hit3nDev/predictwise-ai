import axios from "axios";

const API_BASE_URL = "http://localhost:8000";

export const api = axios.create({ baseURL: API_BASE_URL });

export async function uploadDataset(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await api.post("/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function listDatasets() {
  const res = await api.get("/datasets");
  return res.data;
}

export async function cleanDataset(id, options) {
  const res = await api.post(`/datasets/${id}/clean`, options);
  return res.data;
}

export async function getEDA(id, useCleaned = true) {
  const res = await api.get(`/datasets/${id}/eda`, {
    params: { use_cleaned: useCleaned },
  });
  return res.data;
}
