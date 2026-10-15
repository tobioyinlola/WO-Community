/** A name to greet someone by when there is no profile name: the part of the email before the @. */
export function nameFromEmail(email: string | undefined): string {
  const local = (email ?? "").split("@")[0]?.split(/[._-]/)[0] ?? "";
  return local ? local.charAt(0).toUpperCase() + local.slice(1) : "";
}

/** The dashboard greeting for the time of day where the member is: morning, afternoon or evening. */
export function welcomeTitle(name: string, now: Date = new Date()): string {
  const hour = now.getHours();
  const [words, mark] = hour >= 5 && hour < 12 ? ["Good morning", "☀️"] : hour >= 12 && hour < 17 ? ["Good afternoon", "🌤️"] : ["Good evening", "🌙"];
  return name ? `${words}, ${name} ${mark}` : `${words} ${mark}`;
}
