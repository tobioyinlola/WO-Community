import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import VerifyCertificate from "../pages/public/VerifyCertificate";
import { CertificateSheet } from "./CertificateSheet";

// The client builds real Request objects, which need an absolute address in this environment.
vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  const { default: createClient } = await import("openapi-fetch");
  return { ...actual, api: createClient({ baseUrl: "http://localhost", fetch: actual.authFetch }) };
});

afterEach(() => vi.unstubAllGlobals());

const sheet = {
  holder: "Ada Obi",
  course: "Fundraising basics",
  issuedAt: "2026-10-10T09:00:00Z",
  number: "WO-C-2026-000341",
  hours: 4.5,
  titleText: "Certificate of completion",
  signatoryName: "Onyeka Obi",
  signatoryTitle: "Founder",
  verifyUrl: "https://app.test/verify/WO-C-2026-000341",
};

describe("CertificateSheet", () => {
  it("shows what the certificate says, with the details and a QR code that names its link", () => {
    render(<CertificateSheet {...sheet} />);
    expect(screen.getByText("This certifies that")).toBeInTheDocument();
    expect(screen.getByText("Ada Obi")).toBeInTheDocument();
    expect(screen.getByText("has successfully completed")).toBeInTheDocument();
    expect(screen.getByText("Fundraising basics")).toBeInTheDocument();
    expect(screen.getByText("10 Oct 2026")).toBeInTheDocument();
    expect(screen.getByText("4.5 hours")).toBeInTheDocument();
    expect(screen.getByText("WO-C-2026-000341")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "QR code that opens https://app.test/verify/WO-C-2026-000341" })).toBeInTheDocument();
    expect(screen.getByText("Verify at app.test/verify")).toBeInTheDocument();
    expect(screen.getByText("The future of Africa is being built here.")).toBeInTheDocument();
  });

  it("uses the title and signatory it is given, and the singular for one hour", () => {
    render(<CertificateSheet {...sheet} hours={1} titleText="Certificate of merit" signatoryName="" signatoryTitle="" />);
    expect(screen.getByText("Certificate of merit")).toBeInTheDocument();
    expect(screen.getByText("1 hour")).toBeInTheDocument();
    expect(screen.queryByText("Onyeka Obi")).not.toBeInTheDocument();
  });
});

function verify(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/verify/wo-c-2026-000341"]}>
        <Routes>
          <Route path="/verify/:code" element={<VerifyCertificate />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("VerifyCertificate", () => {
  it("says Valid with the name, course and date and no more", async () => {
    verify(200, { valid: true, status: "valid", number: "WO-C-2026-000341", holder_name: "Ada Obi", course_title: "Fundraising basics", issued_at: "2026-10-10T09:00:00Z", hours: 4.5, verify_url: "x" });
    expect(await screen.findByText("Valid")).toBeInTheDocument();
    expect(screen.getByText("Ada Obi")).toBeInTheDocument();
    expect(screen.getByText("Fundraising basics")).toBeInTheDocument();
    expect(screen.getByText("10 Oct 2026")).toBeInTheDocument();
    expect(screen.getByText("WO-C-2026-000341")).toBeInTheDocument(); // shown in capitals as typed in lower case
  });

  it("says Revoked without naming anyone", async () => {
    verify(200, { valid: false, status: "revoked", number: "WO-C-2026-000341", holder_name: "", course_title: "", issued_at: null, hours: null, verify_url: "x" });
    expect(await screen.findByText("Revoked")).toBeInTheDocument();
    expect(screen.queryByText("Completed by")).not.toBeInTheDocument();
  });

  it("says Not found for a number that does not exist", async () => {
    verify(404, { title: "Not found", status: 404 });
    await waitFor(() => expect(screen.getByText("Not found")).toBeInTheDocument());
    expect(screen.getByText(/Check it was copied in full/)).toBeInTheDocument();
  });
});
