import { Briefcase, CalendarDays, GraduationCap, Home, Megaphone, MessageSquare, Rocket, Trophy, UserCheck, Users } from "lucide-react";
import type { NavEntry } from "../../admin/shell/nav";

/** The member area's map. Entries marked `needs` are shown only to people holding that permission. */
export const MEMBER_NAV: NavEntry[] = [
  { id: "home", label: "Home", to: "/app", icon: Home, end: true },
  { id: "feed", label: "Feed", to: "/app/feed", icon: MessageSquare },
  { id: "directory", label: "Directory", to: "/app/directory", icon: Users },
  { id: "leaderboard", label: "Leaderboard", to: "/app/leaderboard", icon: Trophy },
  { id: "jobs", label: "Jobs", to: "/app/jobs", icon: Briefcase },
  { id: "events", label: "Events", to: "/app/events", icon: CalendarDays },
  { id: "learn", label: "Learn", to: "/app/learn", icon: GraduationCap },
  { id: "mentors", label: "Mentors", to: "/app/mentors", icon: UserCheck },
  { id: "news", label: "News", to: "/app/news", icon: Megaphone },
  { id: "launch", label: "Launch toolkit", to: "/app/launch", icon: Rocket, needs: "toolkit.use" },
];
