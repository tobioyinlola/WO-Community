import { Bold, Italic, Link2, List } from "lucide-react";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import "../../styles/shared-ui.css";

export interface RichEditorHandle {
  /** Adds saved text where the cursor is (or at the end). */
  insert: (html: string) => void;
  clear: () => void;
  focus: () => void;
}

interface Props {
  label: string;
  onChange: (html: string, isEmpty: boolean) => void;
  /** Words shown while it is empty. */
  placeholder?: string;
  disabled?: boolean;
  /** Text to start with, for editing something saved. Read once, when it first appears. */
  initialHtml?: string;
}

const TOOLS = [
  { id: "bold", label: "Bold", icon: Bold, run: () => document.execCommand("bold") },
  { id: "italic", label: "Italic", icon: Italic, run: () => document.execCommand("italic") },
  { id: "list", label: "Bulleted list", icon: List, run: () => document.execCommand("insertUnorderedList") },
  {
    id: "link",
    label: "Add link",
    icon: Link2,
    run: () => {
      const address = window.prompt("Link address, starting with https://");
      if (address && /^https?:\/\//i.test(address.trim())) document.execCommand("createLink", false, address.trim());
    },
  },
];

/**
 * A light text box for replies: bold, italic, a list and a link. Pasted text is kept as plain text,
 * and the server cleans what is sent, so nothing but those four things can get through.
 */
export const RichEditor = forwardRef<RichEditorHandle, Props>(function RichEditor({ label, onChange, placeholder, disabled = false, initialHtml = "" }, ref) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (box.current && initialHtml) box.current.innerHTML = initialHtml;
    // Only once: after that the person is typing and the text is theirs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const report = () => {
    const el = box.current;
    if (!el) return;
    const empty = (el.textContent ?? "").trim() === "" && !el.querySelector("li");
    onChange(empty ? "" : el.innerHTML, empty);
  };

  useImperativeHandle(ref, () => ({
    insert: (html) => {
      const el = box.current;
      if (!el) return;
      el.focus();
      document.execCommand("insertHTML", false, html);
      report();
    },
    clear: () => {
      if (box.current) box.current.innerHTML = "";
      report();
    },
    focus: () => box.current?.focus(),
  }));

  return (
    <div className="wo-rich" data-disabled={disabled}>
      <div className="wo-rich__bar" role="toolbar" aria-label={`${label} formatting`}>
        {TOOLS.map(({ id, label: name, icon: Icon, run }) => (
          <button
            key={id}
            type="button"
            className="wo-rich__tool"
            aria-label={name}
            title={name}
            disabled={disabled}
            // Keep the selection in the text box when the button is pressed.
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              box.current?.focus();
              run();
              report();
            }}
          >
            <Icon size={16} strokeWidth={1.5} aria-hidden="true" />
          </button>
        ))}
      </div>
      <div
        ref={box}
        className="wo-rich__box app-richtext"
        role="textbox"
        aria-multiline="true"
        aria-label={label}
        data-placeholder={placeholder}
        contentEditable={!disabled}
        suppressContentEditableWarning
        tabIndex={0}
        onInput={report}
        onPaste={(event) => {
          event.preventDefault();
          document.execCommand("insertText", false, event.clipboardData.getData("text/plain"));
        }}
      />
    </div>
  );
});
