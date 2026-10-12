import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, unwrap, unwrapTagged } from "../api/client";
import type { components } from "../api/schema";
import { uploadFile } from "../api/upload";
import { Alert, Button, Card, Checkbox, Input, Select, Tabs, Textarea } from "../components";
import { formatDate, humanise } from "../lib/format";
import { htmlToText, textToHtml } from "../lib/html";
import { ErrorState, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { Announcements, Learners, Questions, Requests, Reviews } from "./CourseEngage";
import { ConfirmDialog } from "./dialogs";
import { StatusChip } from "./kit/TableBits";
import { useStepUp } from "./StepUp";

type Course = components["schemas"]["AdminCourse"];
type Lesson = components["schemas"]["AdminLesson"];
type LessonType = components["schemas"]["LessonTypeEnum"];

const TABS = [
  { id: "curriculum", label: "Curriculum" },
  { id: "learners", label: "Learners" },
  { id: "requests", label: "Requests" },
  { id: "reviews", label: "Reviews" },
  { id: "questions", label: "Q&A" },
  { id: "announcements", label: "Announcements" },
  { id: "settings", label: "Settings" },
];
const LESSON_TYPES: LessonType[] = ["video", "reading", "resource"];
const LEVELS = ["beginner", "intermediate", "advanced", "all"];

function LessonForm({ moduleId, lesson, onDone, onCancel }: { moduleId: string; lesson: Lesson | null; onDone: () => Promise<void>; onCancel: () => void }) {
  const guard = useStepUp();
  const [type, setType] = useState<LessonType>((lesson?.type as LessonType) ?? "video");
  const [title, setTitle] = useState(lesson?.title ?? "");
  const [video, setVideo] = useState(lesson?.video_url ?? "");
  const [body, setBody] = useState(lesson ? htmlToText(lesson.body) : "");
  const [url, setUrl] = useState(lesson?.resource_url ?? "");
  const [name, setName] = useState(lesson?.resource_name ?? "");
  const [description, setDescription] = useState(lesson?.description ?? "");
  const [preview, setPreview] = useState(lesson?.is_preview ?? false);
  const [minutes, setMinutes] = useState(lesson?.duration_seconds ? String(Math.round(lesson.duration_seconds / 60)) : "");
  const save = useSubmit(async () => {
    // The API refuses blank fields that do not belong to the kind, so send only the ones that do.
    const data = {
      type,
      title: title.trim(),
      description: description.trim(),
      is_preview: preview,
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
          <Input label="Minutes (optional)" type="number" min={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} error={errors.duration_seconds} />
        </div>
        {type === "video" ? <Input label="YouTube link" value={video} onChange={(e) => setVideo(e.target.value)} error={errors.video_url} /> : null}
        {type === "reading" ? <Textarea label="Text" rows={6} value={body} onChange={(e) => setBody(e.target.value)} error={errors.body} /> : null}
        {type === "resource" ? (
          <div className="app-formgrid">
            <Input label="Link to the file" value={url} onChange={(e) => setUrl(e.target.value)} error={errors.resource_url} />
            <Input label="Name shown to members" value={name} onChange={(e) => setName(e.target.value)} error={errors.resource_name} />
          </div>
        ) : null}
        <Textarea label="About this lecture (optional)" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} />
        <Checkbox label="Free preview: visitors can watch this lecture" checked={preview} onChange={(e) => setPreview(e.target.checked)} />
        <div className="app-cluster">
          <Button size="sm" loading={save.busy} disabled={!title.trim()} onClick={() => void save.run()}>
            {lesson ? "Save lecture" : "Add lecture"}
          </Button>
          <Button size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </div>
    </Card>
  );
}

function BulkLinks({ moduleId, onDone }: { moduleId: string; onDone: () => Promise<void> }) {
  const guard = useStepUp();
  const toast = useToast();
  const [text, setText] = useState("");
  const urls = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const add = useSubmit(async () => {
    await guard(() => unwrap(api.POST("/api/v1/admin/modules/{module_id}/lessons/bulk", { params: { path: { module_id: moduleId } }, body: { urls } })));
    toast.show(`${urls.length} ${urls.length === 1 ? "lecture" : "lectures"} added`);
    setText("");
    await onDone();
  });
  return (
    <div className="app-stack">
      <FormError error={add.error} listFields />
      <Textarea label="Paste YouTube links, one per line" rows={4} value={text} onChange={(e) => setText(e.target.value)} hint="All or nothing: if a link is wrong, none are added and the wrong one is named." />
      <div>
        <Button size="sm" variant="secondary" loading={add.busy} disabled={urls.length === 0} onClick={() => void add.run()}>
          Add {urls.length || ""} {urls.length === 1 ? "lecture" : "lectures"}
        </Button>
      </div>
    </div>
  );
}

function Curriculum({ course, onChanged }: { course: Course; onChanged: () => Promise<void> }) {
  const guard = useStepUp();
  const toast = useToast();
  const [newSection, setNewSection] = useState("");
  const [lessonFor, setLessonFor] = useState<{ moduleId: string; lesson: Lesson | null } | null>(null);
  const [removing, setRemoving] = useState<{ kind: "section" | "lecture"; id: string; title: string } | null>(null);
  const addSection = useSubmit(async () => {
    await guard(() => unwrap(api.POST("/api/v1/admin/courses/{course_id}/modules", { params: { path: { course_id: course.id } }, body: { title: newSection.trim() } })));
    setNewSection("");
    await onChanged();
  });
  const move = async (kind: "modules" | "lessons", ids: string[], from: number, to: number, parent: string) => {
    if (to < 0 || to >= ids.length) return;
    const next = [...ids];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item as string);
    if (kind === "modules") await guard(() => unwrap(api.PUT("/api/v1/admin/courses/{course_id}/modules/order", { params: { path: { course_id: parent } }, body: { ids: next } })));
    else await guard(() => unwrap(api.PUT("/api/v1/admin/modules/{module_id}/lessons/order", { params: { path: { module_id: parent } }, body: { ids: next } })));
    await onChanged();
  };
  const remove = async () => {
    if (!removing) return;
    await guard(() => (removing.kind === "section" ? unwrap(api.DELETE("/api/v1/admin/modules/{module_id}", { params: { path: { module_id: removing.id } } })) : unwrap(api.DELETE("/api/v1/admin/lessons/{lesson_id}", { params: { path: { lesson_id: removing.id } } }))));
    toast.show(`${removing.kind === "section" ? "Section" : "Lecture"} removed`);
    await onChanged();
  };
  const sectionIds = course.modules.map((m) => m.id);
  return (
    <div className="app-stack">
      <p className="body-sm app-muted" style={{ margin: 0 }}>
        Members see the sections and lectures in this order.
      </p>
      {course.modules.map((m, mi) => (
        <Card key={m.id}>
          <div className="app-cluster" style={{ justifyContent: "space-between" }}>
            <h3 className="h4" style={{ margin: 0 }}>
              Section {mi + 1}: {m.title}
            </h3>
            <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
              <Button size="sm" variant="ghost" disabled={mi === 0} onClick={() => void move("modules", sectionIds, mi, mi - 1, course.id)} aria-label={`Move section ${m.title} up`}>
                Up
              </Button>
              <Button size="sm" variant="ghost" disabled={mi === sectionIds.length - 1} onClick={() => void move("modules", sectionIds, mi, mi + 1, course.id)} aria-label={`Move section ${m.title} down`}>
                Down
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setRemoving({ kind: "section", id: m.id, title: m.title })} aria-label={`Remove section ${m.title}`}>
                Remove
              </Button>
            </div>
          </div>
          <ol className="app-stack" style={{ margin: "var(--space-3) 0", paddingLeft: "var(--space-6)", gap: "var(--space-2)" }}>
            {m.lessons.map((l, li) => {
              const ids = m.lessons.map((x) => x.id);
              return (
                <li key={l.id}>
                  <span className="app-cluster" style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
                    <span>
                      {l.title} <span className="caption app-muted">{humanise(l.type)}{l.is_preview ? " · preview" : ""}{l.type === "video" && !l.video_id ? " · no valid link" : ""}</span>
                    </span>
                    <span className="app-cluster" style={{ flexWrap: "nowrap" }}>
                      <Button size="sm" variant="ghost" disabled={li === 0} onClick={() => void move("lessons", ids, li, li - 1, m.id)} aria-label={`Move lecture ${l.title} up`}>
                        Up
                      </Button>
                      <Button size="sm" variant="ghost" disabled={li === ids.length - 1} onClick={() => void move("lessons", ids, li, li + 1, m.id)} aria-label={`Move lecture ${l.title} down`}>
                        Down
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setLessonFor({ moduleId: m.id, lesson: l })} aria-label={`Edit lecture ${l.title}`}>
                        Edit
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setRemoving({ kind: "lecture", id: l.id, title: l.title })} aria-label={`Remove lecture ${l.title}`}>
                        Remove
                      </Button>
                    </span>
                  </span>
                </li>
              );
            })}
          </ol>
          {lessonFor && lessonFor.moduleId === m.id ? (
            <LessonForm
              key={lessonFor.lesson?.id ?? "new"}
              moduleId={m.id}
              lesson={lessonFor.lesson}
              onCancel={() => setLessonFor(null)}
              onDone={async () => {
                setLessonFor(null);
                await onChanged();
              }}
            />
          ) : (
            <div className="app-stack">
              <div>
                <Button size="sm" variant="secondary" onClick={() => setLessonFor({ moduleId: m.id, lesson: null })}>
                  Add a lecture
                </Button>
              </div>
              <BulkLinks moduleId={m.id} onDone={onChanged} />
            </div>
          )}
        </Card>
      ))}
      <FormError error={addSection.error} />
      <div className="app-cluster" style={{ alignItems: "flex-end", flexWrap: "nowrap" }}>
        <div style={{ flex: 1 }}>
          <Input label="New section" value={newSection} onChange={(e) => setNewSection(e.target.value)} />
        </div>
        <Button variant="secondary" loading={addSection.busy} disabled={!newSection.trim()} onClick={() => void addSection.run()}>
          Add section
        </Button>
      </div>
      {removing ? <ConfirmDialog title={`Remove this ${removing.kind}?`} body={`“${removing.title}”${removing.kind === "section" ? " and every lecture in it" : ""} will be deleted.`} confirmLabel="Remove" tone="danger" onConfirm={remove} onClose={() => setRemoving(null)} /> : null}
    </div>
  );
}

function Settings({ id, onSaved }: { id: string; onSaved: () => Promise<void> }) {
  const toast = useToast();
  const guard = useStepUp();
  const existing = useQuery({
    queryKey: ["admin", "course", id, "tagged"],
    queryFn: () => unwrapTagged(api.GET("/api/v1/admin/courses/{course_id}", { params: { path: { course_id: id } } })),
  });
  const [draft, setDraft] = useState<Record<string, string | boolean> | null>(null);
  const [loadedFor, setLoadedFor] = useState("");
  const [cover, setCover] = useState<File | null>(null);
  if (existing.data && loadedFor !== existing.data.etag) {
    const c = existing.data.data;
    setLoadedFor(existing.data.etag);
    setDraft({
      title: c.title,
      subtitle: c.subtitle,
      description: htmlToText(c.description),
      instructor: c.instructor,
      category: c.category,
      level: c.level,
      language: c.language,
      audience: c.audience,
      learn: c.learn_bullets.join("\n"),
      requirements: c.requirements.join("\n"),
      promo_video_url: "",
      enrolment_active: c.enrolment_active,
      open_to_visitors: c.open_to_visitors,
      certificate_enabled: c.certificate_enabled,
    });
  }
  const set = (key: string, value: string | boolean) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const lines = (text: string) => text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const save = useSubmit(async () => {
    if (!draft || !existing.data) return;
    if (cover) {
      const up = await uploadFile(cover, "course_cover");
      await guard(() => unwrap(api.PUT("/api/v1/admin/courses/{course_id}/cover", { params: { path: { course_id: id } }, body: { upload_id: up.id } })));
      setCover(null);
    }
    const body = {
      title: String(draft.title).trim(),
      subtitle: String(draft.subtitle).trim(),
      description: textToHtml(String(draft.description)),
      instructor: String(draft.instructor).trim(),
      category: String(draft.category).trim(),
      level: draft.level as "beginner",
      language: String(draft.language),
      audience: String(draft.audience),
      learn_bullets: lines(String(draft.learn)),
      requirements: lines(String(draft.requirements)),
      ...(String(draft.promo_video_url).trim() ? { promo_video_url: String(draft.promo_video_url).trim() } : {}),
      enrolment_active: Boolean(draft.enrolment_active),
      open_to_visitors: Boolean(draft.open_to_visitors),
      certificate_enabled: Boolean(draft.certificate_enabled),
    };
    const { etag } = await unwrapTagged(api.GET("/api/v1/admin/courses/{course_id}", { params: { path: { course_id: id } } }));
    await guard(() => unwrap(api.PATCH("/api/v1/admin/courses/{course_id}", { params: { path: { course_id: id }, header: { "If-Match": etag } }, body })));
    toast.show("Course saved");
    await onSaved();
  });
  const errors = errorsFrom(save.error).fields;
  if (existing.isPending) return <SkeletonRows />;
  if (existing.isError) return <ErrorState error={existing.error} />;
  if (!draft) return null;
  return (
    <div className="app-stack" style={{ maxWidth: 720 }}>
      <FormError error={save.error} listFields />
      <Input label="Title" value={String(draft.title)} onChange={(e) => set("title", e.target.value)} error={errors.title} />
      <Input label="Subtitle" value={String(draft.subtitle)} onChange={(e) => set("subtitle", e.target.value)} error={errors.subtitle} />
      <Textarea label="What it covers" rows={5} value={String(draft.description)} onChange={(e) => set("description", e.target.value)} error={errors.description} />
      <Textarea label="What learners will learn" rows={4} hint="One point per line, up to 12." value={String(draft.learn)} onChange={(e) => set("learn", e.target.value)} error={errors.learn_bullets} />
      <Textarea label="Requirements" rows={3} hint="One per line." value={String(draft.requirements)} onChange={(e) => set("requirements", e.target.value)} error={errors.requirements} />
      <Textarea label="Who it is for" rows={2} value={String(draft.audience)} onChange={(e) => set("audience", e.target.value)} error={errors.audience} />
      <div className="app-formgrid">
        <Input label="Taught by" value={String(draft.instructor)} onChange={(e) => set("instructor", e.target.value)} error={errors.instructor} />
        <Input label="Category" value={String(draft.category)} onChange={(e) => set("category", e.target.value)} error={errors.category} />
        <Select label="Level" options={LEVELS.map((l) => ({ value: l, label: humanise(l) }))} value={String(draft.level)} onChange={(e) => set("level", e.target.value)} error={errors.level} />
        <Input label="Language code" value={String(draft.language)} onChange={(e) => set("language", e.target.value)} error={errors.language} />
      </div>
      <Input label="Promo video (YouTube link)" value={String(draft.promo_video_url)} hint="Leave blank to keep the current one." onChange={(e) => set("promo_video_url", e.target.value)} error={errors.promo_video_url} />
      <div className="wo-field">
        <label className="wo-label" htmlFor="settings-cover">
          Replace the thumbnail
        </label>
        <input id="settings-cover" type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setCover(e.target.files?.[0] ?? null)} />
      </div>
      <Checkbox label="Open for enrolment" checked={Boolean(draft.enrolment_active)} onChange={(e) => set("enrolment_active", e.target.checked)} />
      <Checkbox label="Visitors can read it without joining" checked={Boolean(draft.open_to_visitors)} onChange={(e) => set("open_to_visitors", e.target.checked)} />
      <Checkbox label="Give a certificate on completion" checked={Boolean(draft.certificate_enabled)} onChange={(e) => set("certificate_enabled", e.target.checked)} />
      <div>
        <Button loading={save.busy} disabled={!String(draft.title).trim()} onClick={() => void save.run()}>
          Save changes
        </Button>
      </div>
    </div>
  );
}

/** One course: its state, what is left before it can be published, and a tab for each thing to manage. */
export default function CourseManage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const client = useQueryClient();
  const guard = useStepUp();
  const toast = useToast();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState<"unpublish" | "delete" | null>(null);
  const tab = TABS.some((t) => t.id === params.get("tab")) ? (params.get("tab") as string) : "curriculum";
  const query = useQuery({ queryKey: ["admin", "course", id], queryFn: () => unwrap(api.GET("/api/v1/admin/courses/{course_id}", { params: { path: { course_id: id } } })) });
  const course = query.data;
  useDocumentTitle(course ? `Manage ${course.title}` : "Course");
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["admin", "course", id] });
    await client.invalidateQueries({ queryKey: ["admin", "courses"] });
  };
  const publish = useSubmit(async (unlisted: boolean) => {
    await guard(() => unwrap(api.POST("/api/v1/admin/courses/{course_id}/publish", { params: { path: { course_id: id } }, body: { unlisted } })));
    toast.show(unlisted ? "Course published by link only" : "Course published");
    await refresh();
  });

  if (query.isPending) return <SkeletonRows />;
  if (query.isError || !course) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const live = course.status !== "draft";
  const todo = course.checklist.filter((c) => !c.done);
  return (
    <>
      <p>
        <Link className="wo-linkbtn" to="/admin/courses">
          <ArrowLeft size={16} strokeWidth={1.5} aria-hidden="true" /> All courses
        </Link>
      </p>
      <header className="app-cluster" style={{ justifyContent: "space-between", alignItems: "flex-start", margin: "var(--space-4) 0 var(--space-6)" }}>
        <div>
          <p className="caption app-muted" style={{ margin: 0 }}>
            Course · edited {formatDate(course.edited_at ?? course.created_at)}
          </p>
          <h1 className="h2" style={{ margin: "var(--space-1) 0" }}>
            {course.title}
          </h1>
          <div className="app-cluster">
            <StatusChip tone={course.status === "published" ? "success" : course.status === "unlisted" ? "info" : "neutral"}>{humanise(course.status)}</StatusChip>
            <span className="body-sm app-muted">
              {course.lesson_count} lectures · {course.learners_count} learners
            </span>
          </div>
        </div>
        <div className="app-cluster">
          <a className="wo-btn wo-btn--secondary" href={`/app/learn/courses/${course.slug}`} target="_blank" rel="noreferrer">
            View as a learner <ExternalLink size={14} strokeWidth={1.5} aria-hidden="true" />
          </a>
          {live ? (
            <Button variant="secondary" onClick={() => setConfirm("unpublish")}>
              Take down
            </Button>
          ) : (
            <>
              <Button variant="ghost" onClick={() => setConfirm("delete")}>
                Delete draft
              </Button>
              <Button variant="secondary" loading={publish.busy} disabled={todo.length > 0} onClick={() => void publish.run(true)}>
                Publish by link only
              </Button>
              <Button loading={publish.busy} disabled={todo.length > 0} onClick={() => void publish.run(false)}>
                Publish
              </Button>
            </>
          )}
        </div>
      </header>
      <FormError error={publish.error} />
      {!live && todo.length > 0 ? (
        <Alert tone="warning" title="Before this can be published">
          <ul style={{ margin: 0, paddingLeft: "var(--space-5)" }}>
            {todo.map((c) => (
              <li key={c.key}>{c.text}</li>
            ))}
          </ul>
        </Alert>
      ) : null}
      <div className="app-tabs-scroll" style={{ margin: "var(--space-6) 0" }}>
        <Tabs
          label="Course sections"
          value={tab}
          onChange={(next) => setParams({ tab: next }, { replace: true })}
          items={TABS.map((t) => ({ id: t.id, label: t.id === "requests" && course.pending_requests ? `Requests (${course.pending_requests})` : t.label }))}
        />
      </div>
      <div role="tabpanel" aria-label={TABS.find((t) => t.id === tab)?.label}>
        {tab === "curriculum" ? <Curriculum course={course} onChanged={refresh} /> : null}
        {tab === "learners" ? <Learners courseId={id} slug={course.slug} /> : null}
        {tab === "requests" ? <Requests courseId={id} /> : null}
        {tab === "reviews" ? <Reviews courseId={id} /> : null}
        {tab === "questions" ? <Questions courseId={id} /> : null}
        {tab === "announcements" ? <Announcements courseId={id} /> : null}
        {tab === "settings" ? <Settings id={id} onSaved={refresh} /> : null}
      </div>
      {confirm === "unpublish" ? (
        <ConfirmDialog
          title="Take this course down?"
          body="New members cannot enrol. People already learning keep their progress."
          confirmLabel="Take down"
          tone="danger"
          onConfirm={async () => {
            await guard(() => unwrap(api.POST("/api/v1/admin/courses/{course_id}/unpublish", { params: { path: { course_id: id } } })));
            toast.show("Course taken down");
            await refresh();
          }}
          onClose={() => setConfirm(null)}
        />
      ) : null}
      {confirm === "delete" ? (
        <ConfirmDialog
          title="Delete this draft?"
          body="The draft and its lectures are deleted for good."
          confirmLabel="Delete"
          tone="danger"
          onConfirm={async () => {
            await guard(() => unwrap(api.DELETE("/api/v1/admin/courses/{course_id}", { params: { path: { course_id: id } } })));
            toast.show("Course deleted");
            await client.invalidateQueries({ queryKey: ["admin", "courses"] });
            navigate("/admin/courses");
          }}
          onClose={() => setConfirm(null)}
        />
      ) : null}
    </>
  );
}
