import { ChevronDown } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import "../styles/learn.css";

export interface AccordionItem {
  id: string;
  title: ReactNode;
  /** A short line beside the title, such as "4 lectures · 32 min". */
  meta?: ReactNode;
  content: ReactNode;
}

/**
 * Sections that open and close. Each header is a button that says whether it is open, and the panel
 * it controls follows it. `defaultOpen` lists the ones open at first.
 */
export function Accordion({ items, defaultOpen = [], allowMultiple = true }: { items: AccordionItem[]; defaultOpen?: string[]; allowMultiple?: boolean }) {
  const base = useId();
  const [open, setOpen] = useState<string[]>(defaultOpen);
  const toggle = (id: string) =>
    setOpen((current) => (current.includes(id) ? current.filter((x) => x !== id) : allowMultiple ? [...current, id] : [id]));
  return (
    <div className="wo-accordion">
      {items.map((item) => {
        const isOpen = open.includes(item.id);
        const panel = `${base}-${item.id}`;
        return (
          <section key={item.id} className="wo-accordion__item" data-open={isOpen}>
            <h3 className="wo-accordion__head">
              <button type="button" className="wo-accordion__button" aria-expanded={isOpen} aria-controls={panel} onClick={() => toggle(item.id)}>
                <ChevronDown size={18} strokeWidth={1.5} aria-hidden="true" className="wo-accordion__chevron" />
                <span className="wo-accordion__title">{item.title}</span>
                {item.meta ? <span className="wo-accordion__meta">{item.meta}</span> : null}
              </button>
            </h3>
            <div id={panel} role="region" aria-label={typeof item.title === "string" ? item.title : undefined} hidden={!isOpen} className="wo-accordion__panel">
              {item.content}
            </div>
          </section>
        );
      })}
    </div>
  );
}
