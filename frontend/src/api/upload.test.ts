import { afterEach, describe, expect, it, vi } from "vitest";

const post = vi.fn();
const get = vi.fn();
vi.mock("./client", () => ({ api: { POST: (...args: unknown[]) => post(...args), GET: (...args: unknown[]) => get(...args) } }));

import { uploadFile } from "./upload";

const reserved = (form: Record<string, unknown>) => ({
  data: { upload: { id: "u1" }, form: { url: "https://storage.test/b/k", expires_in: 60, form_data: {}, headers: {}, ...form } },
});

function setUp(form: Record<string, unknown>) {
  post.mockReset();
  get.mockReset();
  post.mockResolvedValueOnce(reserved(form)).mockResolvedValueOnce({ data: {} });
  get.mockResolvedValue({ data: { status: "ready" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("uploadFile", () => {
  it("sends a form with the file last when storage asks for a POST", async () => {
    setUp({ method: "POST", form_data: { key: "k", policy: "p" } });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    await uploadFile(new File(["x"], "a.png", { type: "image/png" }), "course_cover", 1, 2);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://storage.test/b/k");
    expect(init.method).toBe("POST");
    const keys = [...(init.body as FormData).keys()];
    expect(keys).toEqual(["key", "policy", "file"]);
  });

  it("sends the file itself with the signed headers when storage asks for a PUT", async () => {
    setUp({ method: "PUT", headers: { "Content-Type": "image/png" } });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["x"], "a.png", { type: "image/png" });
    await uploadFile(file, "course_cover", 1, 2);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("PUT");
    expect(init.headers).toEqual({ "Content-Type": "image/png" });
    expect(init.body).toBe(file);
  });

  it("says so when storage turns the file away", async () => {
    setUp({ method: "PUT", headers: {} });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    await expect(uploadFile(new File(["x"], "a.png", { type: "image/png" }), "course_cover", 1, 2)).rejects.toThrow(/Try again/);
  });
});
