import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import { Alert, Badge, Button, Checkbox, Input, Select, Textarea } from "../components";
import { uploadFile } from "../api/upload";
import { textToHtml } from "../lib/html";
import "../styles/learn.css";
import { Drawer } from "../ui/Drawer";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { useStepUp } from "./StepUp";

const LEVELS = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
  { value: "all", label: "All levels" },
];
const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "fr", label: "French" },
  { value: "yo", label: "Yoruba" },
  { value: "ha", label: "Hausa" },
  { value: "ig", label: "Igbo" },
];
const STEPS = ["Details", "Modules and videos", "Pricing", "Review"] as const;

/** What the server accepts too: youtube.com/watch, youtu.be, /embed and /shorts, and no other host. */
export function youtubeId(link: string): string | null {
  let url: URL;
  try {
    url = new URL(link.trim());
  } catch {
    return null;
  }
  const host = url.hostname.replace(/^(www|m)\./, "");
  const valid = (id: string | null | undefined) => (id && /^[A-Za-z0-9_-]{11}$/.test(id) ? id : null);
  if (host === "youtu.be") return valid(url.pathname.slice(1).split("/")[0]);
  if (host !== "youtube.com" && host !== "youtube-nocookie.com") return null;
  if (url.pathname === "/watch") return valid(url.searchParams.get("v"));
  const match = url.pathname.match(/^\/(embed|shorts)\/([^/]+)/);
  return match ? valid(match[2]) : null;
}

interface ModuleDraft {
  key: number;
  title: string;
  links: string;
}

interface Draft {
  title: string;
  subtitle: string;
  description: string;
  instructor: string;
  category: string;
  level: string;
  language: string;
  outcomes: string;
  open_to_visitors: boolean;
  certificate_enabled: boolean;
  publish: boolean;
  cover: File | null;
}

const firstModule = (): ModuleDraft => ({ key: 1, title: "Module 1", links: "" });

const BLANK: Draft = {
  title: "",
  subtitle: "",
  description: "",
  instructor: "",
  category: "",
  level: "beginner",
  language: "en",
  outcomes: "",
  open_to_visitors: false,
  certificate_enabled: true,
  publish: false,
  cover: null,
};

function move<T>(items: T[], index: number, by: -1 | 1): T[] {
  const next = [...items];
  const target = index + by;
  if (target < 0 || target >= next.length) return next;
  [next[index], next[target]] = [next[target] as T, next[index] as T];
  return next;
}

const linesOf = (text: string) => text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);

/**
 * The Add course wizard, in a right-hand drawer: basics, lectures from pasted YouTube links, price and
 * access, then a review. The course is created as a draft when the last step is confirmed, and published
 * only if asked.
 */
export function AddCourse({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const toast = useToast();
  const guard = useStepUp();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(BLANK);
  const [modules, setModules] = useState<ModuleDraft[]>([firstModule()]);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const dirty =
    JSON.stringify({ ...draft, cover: draft.cover?.name }) !== JSON.stringify({ ...BLANK, cover: undefined }) ||
    modules.length > 1 ||
    modules.some((m) => m.links.trim() !== "");

  const categories = useQuery({ queryKey: ["course-categories"], queryFn: () => unwrap(api.GET("/api/v1/courses/categories")) });
  // Each module's links, checked as they are typed: the line number and what is wrong.
  const checkedModules = modules.map((m) => {
    const lines = linesOf(m.links);
    return { ...m, lines, bad: lines.map((l, i) => (youtubeId(l) ? null : i + 1)).filter((n): n is number => n !== null) };
  });
  const links = checkedModules.flatMap((m) => m.lines);
  const badLinks = checkedModules.some((m) => m.bad.length > 0);

  // What stops the next step, said in words rather than by a dead button.
  const problem =
    step === 0
      ? !draft.title.trim()
        ? "Give the course a title."
        : !draft.description.trim()
          ? "Say what the course covers."
          : !draft.category.trim()
            ? "Choose or type a category."
            : ""
      : step === 1 && badLinks
        ? "Fix the links marked below. Only YouTube links work."
        : step === 1 && links.length === 0
          ? "Add at least one YouTube link to publish. You can also save a draft without one."
          : "";
  const blocked = step === 0 ? Boolean(problem) : step === 1 ? badLinks : false;

  const checked = useQuery({
    queryKey: ["youtube-check", links[0] ?? ""],
    enabled: step === 1 && links.length > 0 && !badLinks,
    retry: false,
    queryFn: () => unwrap(api.POST("/api/v1/admin/youtube/validate", { body: { url: links[0] ?? "" } })),
  });

  const create = useSubmit(async () => {
    const course = await guard(() =>
      unwrap(
        api.POST("/api/v1/admin/courses", {
          body: {
            title: draft.title.trim(),
            subtitle: draft.subtitle.trim(),
            description: textToHtml(draft.description),
            instructor: draft.instructor.trim() || "WO Community faculty",
            category: draft.category.trim(),
            level: draft.level as "beginner",
            language: draft.language,
            access: "free",
            learn_bullets: linesOf(draft.outcomes),
            open_to_visitors: draft.open_to_visitors,
            certificate_enabled: draft.certificate_enabled,
          },
        }),
      ),
    );
    try {
      if (draft.cover) {
        const cover = await uploadFile(draft.cover, "course_cover");
        await guard(() => unwrap(api.PUT("/api/v1/admin/courses/{course_id}/cover", { params: { path: { course_id: course.id } }, body: { upload_id: cover.id } })));
      }
      for (const m of checkedModules) {
        if (m.lines.length === 0 && checkedModules.length > 1) continue;
        const section = await guard(() => unwrap(api.POST("/api/v1/admin/courses/{course_id}/modules", { params: { path: { course_id: course.id } }, body: { title: m.title.trim() || "Module" } })));
        if (m.lines.length > 0) await guard(() => unwrap(api.POST("/api/v1/admin/modules/{module_id}/lessons/bulk", { params: { path: { module_id: section.id } }, body: { urls: m.lines } })));
      }
      if (draft.publish) await guard(() => unwrap(api.POST("/api/v1/admin/courses/{course_id}/publish", { params: { path: { course_id: course.id } } })));
    } catch (error) {
      // The draft exists; say what stopped the rest and let the editor finish it on the course page.
      toast.show(`Draft created, but ${messageOf(error)}`);
      onCreated(course.id);
      return;
    }
    toast.show(draft.publish ? "Course published" : "Draft created");
    onCreated(course.id);
  });
  const errors = errorsFrom(create.error).fields;
  const last = step === STEPS.length - 1;

  return (
    <Drawer
      open
      onOpenChange={(open) => !open && onClose()}
      size="lg"
      eyebrow="Courses"
      title="Add course"
      subtitle={`Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}`}
      dirty={dirty}
      footer={
        <>
          {step > 0 ? (
            <Button variant="ghost" onClick={() => setStep(step - 1)}>
              Back
            </Button>
          ) : (
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          )}
          {last ? (
            <Button loading={create.busy} onClick={() => void create.run()}>
              {draft.publish ? "Create and publish" : "Create draft"}
            </Button>
          ) : (
            <Button disabled={blocked} onClick={() => setStep(step + 1)}>
              Continue
            </Button>
          )}
        </>
      }
    >
      <ol className="wo-steps" aria-label="Progress">
        {STEPS.map((name, i) => (
          <li key={name} aria-current={i === step ? "step" : undefined} data-done={i < step}>
            <span className="wo-steps__n">{i + 1}</span>
            <span className="wo-steps__t">{name}</span>
          </li>
        ))}
      </ol>
      <div className="app-stack">
        <FormError error={create.error} />
        {problem ? (
          <p className="body-sm app-muted" role="status" style={{ margin: 0 }}>
            {problem}
          </p>
        ) : null}

        {step === 0 ? (
          <>
            <Input label="Title" value={draft.title} maxLength={160} onChange={(e) => set("title", e.target.value)} error={errors.title} />
            <Input label="Subtitle (optional)" value={draft.subtitle} maxLength={180} hint="One line under the title on the course page." onChange={(e) => set("subtitle", e.target.value)} error={errors.subtitle} />
            <Textarea label="What it covers" rows={5} hint="Leave a blank line between paragraphs." value={draft.description} onChange={(e) => set("description", e.target.value)} error={errors.description} />
            <div className="app-formgrid">
              <Input label="Taught by" value={draft.instructor} placeholder="WO Community faculty" onChange={(e) => set("instructor", e.target.value)} error={errors.instructor} />
              <Input label="Category" list="course-categories" value={draft.category} onChange={(e) => set("category", e.target.value)} error={errors.category} />
              <Select label="Level" options={LEVELS} value={draft.level} onChange={(e) => set("level", e.target.value)} error={errors.level} />
              <Select label="Language" options={LANGUAGES} value={draft.language} onChange={(e) => set("language", e.target.value)} error={errors.language} />
            </div>
            <div className="wo-field">
              <label className="wo-label" htmlFor="add-cover">
                Thumbnail image
              </label>
              <input id="add-cover" type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => set("cover", e.target.files?.[0] ?? null)} />
              <p className="wo-hint">Optional. JPEG, PNG or WebP.</p>
            </div>
            <Textarea label="What members will learn (optional)" rows={3} hint="One outcome per line." value={draft.outcomes} onChange={(e) => set("outcomes", e.target.value)} />
            <datalist id="course-categories">
              {(categories.data?.categories ?? []).map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </>
        ) : null}

        {step === 1 ? (
          <>
            <p className="body-sm app-muted" style={{ margin: 0 }}>
              Paste one YouTube link per line. Each link becomes a lesson in this module, titled from the video. One module
              with one link is a complete course. You can reorder, retitle and add notes on the course page afterwards.
            </p>
            {checkedModules.map((m, index) => (
              <fieldset key={m.key} className="wo-box" style={{ display: "grid", gap: "var(--space-3)", margin: 0 }}>
                <legend className="wo-learn__h3">Module {index + 1}</legend>
                <Input label="Module title" value={m.title} maxLength={120} onChange={(e) => setModules((all) => all.map((x) => (x.key === m.key ? { ...x, title: e.target.value } : x)))} />
                <Textarea
                  label={`YouTube links for module ${index + 1}`}
                  rows={4}
                  placeholder="https://youtu.be/..."
                  value={m.links}
                  onChange={(e) => setModules((all) => all.map((x) => (x.key === m.key ? { ...x, links: e.target.value } : x)))}
                  error={m.bad.length > 0 ? `${m.bad.length === 1 ? `Line ${m.bad[0]} is` : `Lines ${m.bad.join(", ")} are`} not a YouTube link. Use youtube.com/watch, youtu.be, embed or shorts links.` : undefined}
                />
                <div className="app-cluster">
                  <span className="body-sm app-muted">
                    {m.lines.length === 0 ? "No lessons yet" : `${m.lines.length} ${m.lines.length === 1 ? "lesson" : "lessons"}`}
                  </span>
                  <Button variant="ghost" size="sm" disabled={index === 0} aria-label={`Move module ${index + 1} up`} onClick={() => setModules((all) => move(all, index, -1))}>
                    Up
                  </Button>
                  <Button variant="ghost" size="sm" disabled={index === modules.length - 1} aria-label={`Move module ${index + 1} down`} onClick={() => setModules((all) => move(all, index, 1))}>
                    Down
                  </Button>
                  {modules.length > 1 ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Delete module ${index + 1}`}
                      onClick={() => {
                        if (window.confirm(`Delete module ${index + 1}${m.lines.length ? ` and its ${m.lines.length} lessons` : ""}?`)) setModules((all) => all.filter((x) => x.key !== m.key));
                      }}
                    >
                      Delete module
                    </Button>
                  ) : null}
                </div>
              </fieldset>
            ))}
            <div>
              <Button variant="secondary" onClick={() => setModules((all) => [...all, { key: Math.max(...all.map((x) => x.key)) + 1, title: `Module ${all.length + 1}`, links: "" }])}>
                Add module
              </Button>
            </div>
            {links.length > 0 && !badLinks && checked.isPending ? <p className="body-sm app-muted">Checking the first link…</p> : null}
            {checked.isError ? (
              <Alert tone="danger" title="The first link could not be found on YouTube">
                {messageOf(checked.error)}
              </Alert>
            ) : null}
            {checked.data ? (
              <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
                <img src={checked.data.thumbnail} alt="" width={96} height={54} style={{ borderRadius: "var(--radius-md)" }} />
                <span className="body-sm">{checked.data.title || "First lesson found"}</span>
              </div>
            ) : null}
          </>
        ) : null}

        {step === 2 ? (
          <>
            <fieldset className="wo-box" style={{ display: "grid", gap: "var(--space-3)", margin: 0 }}>
              <legend className="wo-learn__h3">Price</legend>
              <label className="app-cluster">
                <input type="radio" name="pricing" checked readOnly /> Free
              </label>
              <label className="app-cluster app-muted">
                <input type="radio" name="pricing" disabled /> Paid <Badge>Coming soon</Badge>
              </label>
              <p className="body-sm app-muted" style={{ margin: 0 }}>
                Every course is free for now. The course keeps a pricing model, so paid courses can be switched on later.
              </p>
            </fieldset>
            <Checkbox label="Visitors can read it without joining" checked={draft.open_to_visitors} onChange={(e) => set("open_to_visitors", e.target.checked)} />
            <Checkbox label="Give a certificate on completion" checked={draft.certificate_enabled} onChange={(e) => set("certificate_enabled", e.target.checked)} />
          </>
        ) : null}

        {step === 3 ? (
          <>
            <dl className="wo-review">
              <dt>Title</dt>
              <dd>{draft.title}</dd>
              <dt>Category</dt>
              <dd>
                {draft.category} · {LEVELS.find((l) => l.value === draft.level)?.label} · {LANGUAGES.find((l) => l.value === draft.language)?.label}
              </dd>
              <dt>Modules</dt>
              <dd>{checkedModules.filter((m) => m.lines.length > 0 || checkedModules.length === 1).length}</dd>
              <dt>Lessons</dt>
              <dd>{links.length}</dd>
              <dt>Price</dt>
              <dd>Free</dd>
              <dt>Cover image</dt>
              <dd>{draft.cover ? draft.cover.name : "None (optional)"}</dd>
              <dt>Certificate</dt>
              <dd>{draft.certificate_enabled ? "Yes" : "No"}</dd>
            </dl>
            <ul style={{ margin: 0, paddingLeft: "var(--space-5)" }} aria-label="Checklist">
              <li>{draft.title.trim() ? "Title: done" : "Title: missing"}</li>
              <li>{draft.description.trim() ? "Description: done" : "Description: missing"}</li>
              <li>{draft.category.trim() ? "Category: done" : "Category: missing"}</li>
              <li>{links.length > 0 ? "At least one lesson with a YouTube link: done" : "At least one lesson with a YouTube link: missing, so it stays a draft"}</li>
            </ul>
            <Checkbox label="Publish as soon as it is created" checked={draft.publish} onChange={(e) => set("publish", e.target.checked)} />
            <p className="body-sm app-muted" style={{ margin: 0 }}>
              {draft.publish ? "Publishing makes it live for members straight away. If something is missing it stays a draft and the course page lists what to do." : "It starts as a draft only editors can see. Use View as a learner on the course page to preview it."}
            </p>
          </>
        ) : null}
      </div>
    </Drawer>
  );
}
