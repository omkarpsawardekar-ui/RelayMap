import axios from "axios";

export const api = axios.create({
  baseURL:
    import.meta.env.VITE_API_BASE_URL ||
    "http://127.0.0.1:8000",

  // Do not set Content-Type globally.
  // Axios automatically handles JSON and FormData requests.

  timeout: 30000,
});

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

  return "An unexpected error occurred.";
}