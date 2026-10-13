/** A name to greet someone by when there is no profile name: the part of the email before the @. */
export function nameFromEmail(email: string | undefined): string {
  const local = (email ?? "").split("@")[0]?.split(/[._-]/)[0] ?? "";
  return local ? local.charAt(0).toUpperCase() + local.slice(1) : "";
}

/** The dashboard greeting, with a wave when the hour is not late and a moon when it is. */
export function welcomeTitle(name: string, now: Date = new Date()): string {
  const hour = now.getHours();
  const mark = hour >= 5 && hour < 18 ? "👋" : "🌙";
  return name ? `Welcome back, ${name} ${mark}` : `Welcome back ${mark}`;
}
