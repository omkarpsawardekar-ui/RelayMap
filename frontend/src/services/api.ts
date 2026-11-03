import axios from "axios";

const TOKEN_KEY = "relaymap_access_token";

export function getAccessToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAccessToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    throw new Error("Unable to save your login session in this browser.");
  }
}

export function clearAccessToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Nothing else is needed if browser storage is unavailable.
  }
}

export const api = axios.create({
  baseURL:
    import.meta.env.VITE_API_BASE_URL ||
    "http://127.0.0.1:8000",
  timeout: 30000,
});

// Attach the saved JWT to every API request.
api.interceptors.request.use((config) => {
  const token = getAccessToken();

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

// Clear an expired or invalid session when the backend rejects it.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && getAccessToken()) {
      clearAccessToken();

      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("relaymap:auth-expired"));
      }
    }

    return Promise.reject(error);
  }
);

export function getApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;

    if (typeof detail === "string") {
      return detail;
    }

    if (detail !== undefined) {
      return JSON.stringify(detail);
    }

    return error.message || "Unable to reach the server.";
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected error occurred.";
}