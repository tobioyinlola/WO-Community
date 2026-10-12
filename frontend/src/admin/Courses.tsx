import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap, unwrapTagged } from "../api/client";
import type { components } from "../api/schema";
import { Alert, Badge, Button, Card, Checkbox, Input, Modal, Select, StatTile, Textarea } from "../components";
import { formatDate, humanise } from "../lib/format";
import { htmlToText, textToHtml } from "../lib/html";
import { EmptyState, ErrorState, Loaded, LoadMore, PageHeader, SkeletonCards, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { ConfirmDialog } from "./dialogs";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Course = components["schemas"]["AdminCourse"];
type Level = components["schemas"]["CourseLevelEnum"];
type Lesson = components["schemas"]["AdminLesson"];
type LessonType = components["schemas"]["LessonTypeEnum"];

const LEVELS: Level[] = ["beginner", "intermediate", "advanced"];
const LESSON_TYPES: LessonType[] = ["video", "reading", "resource"];

interface Draft {
  title: string;
  description: string;
  instructor: string;
  category: string;
  level: Level;
  open_to_visitors: boolean;
  certificate_enabled: boolean;
}

const blankCourse: Draft = { title: "", description: "", instructor: "", category: "", level: "beginner", open_to_visitors: false, certificate_enabled: true };

function Basics({ id, onClose, onSaved }: { id: string | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const guard = useStepUp();
  // Editing needs the version the course is at now, so it is read first.
  const existing = useQuery({
    queryKey: ["admin", "course", id, "tagged"],
    enabled: Boolean(id),
    queryFn: () => unwrapTagged(api.GET("/api/v1/admin/courses/{course_id}", { params: { path: { course_id: id ?? "" } } })),
  });
  const [draft, setDraft] = useState<Draft | null>(id ? null : blankCourse);
  const [loadedFor, setLoadedFor] = useState("");
  if (id && existing.data && loadedFor !== existing.data.etag) {
    const c = existing.data.data;
    setLoadedFor(existing.data.etag);
    setDraft({ title: c.title, description: htmlToText(c.description), instructor: c.instructor, category: c.category, level: c.level as Level, open_to_visitors: c.open_to_visitors, certificate_enabled: c.certificate_enabled });
  }
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const save = useSubmit(async () => {
    if (!draft) return;
    const body = { ...draft, title: draft.title.trim(), instructor: draft.instructor.trim(), category: draft.category.trim(), description: textToHtml(draft.description), access: "free" as const };
    await guard(() =>
      id
        ? unwrap(api.PATCH("/api/v1/admin/courses/{course_id}", { params: { path: { course_id: id }, header: { "If-Match": existing.data?.etag ?? "" } }, body }))
        : unwrap(api.POST("/api/v1/admin/courses", { body })),
    );
    toast.show(id ? "Course saved" : "Draft created");
    await onSaved();
    onClose();
  });
  const errors = errorsFrom(save.error).fields;
  return (
    <Modal open onClose={onClose} eyebrow="Courses" title={id ? "Edit course" : "New course"}
      actions={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={save.busy} disabled={!draft || !draft.title.trim() || !draft.description.trim()} onClick={() => void save.run()}>{id ? "Save" : "Save as draft"}</Button></>}>
      {id && existing.isPending ? <SkeletonRows /> : id && existing.isError ? <ErrorState error={existing.error} /> : draft ? (
      <div className="app-stack">
        <FormError error={save.error} />
        <Input label="Title" value={draft.title} onChange={(e) => set("title", e.target.value)} error={errors.title} />
        <Textarea label="What it covers" rows={5} hint="Leave a blank line between paragraphs." value={draft.description} onChange={(e) => set("description", e.target.value)} error={errors.description} />
        <div className="app-formgrid">
          <Input label="Taught by" value={draft.instructor} onChange={(e) => set("instructor", e.target.value)} error={errors.instructor} />
          <Input label="Category" value={draft.category} onChange={(e) => set("category", e.target.value)} error={errors.category} />
          <Select label="Level" options={LEVELS.map((l) => ({ value: l, label: humanise(l) }))} value={draft.level} onChange={(e) => set("level", e.target.value as Level)} error={errors.level} />
        </div>
        <Checkbox label="Visitors can read it without joining" checked={draft.open_to_visitors} onChange={(e) => set("open_to_visitors", e.target.checked)} />
        <Checkbox label="Give a certificate on completion" checked={draft.certificate_enabled} onChange={(e) => set("certificate_enabled", e.target.checked)} />
        <Alert tone="info" title="Free courses only">Paid courses are not available yet, so every course is free to members.</Alert>
      </div>
      ) : null}
    </Modal>
  );
}

function LessonForm({ moduleId, lesson, onDone, onCancel }: { moduleId: string; lesson: Lesson | null; onDone: () => Promise<void>; onCancel: () => void }) {
  const guard = useStepUp();
  const [type, setType] = useState<LessonType>((lesson?.type as LessonType) ?? "reading");
  const [title, setTitle] = useState(lesson?.title ?? "");
  const [video, setVideo] = useState(lesson?.video_url ?? "");
  const [body, setBody] = useState(lesson ? htmlToText(lesson.body) : "");
  const [url, setUrl] = useState(lesson?.resource_url ?? "");
  const [name, setName] = useState(lesson?.resource_name ?? "");
  const [minutes, setMinutes] = useState(lesson?.duration_seconds ? String(Math.round(lesson.duration_seconds / 60)) : "");
  const save = useSubmit(async () => {
    // The API refuses blank fields that do not belong to the kind, so send only the ones that do.
    const data = {
      type,
      title: title.trim(),
      ...(minutes.trim() ? { duration_seconds: Number(minutes) * 60 } : {}),
      ...(type === "video" ? { video_url: video.trim() } : {}),
      ...(type === "reading" ? { body: textToHtml(body) } : {}),
      ...(type === "resource" ? { resource_url: url.trim(), resource_name: name.trim() } : {}),
    };
    await guard(() =>
      lesson
        ? unwrap(api.PATCH("/api/v1/admin/lessons/{lesson_id}", { params: { path: { lesson_id: lesson.id } }, body: data }))
        : unwrap(api.POST("/api/v1/admin/modules/{module_id}/lessons", { params: { path: { module_id: moduleId } }, body: data })),
    );
    await onDone();
  });
  const errors = errorsFrom(save.error).fields;
  return (
    <Card variant="white">
      <div className="app-stack">
        <FormError error={save.error} listFields />
        <div className="app-formgrid">
          <Select label="Kind" options={LESSON_TYPES.map((t) => ({ value: t, label: t === "video" ? "Video" : t === "reading" ? "Reading" : "Download" }))} value={type} onChange={(e) => setType(e.target.value as LessonType)} />
          <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title} />
          <Input label="Minutes to complete (optional)" type="number" min={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} error={errors.duration_seconds} />
        </div>
        {type === "video" ? <Input label="YouTube link" value={video} onChange={(e) => setVideo(e.target.value)} error={errors.video_url} /> : null}
        {type === "reading" ? <Textarea label="Text" rows={6} value={body} onChange={(e) => setBody(e.target.value)} error={errors.body} /> : null}
        {type === "resource" ? (
          <div className="app-formgrid">
            <Input label="Link to the file" value={url} onChange={(e) => setUrl(e.target.value)} error={errors.resource_url} />
            <Input label="Name shown to members" value={name} onChange={(e) => setName(e.target.value)} error={errors.resource_name} />
          </div>
        ) : null}
        <div className="app-cluster">
          <Button size="sm" loading={save.busy} disabled={!title.trim()} onClick={() => void save.run()}>{lesson ? "Save lesson" : "Add lesson"}</Button>
          <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
        </div>
      </div>
    </Card>
  );
}

function Curriculum({ courseId, onClose, onChanged }: { courseId: string; onClose: () => void; onChanged: () => Promise<void> }) {
  const client = useQueryClient();
  const guard = useStepUp();
  const toast = useToast();
  const course = useQuery({ queryKey: ["admin", "course", courseId], queryFn: () => unwrap(api.GET("/api/v1/admin/courses/{course_id}", { params: { path: { course_id: courseId } } })) });
  const [newModule, setNewModule] = useState("");
  const [lessonFor, setLessonFor] = useState<{ moduleId: string; lesson: Lesson | null } | null>(null);
  const [removing, setRemoving] = useState<{ kind: "module" | "lesson"; id: string; title: string } | null>(null);
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["admin", "course", courseId] });
    await onChanged();
  };
  const addModule = useSubmit(async () => {
    await guard(() => unwrap(api.POST("/api/v1/admin/courses/{course_id}/modules", { params: { path: { course_id: courseId } }, body: { title: newModule.trim() } })));
    setNewModule("");
    await refresh();
  });
  const remove = async () => {
    if (!removing) return;
    await guard(() =>
      removing.kind === "module"
        ? unwrap(api.DELETE("/api/v1/admin/modules/{module_id}", { params: { path: { module_id: removing.id } } }))
        : unwrap(api.DELETE("/api/v1/admin/lessons/{lesson_id}", { params: { path: { lesson_id: removing.id } } })),
    );
    toast.show(`${removing.kind === "module" ? "Module" : "Lesson"} removed`);
    await refresh();
  };
  return (
    <Modal open onClose={onClose} eyebrow="Courses" title="Modules and lessons" actions={<Button onClick={onClose}>Done</Button>}>
      <Loaded query={course} skeleton={<SkeletonRows />}>
        {(c) => (
          <div className="app-stack">
            <p className="body-sm app-muted" style={{ margin: 0 }}>{c.title}. Members see the modules in this order.</p>
            {c.modules.map((m) => (
              <Card key={m.id}>
                <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                  <h3 className="h4" style={{ margin: 0 }}>{m.title}</h3>
                  <Button size="sm" variant="ghost" onClick={() => setRemoving({ kind: "module", id: m.id, title: m.title })} aria-label={`Remove module ${m.title}`}>Remove</Button>
                </div>
                <ol className="app-stack" style={{ margin: "var(--space-3) 0", paddingLeft: "var(--space-6)", gap: "var(--space-2)" }}>
                  {m.lessons.map((l) => (
                    <li key={l.id}>
                      <span className="app-cluster" style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
                        <span>{l.title} <span className="caption app-muted">{humanise(l.type)}</span></span>
                        <span className="app-cluster" style={{ flexWrap: "nowrap" }}>
                          <Button size="sm" variant="ghost" onClick={() => setLessonFor({ moduleId: m.id, lesson: l })} aria-label={`Edit lesson ${l.title}`}>Edit</Button>
                          <Button size="sm" variant="ghost" onClick={() => setRemoving({ kind: "lesson", id: l.id, title: l.title })} aria-label={`Remove lesson ${l.title}`}>Remove</Button>
                        </span>
                      </span>
                    </li>
                  ))}
                </ol>
                {lessonFor && lessonFor.moduleId === m.id ? (
                  <LessonForm key={lessonFor.lesson?.id ?? "new"} moduleId={m.id} lesson={lessonFor.lesson} onCancel={() => setLessonFor(null)} onDone={async () => { setLessonFor(null); await refresh(); }} />
                ) : (
                  <Button size="sm" variant="secondary" onClick={() => setLessonFor({ moduleId: m.id, lesson: null })}>Add a lesson</Button>
                )}
              </Card>
            ))}
            <FormError error={addModule.error} />
            <div className="app-cluster" style={{ alignItems: "flex-end", flexWrap: "nowrap" }}>
              <div style={{ flex: 1 }}><Input label="New module" value={newModule} onChange={(e) => setNewModule(e.target.value)} /></div>
              <Button variant="secondary" loading={addModule.busy} disabled={!newModule.trim()} onClick={() => void addModule.run()}>Add module</Button>
            </div>
          </div>
        )}
      </Loaded>
      {removing ? <ConfirmDialog title={`Remove this ${removing.kind}?`} body={`“${removing.title}”${removing.kind === "module" ? " and every lesson in it" : ""} will be deleted.`} confirmLabel="Remove" tone="danger" onConfirm={remove} onClose={() => setRemoving(null)} /> : null}
    </Modal>
  );
}

function Stats({ course, onClose }: { course: Course; onClose: () => void }) {
  const stats = useQuery({ queryKey: ["admin", "course", course.id, "stats"], queryFn: () => unwrap(api.GET("/api/v1/admin/courses/{course_id}/stats", { params: { path: { course_id: course.id } } })) });
  return (
    <Modal open onClose={onClose} eyebrow={course.title} title="How it is going" actions={<Button onClick={onClose}>Close</Button>}>
      <Loaded query={stats} skeleton={<SkeletonRows />}>
        {(s) => (
          <div className="app-stack">
            <div className="app-grid">
              <StatTile label="Enrolled" value={String(s.enrolled)} />
              <StatTile label="Completed" value={String(s.completed)} />
              <StatTile label="Completion" value={s.completion_rate === null ? "None yet" : `${Math.round(s.completion_rate * 100)}%`} />
              <StatTile label="Rating" value={s.rating.average === null ? "None yet" : `${s.rating.average.toFixed(1)} (${s.rating.count})`} />
            </div>
            <h3 className="h4" style={{ margin: 0 }}>Lessons finished</h3>
            <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0, gap: "var(--space-2)" }}>
              {s.lessons.map((l) => <li key={l.id} className="app-cluster" style={{ justifyContent: "space-between" }}><span>{l.title}</span><Badge variant="neutral">{l.completed_by}</Badge></li>)}
            </ul>
          </div>
        )}
      </Loaded>
    </Modal>
  );
}

export default function Courses() {
  useDocumentTitle("Courses");
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [status, setStatus] = useState<"" | "draft" | "published">("");
  const [editing, setEditing] = useState<Course | "new" | null>(null);
  const [building, setBuilding] = useState<string | null>(null);
  const [stats, setStats] = useState<Course | null>(null);
  const [confirm, setConfirm] = useState<{ course: Course; action: "publish" | "unpublish" | "delete" } | null>(null);
  const list = useOffsetList<Course>(["admin", "courses", status], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/courses", { params: { query: { limit, offset, ...(status ? { status } : {}) } } })),
  );
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "courses"] });
  const duplicate = async (c: Course) => {
    await guard(() => unwrap(api.POST("/api/v1/admin/courses/{course_id}/duplicate", { params: { path: { course_id: c.id } } })));
    toast.show("Copy created as a draft");
    await refresh();
  };
  const run = async (c: Course, action: "publish" | "unpublish" | "delete") => {
    const path = { params: { path: { course_id: c.id } } };
    await guard(() => {
      if (action === "publish") return unwrap(api.POST("/api/v1/admin/courses/{course_id}/publish", path));
      if (action === "unpublish") return unwrap(api.POST("/api/v1/admin/courses/{course_id}/unpublish", path));
      return unwrap(api.DELETE("/api/v1/admin/courses/{course_id}", path));
    });
    toast.show({ publish: "Course published", unpublish: "Course taken down", delete: "Course deleted" }[action]);
    await refresh();
  };
  return (
    <>
      <PageHeader eyebrow="Content" title="Courses" lead="Build learning for the community." actions={<Button onClick={() => setEditing("new")}>New course</Button>} />
      <div style={{ maxWidth: 240, marginBottom: "var(--space-6)" }}>
        <Select label="Show" options={[{ value: "", label: "All" }, { value: "draft", label: "Draft" }, { value: "published", label: "Published" }]} value={status} onChange={(e) => setStatus(e.target.value as "" | "draft" | "published")} />
      </div>
      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title="No courses yet" action={<Button onClick={() => setEditing("new")}>Create the first one</Button>}>Courses you create will be listed here.</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((c) => (
              <li key={c.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <div className="app-cluster"><Badge variant={c.status === "published" ? "success" : "neutral"} dot>{humanise(c.status)}</Badge><Badge variant="neutral">{humanise(c.level)}</Badge></div>
                    <span className="caption app-muted">{c.lesson_count} lessons · edited {formatDate(c.edited_at ?? c.created_at)}</span>
                  </div>
                  <h2 className="h4" style={{ margin: "var(--space-3) 0 var(--space-1)" }}>{c.title}</h2>
                  <p className="body-sm app-muted" style={{ margin: 0 }}>{[c.instructor, c.category].filter(Boolean).join(" · ")}</p>
                  <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                    <Button size="sm" variant="secondary" onClick={() => setEditing(c)}>Details</Button>
                    <Button size="sm" variant="secondary" onClick={() => setBuilding(c.id)}>Lessons</Button>
                    {c.status === "draft" ? <Button size="sm" onClick={() => setConfirm({ course: c, action: "publish" })}>Publish</Button> : <Button size="sm" variant="ghost" onClick={() => setConfirm({ course: c, action: "unpublish" })}>Take down</Button>}
                    {c.status === "published" ? <Button size="sm" variant="ghost" onClick={() => setStats(c)}>Results</Button> : null}
                    <Button size="sm" variant="ghost" onClick={() => void duplicate(c)} aria-label={`Copy ${c.title}`}>Copy</Button>
                    {c.status === "draft" ? <Button size="sm" variant="ghost" onClick={() => setConfirm({ course: c, action: "delete" })} aria-label={`Delete ${c.title}`}>Delete</Button> : null}
                  </div>
                </Card>
              </li>
            ))}
          </ul>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
      {editing ? <Basics id={editing === "new" ? null : editing.id} onClose={() => setEditing(null)} onSaved={refresh} /> : null}
      {building ? <Curriculum courseId={building} onClose={() => setBuilding(null)} onChanged={refresh} /> : null}
      {stats ? <Stats course={stats} onClose={() => setStats(null)} /> : null}
      {confirm ? (
        <ConfirmDialog
          title={{ publish: "Publish this course?", unpublish: "Take this course down?", delete: "Delete this course?" }[confirm.action]}
          body={{ publish: "Members can enrol straight away. It needs at least one lesson.", unpublish: "New members cannot enrol. People already learning keep their progress.", delete: "The draft and its lessons are deleted for good." }[confirm.action]}
          confirmLabel={{ publish: "Publish", unpublish: "Take down", delete: "Delete" }[confirm.action]}
          tone={confirm.action === "publish" ? "primary" : "danger"}
          onConfirm={() => run(confirm.course, confirm.action)}
          onClose={() => setConfirm(null)}
        />
      ) : null}
    </>
  );
}
