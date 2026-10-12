import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import { uploadFile } from "../api/upload";
import { Alert, Button, Input } from "../components";
import { CertificateSheet } from "../learn/CertificateSheet";
import { ErrorState, PageHeader, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { useStepUp } from "./StepUp";
import "../styles/learn.css";

const SAMPLE_VERIFY = `${window.location.origin}/verify/WO-C-2026-000341`;

/**
 * What appears on every new certificate: the title, who signs and their signature. The sheet beside the
 * form is the same layout members receive and updates as you type. Changes apply to certificates issued
 * from now on; issued ones keep what they were drawn with until they are reissued.
 */
export default function CertificateTemplate() {
  useDocumentTitle("Certificate template");
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const saved = useQuery({ queryKey: ["admin", "certificate-settings"], queryFn: () => unwrap(api.GET("/api/v1/admin/certificate-settings")) });
  const [draft, setDraft] = useState<{ title_text: string; signatory_name: string; signatory_title: string } | null>(null);
  const [loadedFor, setLoadedFor] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [removeSignature, setRemoveSignature] = useState(false);

  if (saved.data && loadedFor !== saved.data.version) {
    setLoadedFor(saved.data.version);
    setDraft({ title_text: saved.data.title_text, signatory_name: saved.data.signatory_name, signatory_title: saved.data.signatory_title });
  }
  const set = (key: "title_text" | "signatory_name" | "signatory_title", value: string) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const unsaved = Boolean(saved.data && draft && (draft.title_text !== saved.data.title_text || draft.signatory_name !== saved.data.signatory_name || draft.signatory_title !== saved.data.signatory_title || file || removeSignature));

  const save = useSubmit(async () => {
    if (!draft) return;
    const upload = file ? await uploadFile(file, "cert_signature") : null;
    await guard(() =>
      unwrap(
        api.PUT("/api/v1/admin/certificate-settings", {
          body: { ...draft, ...(upload ? { signature_upload_id: upload.id } : {}), ...(removeSignature && !upload ? { remove_signature: true } : {}) },
        }),
      ),
    );
    setFile(null);
    setRemoveSignature(false);
    setPreview(null);
    toast.show("Template saved. It applies to new certificates.");
    await client.invalidateQueries({ queryKey: ["admin", "certificate-settings"] });
  });
  const pdf = useSubmit(async () => {
    const response = await api.POST("/api/v1/admin/certificate-settings/preview", { body: { ...(draft ?? {}), ...(removeSignature ? { remove_signature: true } : {}) }, parseAs: "blob" });
    if (response.error || !response.data) throw new Error("We could not draw the preview.");
    window.open(URL.createObjectURL(response.data as Blob), "_blank", "noopener");
  });
  const errors = errorsFrom(save.error).fields;

  if (saved.isPending) return <SkeletonRows />;
  if (saved.isError || !draft || !saved.data) return <ErrorState error={saved.error} onRetry={() => void saved.refetch()} />;

  const shownSignature = removeSignature ? null : (preview ?? saved.data.signature_url);
  return (
    <>
      <PageHeader
        eyebrow="Learning"
        title="Certificate template"
        lead="What members see on their certificate. Changes apply to certificates issued from now on."
        actions={
          <Link className="wo-btn wo-btn--secondary" to="/admin/certificates">
            Issued certificates
          </Link>
        }
      />
      <div className="wo-certgrid">
        <div className="app-stack">
          <FormError error={save.error} listFields />
          <Input label="Title shown on the certificate" value={draft.title_text} maxLength={60} onChange={(e) => set("title_text", e.target.value)} error={errors.title_text} />
          <Input label="Signatory name" value={draft.signatory_name} maxLength={120} onChange={(e) => set("signatory_name", e.target.value)} error={errors.signatory_name} />
          <Input label="Signatory title" value={draft.signatory_title} maxLength={120} onChange={(e) => set("signatory_title", e.target.value)} error={errors.signatory_title} />
          <div className="wo-field">
            <label className="wo-label" htmlFor="cert-signature">
              Signature image (optional)
            </label>
            <input
              id="cert-signature"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(e) => {
                const next = e.target.files?.[0] ?? null;
                setFile(next);
                setRemoveSignature(false);
                setPreview((old) => {
                  if (old?.startsWith("blob:")) URL.revokeObjectURL(old);
                  return next ? URL.createObjectURL(next) : null;
                });
              }}
            />
            <span className="wo-hint">A dark signature on a plain or transparent background looks best.</span>
            {saved.data.signature_url && !file ? (
              <div>
                <Button variant="ghost" size="sm" onClick={() => setRemoveSignature((v) => !v)} aria-pressed={removeSignature}>
                  {removeSignature ? "Keep the current signature" : "Remove the current signature"}
                </Button>
              </div>
            ) : null}
          </div>
          {pdf.error ? (
            <Alert tone="danger" title="No preview">
              {messageOf(pdf.error)}
            </Alert>
          ) : null}
          <div className="app-cluster">
            <Button loading={save.busy} disabled={!unsaved || !draft.title_text.trim()} onClick={() => void save.run()}>
              Save template
            </Button>
            <Button variant="secondary" loading={pdf.busy} icon={<Eye size={16} strokeWidth={1.5} />} onClick={() => void pdf.run()}>
              Open the PDF preview
            </Button>
          </div>
          <p className="body-sm app-muted" style={{ margin: 0 }}>
            Certificates already issued keep the template they were drawn with. Reissue one from the issued certificates list to give it the new look.
          </p>
        </div>
        <CertificateSheet
          holder="Amaka Obi"
          course="Founder fundamentals"
          issuedAt={new Date()}
          number="WO-C-2026-000341"
          hours={4.5}
          titleText={draft.title_text.trim() || "Certificate of completion"}
          signatoryName={draft.signatory_name}
          signatoryTitle={draft.signatory_title}
          signatureUrl={shownSignature}
          verifyUrl={SAMPLE_VERIFY}
        />
      </div>
    </>
  );
}
