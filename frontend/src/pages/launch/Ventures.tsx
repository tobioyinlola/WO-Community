import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Rocket } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { Badge, Button, CardTitle, CardText, CardTo, Input, Modal, Select } from "../../components";
import { formatDate } from "../../lib/format";
import { EmptyState, Loaded, PageHeader, SkeletonCards } from "../../ui/blocks";
import { FormError, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";

export const VENTURES_KEY = ["toolkit", "ventures"] as const;

function NewVenture({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const startups = useQuery({ queryKey: ["me", "startups"], queryFn: () => unwrap(api.GET("/api/v1/me/startups")) });
  const [name, setName] = useState("");
  const [from, setFrom] = useState("");
  const submit = useSubmit(async () => {
    const venture = await unwrap(api.POST("/api/v1/toolkit/ventures", { body: { name: name.trim(), ...(from ? { from_startup_id: from } : {}) } }));
    await client.invalidateQueries({ queryKey: VENTURES_KEY });
    toast.show("Venture created");
    onClose();
    navigate(`/app/launch/${venture.id}/profile`);
  });
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Launch toolkit"
      title="Start a venture"
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button loading={submit.busy} disabled={name.trim().length < 2} onClick={() => void submit.run()}>Create</Button>
        </>
      }
    >
      <div className="app-stack">
        <FormError error={submit.error} />
        <Input label="What is it called?" value={name} onChange={(e) => setName(e.target.value)} />
        {startups.data && startups.data.length > 0 ? (
          <Select
            label="Start from one of your startups"
            hint="We copy its details so you do not type them twice."
            value={from}
            onChange={(e) => {
              setFrom(e.target.value);
              if (!name.trim()) setName(startups.data?.find((s) => s.id === e.target.value)?.name ?? "");
            }}
            options={[{ value: "", label: "Start empty" }, ...startups.data.map((s) => ({ value: s.id, label: s.name ?? "Startup" }))]}
          />
        ) : null}
      </div>
    </Modal>
  );
}

export default function VenturesPage() {
  const [creating, setCreating] = useState(false);
  const query = useQuery({ queryKey: VENTURES_KEY, queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures")) });
  const shared = useQuery({ queryKey: ["toolkit", "shared"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures-shared-with-me")) });
  return (
    <>
      <PageHeader
        eyebrow="Launch toolkit"
        title="Launch toolkit"
        lead="A private workspace to take an idea to something you can show: score it, plan it, model it and pitch it."
        actions={<Button onClick={() => setCreating(true)}>Start a venture</Button>}
      />
      <Loaded
        query={query}
        skeleton={<SkeletonCards count={3} />}
        isEmpty={(d) => d.results.length === 0}
        empty={
          <EmptyState title="Start your first venture" icon={<Rocket size={22} strokeWidth={1.5} />} action={<Button onClick={() => setCreating(true)}>Start a venture</Button>}>
            Everything you write here is private to you. Nothing is shown to other members unless you share it.
          </EmptyState>
        }
      >
        {(data) => (
          <div className="app-grid">
            {data.results.map((v) => (
              <CardTo key={v.id} to={`/app/launch/${v.id}`}>
                <div className="app-cluster" style={{ marginBottom: "var(--space-3)" }}>
                  <Badge variant={v.status === "active" ? "success" : "neutral"} dot>{v.status === "active" ? "Active" : "Archived"}</Badge>
                </div>
                <CardTitle>{v.name}</CardTitle>
                <CardText>Profile {v.profile_completeness}% complete</CardText>
                <div className="app-meter" style={{ margin: "var(--space-3) 0" }} aria-hidden="true"><span style={{ width: `${v.profile_completeness}%` }} /></div>
                <p className="caption app-faint" style={{ margin: 0 }}>Updated {formatDate(v.updated_at)}</p>
              </CardTo>
            ))}
          </div>
        )}
      </Loaded>
      {shared.data && shared.data.length > 0 ? (
        <section className="app-section" aria-labelledby="shared">
          <h2 className="h3" id="shared" style={{ margin: "0 0 var(--space-4)" }}>Shared with you</h2>
          <div className="app-grid">
            {shared.data.map((s) => (
              <CardTo key={s.venture_id} to={`/app/launch/${s.venture_id}`}>
                <CardTitle>{s.name}</CardTitle>
                <CardText>Read only. Shared {formatDate(s.shared_at)}.</CardText>
              </CardTo>
            ))}
          </div>
        </section>
      ) : null}
      {creating ? <NewVenture onClose={() => setCreating(false)} /> : null}
    </>
  );
}

export function useDeleteVenture(ventureId: string) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/toolkit/ventures/{venture_id}", { params: { path: { venture_id: ventureId } } })),
    onSuccess: async () => {
      toast.show("Venture deleted. You have 14 days to restore it.");
      await client.invalidateQueries({ queryKey: VENTURES_KEY });
      navigate("/app/launch");
    },
  });
}
