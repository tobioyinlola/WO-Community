import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import { Alert, Button, Input } from "../components";
import { CertificateSheet } from "../learn/CertificateSheet";
import { ErrorState, PageHeader, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { useStepUp } from "./StepUp";
import "../styles/learn.css";

/**
 * What appears on every new certificate: the title and the name of who signs. The sheet beside the
 * form is the same layout members receive and updates as you type. Changes apply to certificates issued
 * from now on; issued ones keep what they were drawn with until they are reissued.
 */
export default function CertificateTemplate() {
  useDocumentTitle("Certificate template");
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const saved = useQuery({ queryKey: ["admin", "certificate-settings"], queryFn: () => unwrap(api.GET("/api/v1/admin/certificate-settings")) });
  const [draft, setDraft] = useState<{ title_text: string; signatory_name: string} | null>(null);
  const [loadedFor, setLoadedFor] = useState(0);

  if (saved.data && loadedFor !== saved.data.version) {
    setLoadedFor(saved.data.version);
    setDraft({ title_text: saved.data.title_text, signatory_name: saved.data.signatory_name });
  }
  const set = (key: "title_text" | "signatory_name", value: string) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const unsaved = Boolean(saved.data && draft && (draft.title_text !== saved.data.title_text || draft.signatory_name !== saved.data.signatory_name));

  const save = useSubmit(async () => {
    if (!draft) return;
    await guard(() =>
      unwrap(
        api.PUT("/api/v1/admin/certificate-settings", {
          body: { ...draft },
        }),
      ),
    );
    toast.show("Template saved. It applies to new certificates.");
    await client.invalidateQueries({ queryKey: ["admin", "certificate-settings"] });
  });
  const pdf = useSubmit(async () => {
    const response = await api.POST("/api/v1/admin/certificate-settings/preview", { body: { ...(draft ?? {}) }, parseAs: "blob" });
    if (response.error || !response.data) throw new Error("We could not draw the preview.");
    window.open(URL.createObjectURL(response.data as Blob), "_blank", "noopener");
  });
  const errors = errorsFrom(save.error).fields;

  if (saved.isPending) return <SkeletonRows />;
  if (saved.isError || !draft || !saved.data) return <ErrorState error={saved.error} onRetry={() => void saved.refetch()} />;

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
          <Input label="Signatory name" hint="Printed on every certificate as a name only." value={draft.signatory_name} maxLength={120} onChange={(e) => set("signatory_name", e.target.value)} error={errors.signatory_name} />
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
        />
      </div>
    </>
  );
}
