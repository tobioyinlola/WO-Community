import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import { Alert, Button, Checkbox, Input, Select, Textarea } from "../components";
import { uploadFile } from "../api/upload";
import { textToHtml } from "../lib/html";
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
const CURRENCIES = [
  { value: "NGN", label: "Naira (NGN)" },
  { value: "USD", label: "US dollar (USD)" },
];
const STEPS = ["Basics", "Lectures", "Pricing and access", "Review"] as const;

interface Draft {
  title: string;
  subtitle: string;
  description: string;
  instructor: string;
  category: string;
  level: string;
  language: string;
  links: string;
  paid: boolean;
  price: string;
  currency: string;
  open_to_visitors: boolean;
  certificate_enabled: boolean;
  publish: boolean;
  cover: File | null;
}

const BLANK: Draft = {
  title: "",
  subtitle: "",
  description: "",
  instructor: "",
  category: "",
  level: "beginner",
  language: "en",
  links: "",
  paid: false,
  price: "",
  currency: "NGN",
  open_to_visitors: false,
  certificate_enabled: true,
  publish: false,
  cover: null,
};

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
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const dirty = JSON.stringify({ ...draft, cover: draft.cover?.name }) !== JSON.stringify({ ...BLANK, cover: undefined });

  const categories = useQuery({ queryKey: ["course-categories"], queryFn: () => unwrap(api.GET("/api/v1/courses/categories")) });
  const links = linesOf(draft.links);
  const price = Number(draft.price);

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
      : step === 2 && draft.paid && !(price > 0)
        ? "Enter a price above zero."
        : "";

  const checked = useQuery({
    queryKey: ["youtube-check", links[0] ?? ""],
    enabled: step === 1 && links.length > 0,
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
            access: draft.paid ? "paid" : "free",
            ...(draft.paid ? { price_minor: Math.round(price * 100), currency: draft.currency } : {}),
            open_to_visitors: !draft.paid && draft.open_to_visitors,
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
      if (links.length > 0) {
        const section = await guard(() => unwrap(api.POST("/api/v1/admin/courses/{course_id}/modules", { params: { path: { course_id: course.id } }, body: { title: "Section 1" } })));
        await guard(() => unwrap(api.POST("/api/v1/admin/modules/{module_id}/lessons/bulk", { params: { path: { module_id: section.id } }, body: { urls: links } })));
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
            <Button disabled={Boolean(problem)} onClick={() => setStep(step + 1)}>
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
              <p className="wo-hint">A course needs one to be published. JPEG, PNG or WebP.</p>
            </div>
            <datalist id="course-categories">
              {(categories.data?.categories ?? []).map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </>
        ) : null}

        {step === 1 ? (
          <>
            <Textarea
              label="YouTube links, one per line"
              rows={8}
              hint="Each link becomes a lecture, in this order, with its title taken from YouTube. You can add sections, reorder and edit on the course page afterwards."
              value={draft.links}
              onChange={(e) => set("links", e.target.value)}
              error={errors.urls}
            />
            <p className="body-sm app-muted" style={{ margin: 0 }}>
              {links.length === 0 ? "No lectures yet. You can add them later." : `${links.length} ${links.length === 1 ? "lecture" : "lectures"} will be added.`}
            </p>
            {links.length > 0 && checked.isPending ? <p className="body-sm app-muted">Checking the first link…</p> : null}
            {checked.isError ? (
              <Alert tone="danger" title="The first link is not a YouTube video">
                {messageOf(checked.error)}
              </Alert>
            ) : null}
            {checked.data ? (
              <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
                <img src={checked.data.thumbnail} alt="" width={96} height={54} style={{ borderRadius: "var(--radius-md)" }} />
                <span className="body-sm">{checked.data.title || "First lecture found"}</span>
              </div>
            ) : null}
          </>
        ) : null}

        {step === 2 ? (
          <>
            <Checkbox label="This is a paid course" checked={draft.paid} onChange={(e) => set("paid", e.target.checked)} />
            {draft.paid ? (
              <>
                <div className="app-formgrid">
                  <Input label="Price" type="number" min={1} step="any" value={draft.price} onChange={(e) => set("price", e.target.value)} error={errors.price_minor} />
                  <Select label="Currency" options={CURRENCIES} value={draft.currency} onChange={(e) => set("currency", e.target.value)} error={errors.currency} />
                </div>
                <Alert tone="info" title="Payments are not switched on">
                  Members will ask for access and you approve each request. The price is shown so they know what it is.
                </Alert>
              </>
            ) : (
              <Checkbox label="Visitors can read it without joining" checked={draft.open_to_visitors} onChange={(e) => set("open_to_visitors", e.target.checked)} />
            )}
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
              <dt>Lectures</dt>
              <dd>{links.length}</dd>
              <dt>Price</dt>
              <dd>{draft.paid ? `${draft.currency} ${price.toLocaleString()} (requests, while payments are off)` : "Free"}</dd>
              <dt>Thumbnail</dt>
              <dd>{draft.cover ? draft.cover.name : "None yet"}</dd>
              <dt>Certificate</dt>
              <dd>{draft.certificate_enabled ? "Yes" : "No"}</dd>
            </dl>
            <Checkbox label="Publish as soon as it is created" checked={draft.publish} onChange={(e) => set("publish", e.target.checked)} />
            <p className="body-sm app-muted" style={{ margin: 0 }}>
              {draft.publish ? "A course needs a cover, a description and at least one lecture to publish. If something is missing it stays a draft and the course page lists what to do." : "It starts as a draft only editors can see."}
            </p>
          </>
        ) : null}
      </div>
    </Drawer>
  );
}
