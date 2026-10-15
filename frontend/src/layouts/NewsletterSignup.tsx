import { useId, useState, type FormEvent } from "react";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";

/** The newsletter sign up in the footer. A link we email confirms it before anything is sent. */
export function NewsletterSignup() {
  const id = useId();
  const [email, setEmail] = useState("");
  const [trap, setTrap] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done">("idle");
  const [problem, setProblem] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setProblem("Enter a full email address.");
      return;
    }
    setState("sending");
    setProblem("");
    try {
      await unwrap(api.POST("/api/v1/newsletter/subscribe", { body: { email: email.trim(), website: trap } }));
      setState("done");
    } catch (error) {
      setProblem(messageOf(error));
      setState("idle");
    }
  };

  return (
    <section className="site-news" aria-labelledby={`${id}-title`}>
      <div>
        <span className="wo-eyebrow">Newsletter</span>
        <h2 className="h3 site-news__title" id={`${id}-title`}>
          Stories, opportunities and events, in your inbox.
        </h2>
        <p className="body site-news__lead">
          What is happening across Africa&rsquo;s founder, operator and investor community. No noise; leave whenever you like.
        </p>
      </div>
      {state === "done" ? (
        <p className="site-news__done" role="status">
          Almost there. Check your inbox and open the link to confirm your subscription.
        </p>
      ) : (
        <form className="site-news__form" onSubmit={submit} noValidate>
          <label className="wo-visually-hidden" htmlFor={`${id}-email`}>
            Email address
          </label>
          <input
            id={`${id}-email`}
            className="site-news__input"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={problem ? true : undefined}
            aria-describedby={problem ? `${id}-problem` : undefined}
          />
          {/* Hidden from people; a bot that fills it in is ignored. */}
          <input
            className="site-news__trap"
            type="text"
            name="website"
            tabIndex={-1}
            autoComplete="off"
            aria-hidden="true"
            value={trap}
            onChange={(e) => setTrap(e.target.value)}
          />
          <button type="submit" className="wo-btn wo-btn--accent" disabled={state === "sending"}>
            {state === "sending" ? "Subscribing…" : "Subscribe"}
          </button>
          {problem ? (
            <p className="site-news__problem" id={`${id}-problem`} role="alert">
              {problem}
            </p>
          ) : null}
        </form>
      )}
    </section>
  );
}
