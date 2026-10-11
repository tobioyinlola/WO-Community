/** What the API sends for every failure (RFC 9457 problem details). */
export interface Problem {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  code?: string;
  errors?: Record<string, unknown>;
}

/** A failed API call, with the problem the server described. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem: Problem;

  constructor(status: number, problem: Problem) {
    super(problem.detail || problem.title || `The request failed (${status}).`);
    this.name = "ApiError";
    this.status = status;
    this.code = problem.code ?? "";
    this.problem = problem;
  }

  get isValidation(): boolean {
    return this.status === 400 && this.code === "validation_error";
  }

  /** Messages per field, flattened to plain strings. Nested problems use dotted keys. */
  get fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    const walk = (value: unknown, path: string) => {
      if (typeof value === "string") {
        out[path] = out[path] ? `${out[path]} ${value}` : value;
      } else if (Array.isArray(value)) {
        for (const item of value) walk(item, path);
      } else if (value && typeof value === "object") {
        for (const [key, inner] of Object.entries(value)) walk(inner, path ? `${path}.${key}` : key);
      }
    };
    walk(this.problem.errors ?? {}, "");
    return out;
  }
}

/** Turns anything thrown into a sentence a member can read. */
export function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return "Too many attempts. Wait a moment, then try again.";
    if (error.status >= 500) return "Something went wrong on our side. Please try again.";
    return error.message;
  }
  if (error instanceof TypeError) return "We could not reach the server. Check your connection.";
  return "Something went wrong. Please try again.";
}

export function isStatus(error: unknown, ...statuses: number[]): boolean {
  return error instanceof ApiError && statuses.includes(error.status);
}
