import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Button, Input, Select } from "../components";
import { formatDate } from "../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, SkeletonRows, TableScroll, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { ReasonDialog } from "./dialogs";
import { StatusChip } from "./kit/TableBits";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Row = components["schemas"]["AdminCertificate"];

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Every certificate issued, with revoke and reissue. Reissuing a revoked certificate makes it valid again. */
export default function AdminCertificates() {
  useDocumentTitle("Certificates");
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"" | "valid" | "revoked">("");
  const [revoking, setRevoking] = useState<Row | null>(null);
  const [reissuing, setReissuing] = useState<Row | null>(null);
  const query = useDebounced(q.trim());
  const list = useOffsetList<Row>(["admin", "certificates", status, query], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/certificates", { params: { query: { limit, offset, ...(status ? { status } : {}), ...(query ? { q: query } : {}) } } })),
  );
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "certificates"] });
  return (
    <>
      <PageHeader
        eyebrow="Learning"
        title="Certificates"
        lead="Every certificate issued, newest first."
        actions={
          <Link className="wo-btn wo-btn--secondary" to="/admin/learning/certificate-template">
            Certificate template
          </Link>
        }
      />
      <div className="app-cluster" style={{ margin: "var(--space-6) 0", alignItems: "flex-end" }}>
        <div style={{ minWidth: 240, flex: "1 1 240px", maxWidth: 380 }}>
          <Input label="Search certificates" type="search" value={q} hint="A number, name, course or email." onChange={(e) => setQ(e.target.value)} />
        </div>
        <div style={{ width: 170 }}>
          <Select label="Status" options={[{ value: "", label: "All" }, { value: "valid", label: "Valid" }, { value: "revoked", label: "Revoked" }]} value={status} onChange={(e) => setStatus(e.target.value as "" | "valid" | "revoked")} />
        </div>
      </div>
      {list.query.isPending ? <SkeletonRows /> : null}
      {list.query.isError ? <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} /> : null}
      {list.isEmpty ? <EmptyState title={q || status ? "No certificates match" : "No certificates yet"}>A certificate is issued when a member finishes a course that offers one.</EmptyState> : null}
      {list.items.length ? (
        <TableScroll label="Certificates">
          <table className="app-table">
            <thead>
              <tr>
                <th scope="col">Certificate</th>
                <th scope="col">Learner</th>
                <th scope="col">Issued</th>
                <th scope="col">Status</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {list.items.map((c) => (
                <tr key={c.id}>
                  <th scope="row">
                    <span className="mono">{c.number}</span>
                    <div className="caption app-muted">{c.course_title}</div>
                  </th>
                  <td>
                    {c.holder_name}
                    <div className="caption app-muted">{c.email}</div>
                  </td>
                  <td>{formatDate(c.issued_at)}</td>
                  <td>
                    <StatusChip tone={c.status === "valid" ? "success" : "danger"}>{c.status === "valid" ? "Valid" : "Revoked"}</StatusChip>
                    {c.revoked_reason ? <div className="caption app-muted">{c.revoked_reason}</div> : null}
                  </td>
                  <td>
                    <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
                      <Button size="sm" variant="secondary" onClick={() => setReissuing(c)} aria-label={`${c.status === "revoked" ? "Restore" : "Reissue"} certificate ${c.number}`}>
                        {c.status === "revoked" ? "Restore" : "Reissue"}
                      </Button>
                      {c.status === "valid" ? (
                        <Button size="sm" variant="ghost" onClick={() => setRevoking(c)} aria-label={`Revoke certificate ${c.number}`}>
                          Revoke
                        </Button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      ) : null}
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
      {revoking ? (
        <ReasonDialog
          title={`Revoke ${revoking.number}?`}
          confirmLabel="Revoke certificate"
          tone="danger"
          intro="The public page will show it as revoked and the member can no longer download it. The reason is kept in the audit log."
          onConfirm={async (reason) => {
            await guard(() => unwrap(api.POST("/api/v1/admin/certificates/{certificate_id}/revoke", { params: { path: { certificate_id: revoking.id } }, body: { reason } })));
            toast.show("Certificate revoked");
            await refresh();
          }}
          onClose={() => setRevoking(null)}
        />
      ) : null}
      {reissuing ? (
        <ReasonDialog
          title={`${reissuing.status === "revoked" ? "Restore" : "Reissue"} ${reissuing.number}?`}
          confirmLabel={reissuing.status === "revoked" ? "Restore certificate" : "Reissue certificate"}
          required={false}
          intro={`The certificate is drawn again with the template as it is now and the member is told. ${reissuing.status === "revoked" ? "It becomes valid again. " : ""}The reason box is optional and not shown to the member.`}
          onConfirm={async () => {
            await guard(() => unwrap(api.POST("/api/v1/admin/certificates/{certificate_id}/reissue", { params: { path: { certificate_id: reissuing.id } }, body: {} })));
            toast.show(reissuing.status === "revoked" ? "Certificate restored" : "Certificate reissued");
            await refresh();
          }}
          onClose={() => setReissuing(null)}
        />
      ) : null}
    </>
  );
}
