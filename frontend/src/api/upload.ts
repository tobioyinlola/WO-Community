import { api } from "./client";

export type UploadPurpose = "support_attachment" | "course_cover" | "cert_signature";

export interface Uploaded {
  id: string;
  name: string;
  size: number;
}

/** Why a file was turned away, in words a person can act on. */
const REJECTIONS: Record<string, string> = {
  malware_detected: "was blocked because it may contain a virus.",
  type_mismatch: "is not the kind of file its name says.",
  type_not_allowed: "is not an allowed type.",
  corrupt: "could not be read.",
  active_content: "contains something we cannot accept.",
  encrypted: "is password protected.",
  too_large: "is too large.",
  size_mismatch: "did not arrive complete.",
};

export class UploadError extends Error {}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Sends one file through the three steps the API asks for: reserve it, post it straight to storage,
 * then say it has arrived and wait until it has been checked. Resolves with the id to attach.
 */
export async function uploadFile(file: File, purpose: UploadPurpose, pollMs = 700, maxPolls = 40): Promise<Uploaded> {
  const label = `“${file.name}”`;
  const reserved = await api.POST("/api/v1/uploads", {
    body: { purpose, content_type: file.type, size: file.size, filename: file.name },
  });
  if (reserved.error || !reserved.data) {
    const detail = (reserved.error as { detail?: string } | undefined)?.detail;
    throw new UploadError(detail ? `${label}: ${detail}` : `We could not start uploading ${label}.`);
  }
  const { upload, form } = reserved.data;

  let sent: Response;
  try {
    if (form.method === "PUT") {
      // Storage that cannot take a form (Cloudflare R2): the file is the whole request body.
      sent = await fetch(form.url, { method: "PUT", headers: form.headers, body: file });
    } else {
      const data = new FormData();
      for (const [key, value] of Object.entries(form.form_data)) data.append(key, value);
      data.append("file", file); // the file must be the last field
      sent = await fetch(form.url, { method: "POST", body: data });
    }
  } catch {
    throw new UploadError(`We could not upload ${label}. Check your connection and try again.`);
  }
  if (!sent.ok) throw new UploadError(`We could not upload ${label}. Try again.`);

  const done = await api.POST("/api/v1/uploads/{upload_id}/complete", { params: { path: { upload_id: upload.id } } });
  if (done.error) throw new UploadError(`We could not finish uploading ${label}.`);

  for (let attempt = 0; attempt < maxPolls; attempt += 1) {
    const checked = await api.GET("/api/v1/uploads/{upload_id}", { params: { path: { upload_id: upload.id } } });
    const state = checked.data;
    if (state?.status === "ready") return { id: upload.id, name: file.name, size: file.size };
    if (state?.status === "rejected") {
      throw new UploadError(`${label} ${REJECTIONS[state.reason] ?? "was not accepted."}`);
    }
    await wait(pollMs);
  }
  throw new UploadError(`${label} is taking too long to check. Try again in a moment.`);
}

export const ATTACHMENT_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/webp"];
export const ATTACHMENT_MAX_BYTES = 5 * 1024 * 1024;
export const ATTACHMENT_LIMIT = 3;

/** A problem with a file that can be seen before sending it anywhere. */
export function checkAttachment(file: File): string | null {
  if (!ATTACHMENT_TYPES.includes(file.type)) return `“${file.name}” is not a PDF or an image (JPEG, PNG or WebP).`;
  if (file.size > ATTACHMENT_MAX_BYTES) return `“${file.name}” is larger than 5 MB.`;
  if (file.size === 0) return `“${file.name}” is empty.`;
  return null;
}
