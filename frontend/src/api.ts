const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) || DEFAULT_BASE_URL;

async function checkResponse(response: Response): Promise<Response> {
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") {
        message = data.detail;
      }
    } catch {
      try {
        const text = await response.text();
        if (text) {
          message = text;
        }
      } catch {
        /* ignore */
      }
    }
    throw new Error(message);
  }
  return response;
}

export async function encodeText(text: string): Promise<{ blobUrl: string; blob: Blob }> {
  const response = await checkResponse(
    await fetch(`${API_BASE_URL}/encode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    })
  );
  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);
  return { blobUrl, blob };
}

export async function decodeFile(file: File): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await checkResponse(
    await fetch(`${API_BASE_URL}/decode`, {
      method: "POST",
      body: formData,
    })
  );
  return response.text();
}
