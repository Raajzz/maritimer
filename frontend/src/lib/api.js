// Thin fetch wrapper (ARCHITECTURE.md §4). Adds the bearer token, unwraps the API error envelope.
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/$/, "");

let tokenProvider = async () => null;
let onNotApproved = () => {};

export function setTokenProvider(fn) {
  tokenProvider = fn;
}

export function setNotApprovedHandler(fn) {
  onNotApproved = fn;
}

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details || {};
  }

  // Flatten DRF field errors into readable lines.
  get fieldMessages() {
    const out = [];
    const walk = (value, prefix) => {
      if (Array.isArray(value)) value.forEach((v) => (typeof v === "string" ? out.push(prefix ? `${prefix}: ${v}` : v) : walk(v, prefix)));
      else if (value && typeof value === "object") Object.entries(value).forEach(([k, v]) => walk(v, prefix ? `${prefix}.${k}` : k));
      else if (value != null) out.push(prefix ? `${prefix}: ${value}` : String(value));
    };
    walk(this.details, "");
    return out;
  }
}

export async function request(path, { method = "GET", body, form, raw = false, signal } = {}) {
  const headers = { Accept: "application/json" };
  const token = await tokenProvider();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) {
    payload = new FormData();
    Object.entries(form).forEach(([k, v]) => v !== undefined && v !== null && payload.append(k, v));
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { method, headers, body: payload, signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "Cannot reach the server. Check your connection and try again.");
  }
  if (raw && res.ok) return res;
  if (res.status === 204) return null;
  const isJson = (res.headers.get("Content-Type") || "").includes("application/json");
  const data = isJson ? await res.json() : null;
  if (!res.ok) {
    const err = data?.error || {};
    const apiError = new ApiError(res.status, err.code || "error", err.message || `Request failed (${res.status})`, err.details);
    if (apiError.code === "not_approved") onNotApproved(apiError.details);
    throw apiError;
  }
  return data;
}

export const api = {
  get: (path, opts) => request(path, opts),
  post: (path, body) => request(path, { method: "POST", body: body ?? {} }),
  put: (path, body) => request(path, { method: "PUT", body }),
  patch: (path, body) => request(path, { method: "PATCH", body }),
  del: (path) => request(path, { method: "DELETE" }),
  upload: (path, form) => request(path, { method: "POST", form }),
};

export function qs(params) {
  const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}

// PDFs (PROGRESS.md C8): cached documents come back as JSON {file}, previews as application/pdf bytes.
// The window is opened synchronously so popup blockers allow it.
export async function openDocument(path) {
  const win = window.open("", "_blank");
  try {
    const res = await request(`${path}${path.includes("?") ? "&" : "?"}redirect=false`, { raw: true });
    const type = res.headers.get("Content-Type") || "";
    if (type.includes("application/json")) {
      const data = await res.json();
      const url = data.file?.download_url || data.download_url;
      if (win) win.location = url;
      else window.location.assign(url);
    } else {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      if (win) win.location = url;
      else window.location.assign(url);
    }
  } catch (err) {
    if (win) win.close();
    throw err;
  }
}

export function openFile(fileRef) {
  if (fileRef?.download_url) window.open(fileRef.download_url, "_blank", "noopener");
}
