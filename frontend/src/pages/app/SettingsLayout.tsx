import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../../auth/AuthProvider";
import "../../styles/mentor.css";

/** Settings with a vertical list of sections beside it. Mentorship appears once a member is an approved mentor. */
export default function SettingsLayout() {
  const { me } = useAuth();
  const mentor = me?.roles.includes("mentor") ?? false;
  const links = [
    { to: "/app/settings", label: "Privacy and notifications", end: true },
    ...(mentor ? [{ to: "/app/settings/mentorship", label: "Mentorship", end: false }] : []),
  ];
  return (
    <div className="wo-settings">
      <nav className="wo-settings__nav" aria-label="Settings sections">
        <ul>
          {links.map((l) => (
            <li key={l.to}>
              <NavLink to={l.to} end={l.end}>
                {l.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="wo-settings__body">
        <Outlet />
      </div>
    </div>
  );
}
