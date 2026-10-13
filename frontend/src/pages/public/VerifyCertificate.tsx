import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, ShieldX } from "lucide-react";
import { useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { ApiError } from "../../api/errors";
import { formatDate } from "../../lib/format";
import { SkeletonRows, useDocumentTitle } from "../../ui/blocks";
import "../../styles/learn.css";

/**
 * The page a certificate's QR code and link open. Anyone can see it. It says whether the certificate is
 * valid and, if so, who completed which course and when. Nothing else about the person is shown.
 */
export default function VerifyCertificate() {
  const { code = "" } = useParams();
  useDocumentTitle("Verify a certificate");
  const query = useQuery({
    queryKey: ["verify", code],
    queryFn: () => unwrap(api.GET("/api/v1/public/certificates/{code}", { params: { path: { code } } })),
    retry: false,
  });
  const unknown = query.error instanceof ApiError && query.error.status === 404;
  return (
    <div className="wo-verify">
        <p className="wo-verify__eyebrow">Certificate check</p>
        <h1 className="h2" style={{ margin: 0 }}>
          Verify a certificate
        </h1>
        <p className="body-sm app-muted" style={{ margin: 0 }}>
          Certificate number <span className="mono">{code.toUpperCase()}</span>
        </p>
        {query.isPending ? <SkeletonRows /> : null}
        {query.data?.valid ? (
          <section className="wo-verify__card" data-state="valid" aria-live="polite">
            <p className="wo-verify__status">
              <BadgeCheck size={22} strokeWidth={1.5} aria-hidden="true" /> Valid
            </p>
            <dl className="wo-verify__facts">
              <dt>Completed by</dt>
              <dd>{query.data.holder_name}</dd>
              <dt>Course</dt>
              <dd>{query.data.course_title}</dd>
              <dt>Date of completion</dt>
              <dd>{query.data.issued_at ? formatDate(query.data.issued_at) : ""}</dd>
              {query.data.hours ? (
                <>
                  <dt>Course length</dt>
                  <dd>{query.data.hours} hours</dd>
                </>
              ) : null}
            </dl>
            <p className="body-sm app-muted" style={{ margin: 0 }}>
              Issued by WO Community.
            </p>
          </section>
        ) : null}
        {query.data && !query.data.valid ? (
          <section className="wo-verify__card" data-state="revoked" aria-live="polite">
            <p className="wo-verify__status">
              <ShieldX size={22} strokeWidth={1.5} aria-hidden="true" /> Revoked
            </p>
            <p style={{ margin: 0 }}>WO Community has withdrawn this certificate. It should not be relied on.</p>
          </section>
        ) : null}
        {unknown ? (
          <section className="wo-verify__card" data-state="unknown" aria-live="polite">
            <p className="wo-verify__status">
              <ShieldX size={22} strokeWidth={1.5} aria-hidden="true" /> Not found
            </p>
            <p style={{ margin: 0 }}>We have no certificate with this number. Check it was copied in full, with the dashes.</p>
          </section>
        ) : null}
        {query.isError && !unknown ? <p role="alert">We could not check this certificate just now. Try again in a moment.</p> : null}
    </div>
  );
}
