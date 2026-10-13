import { ArrowUpRight } from "lucide-react";

/** The arrow in a circle at the end of a primary button. The circle is sized by the button. */
export function ArrowCircle() {
  return (
    <span className="wo-btn__arrow" aria-hidden="true">
      <ArrowUpRight size={16} strokeWidth={2} />
    </span>
  );
}
