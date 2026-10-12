import { Navigate, useSearchParams } from "react-router-dom";
import { rememberRefCode } from "./ref";

/** A shared link, `/join?ref=CODE`. It keeps the code and opens the sign up form. */
export function JoinRedirect() {
  const [params] = useSearchParams();
  const code = (params.get("ref") ?? "").trim().toUpperCase().slice(0, 12);
  if (code) rememberRefCode(code);
  return <Navigate to={code ? `/register?ref=${encodeURIComponent(code)}` : "/register"} replace />;
}
