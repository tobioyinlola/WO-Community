import { useRef, type KeyboardEvent } from "react";

interface Option<T extends string> {
  value: T;
  label: string;
}

/** A row of choices where exactly one is on, switching what the panel below shows. Arrow keys move between them. */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  idPrefix,
  controls = true,
}: {
  label: string;
  options: Array<Option<T>>;
  value: T;
  onChange: (next: T) => void;
  /** Ids the panel can point back at with `aria-labelledby`. */
  idPrefix: string;
  /** False when no panel with the matching id is on the page (a specimen). */
  controls?: boolean;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const move = (event: KeyboardEvent, index: number) => {
    const last = options.length - 1;
    const next = event.key === "ArrowRight" ? (index === last ? 0 : index + 1) : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1) : event.key === "Home" ? 0 : event.key === "End" ? last : -1;
    if (next < 0) return;
    event.preventDefault();
    const target = options[next];
    if (target) {
      onChange(target.value);
      refs.current[next]?.focus();
    }
  };
  return (
    <div role="tablist" aria-label={label} className="adm-seg">
      {options.map((option, index) => (
        <button
          key={option.value}
          ref={(el) => {
            refs.current[index] = el;
          }}
          type="button"
          role="tab"
          id={`${idPrefix}-${option.value}`}
          aria-selected={option.value === value}
          aria-controls={controls ? `${idPrefix}-panel` : undefined}
          tabIndex={option.value === value ? 0 : -1}
          className="adm-seg__tab"
          onClick={() => onChange(option.value)}
          onKeyDown={(e) => move(e, index)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
