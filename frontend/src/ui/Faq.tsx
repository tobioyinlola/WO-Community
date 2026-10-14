import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";

export interface FaqItem {
  question: string;
  answer: string;
}

/** Questions that open one at a time. The first is open to begin with. */
export function Faq({ items }: { items: FaqItem[] }) {
  const base = useId();
  const [open, setOpen] = useState<number | null>(0);
  return (
    <div className="site-faq">
      {items.map((item, index) => {
        const isOpen = open === index;
        const buttonId = `${base}-q${index}`;
        const panelId = `${base}-a${index}`;
        return (
          <div key={item.question} className="site-faq__item" data-open={isOpen}>
            <h3 className="site-faq__q">
              <button type="button" id={buttonId} aria-expanded={isOpen} aria-controls={panelId} onClick={() => setOpen(isOpen ? null : index)}>
                <span>{item.question}</span>
                <span className="site-faq__chevron" aria-hidden="true">
                  <ChevronDown size={20} strokeWidth={2} />
                </span>
              </button>
            </h3>
            <div id={panelId} role="region" aria-labelledby={buttonId} className="site-faq__panel">
              <div className="site-faq__inner">
                <p>{item.answer}</p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
