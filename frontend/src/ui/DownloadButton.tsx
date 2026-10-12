import { useState, type ReactNode } from "react";
import { downloadFile } from "../api/client";
import { messageOf } from "../api/errors";
import { Button, type ButtonProps } from "../components";
import { useToast } from "./Toast";

interface Props extends Omit<ButtonProps, "onClick" | "children"> {
  path: string;
  filename: string;
  children: ReactNode;
}

/** A button that downloads a file the API only serves to signed in members. */
export function DownloadButton({ path, filename, children, ...rest }: Props) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      {...rest}
      loading={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await downloadFile(path, filename);
        } catch (error) {
          toast.show(messageOf(error));
        } finally {
          setBusy(false);
        }
      }}
    >
      {children}
    </Button>
  );
}
