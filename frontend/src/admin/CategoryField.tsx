import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { Input, Select } from "../components";
import { permissionsFor } from "./permissions";

const NEW = "__new__";

/**
 * A course's category: one from the list the admins manage under Lists, or a new name, which joins
 * that list when the course is saved.
 */
export function CategoryField({ value, onChange, error }: { value: string; onChange: (value: string) => void; error?: string }) {
  const { me } = useAuth();
  const canManage = permissionsFor(me?.roles ?? []).has("reference.manage");
  const options = useQuery({ queryKey: ["admin", "course-categories"], queryFn: () => unwrap(api.GET("/api/v1/admin/course-categories")) });
  const names = (options.data ?? []).map((c) => c.name);
  const known = names.some((n) => n.toLowerCase() === value.trim().toLowerCase());
  const [typing, setTyping] = useState(false);
  // A course whose category is not offered any more (retired) keeps it as a choice.
  const shown = value.trim() && !known && !typing ? [...names, value] : names;

  return (
    <div className="app-stack" style={{ gap: "var(--space-2)" }}>
      <Select
        label="Category"
        value={typing ? NEW : value}
        onChange={(e) => {
          if (e.target.value === NEW) {
            setTyping(true);
            onChange("");
          } else {
            setTyping(false);
            onChange(e.target.value);
          }
        }}
        options={[
          { value: "", label: options.isPending ? "Loading categories…" : "Choose a category" },
          ...shown.map((n) => ({ value: n, label: n })),
          { value: NEW, label: "Add a new category…" },
        ]}
        error={typing ? undefined : error}
      />
      {typing ? (
        <Input
          label="New category name"
          maxLength={60}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          error={error}
          hint="It joins the category list when you save the course."
        />
      ) : null}
      {canManage ? (
        <p className="caption app-muted" style={{ margin: 0 }}>
          <Link className="app-link" to="/admin/lists?list=course_categories">Manage course categories</Link>
        </p>
      ) : null}
    </div>
  );
}
