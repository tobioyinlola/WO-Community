import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Award, Download, Eye, Share2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import type { components } from "../api/schema";
import { Alert, Button, Card, CardText, CardTitle, Switch } from "../components";
import { formatDate } from "../lib/format";
import { EmptyState, ErrorState, Loaded, PageHeader, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { CertificateSheet } from "./CertificateSheet";
import "../styles/learn.css";

export type Certificate = components["schemas"]["Certificate"];

/** Asks for a short lived link to the PDF and starts the download without leaving the page. */
export function useCertificateActions(certificate: Pick<Certificate, "id" | "verify_url" | "course_title">) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const download = async () => {
    setBusy(true);
    try {
      const link = await unwrap(api.GET("/api/v1/certificates/{certificate_id}/download", { params: { path: { certificate_id: certificate.id } } }));
      const a = document.createElement("a");
      a.href = link.url;
      a.download = link.filename;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (error) {
      toast.show(messageOf(error));
    } finally {
      setBusy(false);
    }
  };
  const share = async () => {
    try {
      if (navigator.share) await navigator.share({ title: `My certificate for ${certificate.course_title}`, url: certificate.verify_url });
      else {
        await navigator.clipboard.writeText(certificate.verify_url);
        toast.show("Verification link copied");
      }
    } catch {
      /* a closed share sheet is not an error */
    }
  };
  return { busy, download, share };
}

/** What the member sees on finishing a course: a calm confirmation with the ways to use the certificate. */
export function CompletionCard({ courseSlug }: { courseSlug: string }) {
  // The certificate is drawn by a worker a moment after the last lecture, so ask again until it is there.
  const query = useQuery({
    queryKey: ["certificates", "for", courseSlug],
    queryFn: () => unwrap(api.GET("/api/v1/me/certificates")),
    refetchInterval: (q) => (q.state.data?.some((c) => c.course_slug === courseSlug) ? false : 2500),
  });
  const certificate = query.data?.find((c) => c.course_slug === courseSlug);
  if (!certificate) {
    return (
      <Alert tone="success" title="You finished the course">
        <span role="status">Your certificate is being prepared. It appears here in a moment.</span>
      </Alert>
    );
  }
  return <CompletionActions certificate={certificate} />;
}

function CompletionActions({ certificate }: { certificate: Certificate }) {
  const { busy, download, share } = useCertificateActions(certificate);
  return (
    <section className="wo-box" aria-labelledby="done-heading">
      <h2 id="done-heading" className="wo-learn__h3" style={{ marginTop: 0 }}>
        <Award size={20} strokeWidth={1.5} aria-hidden="true" /> You finished {certificate.course_title}
      </h2>
      <p className="body-sm app-muted" role="status">
        Your certificate {certificate.number} is ready.
      </p>
      <div className="wo-certpage__actions">
        <Button loading={busy} icon={<Download size={16} strokeWidth={1.5} />} onClick={() => void download()}>
          Download certificate
        </Button>
        <Link className="wo-btn wo-btn--secondary" to={`/app/learn/certificates/${certificate.id}`}>
          <Eye size={16} strokeWidth={1.5} aria-hidden="true" /> View certificate
        </Link>
        <Button variant="secondary" icon={<Share2 size={16} strokeWidth={1.5} />} onClick={() => void share()}>
          Share
        </Button>
      </div>
    </section>
  );
}

function CertificateCard({ certificate }: { certificate: Certificate }) {
  const { busy, download, share } = useCertificateActions(certificate);
  const revoked = certificate.status === "revoked";
  return (
    <Card>
      <Award size={28} strokeWidth={1.5} aria-hidden="true" />
      <CardTitle style={{ marginTop: "var(--space-3)" }}>{certificate.course_title}</CardTitle>
      <CardText>
        {certificate.holder_name} · {formatDate(certificate.issued_at)}
        {revoked ? " · Revoked" : ""}
      </CardText>
      <p className="mono" style={{ margin: "var(--space-3) 0" }}>
        {certificate.number}
      </p>
      <div className="wo-certpage__actions">
        <Link className="wo-btn wo-btn--secondary wo-btn--sm" to={`/app/learn/certificates/${certificate.id}`}>
          View
        </Link>
        {revoked ? null : (
          <>
            <Button variant="secondary" size="sm" loading={busy} onClick={() => void download()} aria-label={`Download the certificate for ${certificate.course_title}`}>
              Download
            </Button>
            <Button variant="ghost" size="sm" onClick={() => void share()} aria-label={`Share the certificate for ${certificate.course_title}`}>
              Share
            </Button>
          </>
        )}
      </div>
    </Card>
  );
}

/** Every certificate the member has earned. */
export function Certificates() {
  useDocumentTitle("Your certificates");
  const query = useQuery({ queryKey: ["certificates"], queryFn: () => unwrap(api.GET("/api/v1/me/certificates")) });
  return (
    <>
      <PageHeader eyebrow="Learn" title="Your certificates" lead="Earned by finishing a course. Each has a number anyone can check." />
      <Loaded query={query} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No certificates yet">Finish a course that offers one and it appears here.</EmptyState>}>
        {(items) => (
          <ul className="app-grid" aria-label="Certificates" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {items.map((c) => (
              <li key={c.id}>
                <CertificateCard certificate={c} />
              </li>
            ))}
          </ul>
        )}
      </Loaded>
    </>
  );
}

/** One certificate, shown as the page members receive, with the ways to download and share it. */
export default function CertificatePage() {
  const { id = "" } = useParams();
  const query = useQuery({ queryKey: ["certificate", id], queryFn: () => unwrap(api.GET("/api/v1/certificates/{certificate_id}", { params: { path: { certificate_id: id } } })), retry: false });
  const certificate = query.data;
  useDocumentTitle(certificate ? `Certificate: ${certificate.course_title}` : "Certificate");
  const actions = useCertificateActions(certificate ?? { id, verify_url: "", course_title: "" });
  const client = useQueryClient();
  const toast = useToast();
  const listing = useMutation({
    mutationFn: (show: boolean) => unwrap(api.PATCH("/api/v1/certificates/{certificate_id}", { params: { path: { certificate_id: id } }, body: { show_on_profile: show } })),
    onSuccess: async (saved) => {
      toast.show(saved.show_on_profile ? "Shown on your profile" : "Hidden from your profile");
      await Promise.all([client.invalidateQueries({ queryKey: ["certificate", id] }), client.invalidateQueries({ queryKey: ["certificates"] })]);
    },
    onError: (error) => toast.show(messageOf(error)),
  });
  if (query.isPending) return <SkeletonRows />;
  if (query.isError || !certificate) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const revoked = certificate.status === "revoked";
  return (
    <div className="wo-certpage">
      <p>
        <Link className="wo-linkbtn" to="/app/learn/certificates">
          <ArrowLeft size={16} strokeWidth={1.5} aria-hidden="true" /> Your certificates
        </Link>
      </p>
      <h1 className="h2" style={{ margin: 0 }}>
        {certificate.course_title}
      </h1>
      {revoked ? (
        <Alert tone="danger" title="This certificate has been revoked">
          It no longer verifies. If you think this is a mistake, contact support.
        </Alert>
      ) : null}
      <div className="wo-certgrid">
        <CertificateSheet
          holder={certificate.holder_name}
          course={certificate.course_title}
          issuedAt={certificate.issued_at}
          number={certificate.number}
          hours={certificate.hours}
          titleText={certificate.title_text}
          signatoryName={certificate.signatory_name}
          signatoryTitle={certificate.signatory_title}
          signatureUrl={certificate.signature_url}
          verifyUrl={certificate.verify_url}
        />
        <aside className="app-stack" aria-label="About this certificate">
          <div className="wo-certpage__actions">
            {revoked ? null : (
              <Button loading={actions.busy} icon={<Download size={16} strokeWidth={1.5} />} onClick={() => void actions.download()}>
                Download certificate
              </Button>
            )}
            {revoked ? null : (
              <Button variant="secondary" icon={<Share2 size={16} strokeWidth={1.5} />} onClick={() => void actions.share()}>
                Share
              </Button>
            )}
          </div>
          {revoked ? null : (
            <div className="app-stack" style={{ gap: "var(--space-1)" }}>
              <Switch label="Show on my profile" checked={certificate.show_on_profile} disabled={listing.isPending} onChange={(e) => listing.mutate(e.target.checked)} />
              <p className="caption app-muted" style={{ margin: 0 }}>
                Members who can see your profile will see the course, the date and a link to verify it.
              </p>
            </div>
          )}
          <p className="body-sm app-muted" style={{ margin: 0 }}>
            Anyone with the link can confirm it is real. They see your name, the course and the date, and nothing else.
          </p>
          <p className="body-sm" style={{ margin: 0 }}>
            Certificate number <span className="mono">{certificate.number}</span>
          </p>
          <p className="body-sm app-muted" style={{ margin: 0 }}>
            The name on a certificate is taken from your profile on the day it is issued. To change it for your next certificate, edit your profile.{" "}
            <Link className="wo-linkbtn" to="/app/me">
              Open your profile
            </Link>
          </p>
        </aside>
      </div>
    </div>
  );
}
