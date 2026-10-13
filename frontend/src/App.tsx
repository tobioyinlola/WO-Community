import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { isStatus } from "./api/errors";
import { AuthProvider } from "./auth/AuthProvider";
import { GuestOnly, RequireAuth } from "./auth/guards";
import { AppLayout } from "./layouts/AppLayout";
import { SearchPage } from "./shell/SearchPage";
import { HelpPage } from "./pages/support/Help";
import { JoinRedirect } from "./referrals/Join";
import { MySupportPage } from "./pages/support/MySupport";
import { SupportTicketPage } from "./pages/support/Ticket";
import { AuthLayout } from "./layouts/AuthLayout";
import { PublicLayout } from "./layouts/PublicLayout";
import { Design } from "./pages/Design";
import { ForgotPassword, ResetPassword, VerifyEmail } from "./pages/auth/Recovery";
import { Login } from "./pages/auth/Login";
import { Register } from "./pages/auth/Register";
import { Explore } from "./pages/public/Explore";
import { Landing } from "./pages/public/Landing";
import { Legal } from "./pages/public/Legal";
import { NewsItem, NewsList } from "./pages/public/News";
import { Skeleton } from "./ui/blocks";
import { ToastProvider } from "./ui/Toast";

const Home = lazy(() => import("./pages/app/Home"));
const Feed = lazy(() => import("./pages/app/Feed"));
const Directory = lazy(() => import("./pages/app/Directory"));
const MemberPage = lazy(() => import("./pages/app/Directory").then((m) => ({ default: m.MemberPage })));
const StartupPage = lazy(() => import("./pages/app/Directory").then((m) => ({ default: m.StartupPage })));
const Jobs = lazy(() => import("./pages/app/Jobs"));
const JobDetail = lazy(() => import("./pages/app/Jobs").then((m) => ({ default: m.JobDetail })));
const NewJob = lazy(() => import("./pages/app/Jobs").then((m) => ({ default: m.NewJob })));
const Events = lazy(() => import("./pages/app/Events"));
const EventDetail = lazy(() => import("./pages/app/Events").then((m) => ({ default: m.EventDetail })));
const Learn = lazy(() => import("./learn/Catalog"));
const CourseLanding = lazy(() => import("./learn/Landing"));
const LecturePlayer = lazy(() => import("./learn/Player"));
const MyLearning = lazy(() => import("./learn/MyLearning"));
const Certificates = lazy(() => import("./learn/Certificates").then((m) => ({ default: m.Certificates })));
const CertificatePage = lazy(() => import("./learn/Certificates"));
const VerifyCertificate = lazy(() => import("./pages/public/VerifyCertificate"));
const AdminCertificateTemplate = lazy(() => import("./admin/CertificateTemplate"));
const AdminCertificates = lazy(() => import("./admin/AdminCertificates"));
const CourseRedirect = lazy(() => import("./learn/Redirects").then((m) => ({ default: m.CourseRedirect })));
const LessonRedirect = lazy(() => import("./learn/Redirects").then((m) => ({ default: m.LessonRedirect })));
const Mentors = lazy(() => import("./pages/app/Mentors"));
const MentorDetail = lazy(() => import("./pages/app/Mentors").then((m) => ({ default: m.MentorDetail })));
const SessionsPage = lazy(() => import("./pages/app/Mentors").then((m) => ({ default: m.SessionsPage })));
const BecomeMentor = lazy(() => import("./pages/app/Mentors").then((m) => ({ default: m.BecomeMentor })));
const Profile = lazy(() => import("./pages/app/Account"));
const StartupForm = lazy(() => import("./pages/app/Account").then((m) => ({ default: m.StartupForm })));
const Settings = lazy(() => import("./pages/app/Account").then((m) => ({ default: m.SettingsPage })));
const SettingsLayout = lazy(() => import("./pages/app/SettingsLayout"));
const MentorSettings = lazy(() => import("./mentor/MentorSettings"));
const Notifications = lazy(() => import("./pages/app/Updates").then((m) => ({ default: m.NotificationsPage })));
const News = lazy(() => import("./pages/app/Updates").then((m) => ({ default: m.NewsPage })));
const Ventures = lazy(() => import("./pages/launch/Ventures"));
const Workspace = lazy(() => import("./pages/launch/Workspace"));
const LaunchOverview = lazy(() => import("./pages/launch/Overview"));
const ProfileTab = lazy(() => import("./pages/launch/ProfileTab"));
const ScoreTab = lazy(() => import("./pages/launch/ScoreTab"));
const PlanTab = lazy(() => import("./pages/launch/PlanTab"));
const ForecastTab = lazy(() => import("./pages/launch/ForecastTab"));
const DecksTab = lazy(() => import("./pages/launch/DecksTab"));
const PrototypesTab = lazy(() => import("./pages/launch/PrototypesTab"));
const PartnerTab = lazy(() => import("./pages/launch/PartnerTab"));
const SharingTab = lazy(() => import("./pages/launch/SharingTab"));
const SharedView = lazy(() => import("./pages/launch/SharedView"));
const AdminLayout = lazy(() => import("./admin/AdminLayout").then((m) => ({ default: m.AdminLayout })));
const AdminHome = lazy(() => import("./admin/AdminHome"));
const AdminMembers = lazy(() => import("./admin/Members"));
const AdminApprovals = lazy(() => import("./admin/Approvals"));
const AdminInvitations = lazy(() => import("./admin/Invitations"));
const AdminMentors = lazy(() => import("./admin/MentorApplications"));
const AdminReports = lazy(() => import("./admin/Reports"));
const AdminJobs = lazy(() => import("./admin/AdminJobs"));
const AdminWins = lazy(() => import("./admin/Queues").then((m) => ({ default: m.WinsReview })));
const AdminNews = lazy(() => import("./admin/News"));
const AdminEvents = lazy(() => import("./admin/Events"));
const AdminCourses = lazy(() => import("./admin/Courses"));
const AdminCourseManage = lazy(() => import("./admin/CourseManage"));
const AdminCourseRequests = lazy(() => import("./admin/CourseRequests"));
const AdminEmail = lazy(() => import("./admin/Email"));
const AdminLists = lazy(() => import("./admin/Reference"));
const AdminStub = lazy(() => import("./admin/Stub"));
const AuditLog = lazy(() => import("./admin/AuditLog"));
const AdminFeed = lazy(() => import("./admin/AdminFeed"));
const AdminSessions = lazy(() => import("./admin/MentoringSessions").then((m) => ({ default: m.MentoringSessions })));
const AdminMatches = lazy(() => import("./admin/MentoringSessions").then((m) => ({ default: m.MentoringMatches })));
const AdminAnalytics = lazy(() => import("./admin/Analytics").then((m) => ({ default: m.AnalyticsOverview })));
const AdminFunnels = lazy(() => import("./admin/Analytics").then((m) => ({ default: m.AnalyticsFunnels })));
const AdminAnalyticReports = lazy(() => import("./admin/Analytics").then((m) => ({ default: m.AnalyticsReports })));
const AdminSettings = lazy(() => import("./admin/Settings"));
const AdminDesign = lazy(() => import("./admin/AdminDesign"));
const AdminSupport = lazy(() => import("./admin/Support"));
const AdminSupportReplies = lazy(() => import("./admin/SupportReplies"));
const AdminSecurity = lazy(() => import("./admin/Security"));
const NewsStory = lazy(() => import("./pages/app/Updates").then((m) => ({ default: m.NewsStory })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // A refused or missing request will not succeed on a second try; a dropped connection may.
      retry: (count, error) => !isStatus(error, 400, 401, 403, 404, 409, 412, 422, 429) && count < 2,
    },
  },
});

function Fallback() {
  return (
    <div className="app-stack" role="status" aria-label="Loading">
      <Skeleton width="30%" height={28} />
      <Skeleton />
      <Skeleton width="70%" />
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <AuthProvider>
            <Suspense fallback={<Fallback />}>
              <Routes>
                <Route element={<PublicLayout />}>
                  <Route index element={<Landing />} />
                  <Route path="explore" element={<Explore />} />
                  <Route path="news" element={<NewsList />} />
                  <Route path="news/:slug" element={<NewsItem />} />
                  <Route path="legal/:doc" element={<Legal />} />
                  <Route path="help" element={<HelpPage />} />
                  <Route path="verify/:code" element={<VerifyCertificate />} />
                  <Route path="design" element={<Design />} />
                </Route>
                <Route path="share/:token" element={<SharedView />} />
                <Route path="join" element={<JoinRedirect />} />
                <Route element={<GuestOnly />}>
                  <Route element={<AuthLayout />}>
                    <Route path="login" element={<Login />} />
                    <Route path="register" element={<Register />} />
                    <Route path="verify-email" element={<VerifyEmail />} />
                    <Route path="forgot-password" element={<ForgotPassword />} />
                    <Route path="reset-password" element={<ResetPassword />} />
                  </Route>
                </Route>
                <Route element={<RequireAuth />}>
                  <Route path="app" element={<AppLayout />}>
                    <Route index element={<Home />} />
                    <Route path="feed" element={<Feed />} />
                    <Route path="directory" element={<Directory />} />
                    <Route path="members/:id" element={<MemberPage />} />
                    <Route path="startups/new" element={<StartupForm />} />
                    <Route path="startups/:id" element={<StartupPage />} />
                    <Route path="startups/:id/edit" element={<StartupForm />} />
                    <Route path="jobs" element={<Jobs />} />
                    <Route path="jobs/new" element={<NewJob />} />
                    <Route path="jobs/:id/edit" element={<NewJob />} />
                    <Route path="jobs/:id" element={<JobDetail />} />
                    <Route path="events" element={<Events />} />
                    <Route path="events/:id" element={<EventDetail />} />
                    <Route path="learn" element={<Learn />} />
                    <Route path="learn/my" element={<MyLearning />} />
                    <Route path="learn/certificates" element={<Certificates />} />
                    <Route path="learn/certificates/:id" element={<CertificatePage />} />
                    <Route path="learn/courses/:ref" element={<CourseLanding />} />
                    <Route path="learn/courses/:ref/lecture/:lessonId" element={<LecturePlayer />} />
                    <Route path="learn/lesson/:id" element={<LessonRedirect />} />
                    <Route path="learn/:id" element={<CourseRedirect />} />
                    <Route path="mentors" element={<Mentors />} />
                    <Route path="mentors/sessions" element={<SessionsPage />} />
                    <Route path="mentors/become" element={<BecomeMentor />} />
                    <Route path="mentors/:id" element={<MentorDetail />} />
                    <Route path="news" element={<News />} />
                    <Route path="news/:id" element={<NewsStory />} />
                    <Route path="launch" element={<Ventures />} />
                    <Route path="launch/:ventureId" element={<Workspace />}>
                      <Route index element={<LaunchOverview />} />
                      <Route path="profile" element={<ProfileTab />} />
                      <Route path="score" element={<ScoreTab />} />
                      <Route path="plan" element={<PlanTab />} />
                      <Route path="forecast" element={<ForecastTab />} />
                      <Route path="decks" element={<DecksTab />} />
                      <Route path="prototypes" element={<PrototypesTab />} />
                      <Route path="partner" element={<PartnerTab />} />
                      <Route path="sharing" element={<SharingTab />} />
                    </Route>
                    <Route path="search" element={<SearchPage scope="member" />} />
                    <Route path="support" element={<MySupportPage />} />
                    <Route path="support/:id" element={<SupportTicketPage />} />
                    <Route path="notifications" element={<Notifications />} />
                    <Route path="me" element={<Profile />} />
                    <Route path="settings" element={<SettingsLayout />}>
                      <Route index element={<Settings />} />
                      <Route path="mentorship" element={<MentorSettings />} />
                    </Route>
                    <Route path="*" element={<Navigate to="/app" replace />} />
                  </Route>
                </Route>
                <Route element={<RequireAuth />}>
                  <Route path="admin" element={<AdminLayout />}>
                    <Route index element={<AdminHome />} />
                    <Route path="members" element={<AdminMembers />}>
                      <Route path=":memberId" element={null} />
                    </Route>
                    <Route path="approvals" element={<AdminApprovals />} />
                    <Route path="invitations" element={<AdminInvitations />} />
                    <Route path="mentors" element={<AdminMentors />} />
                    <Route path="reports" element={<AdminReports />} />
                    <Route path="jobs" element={<AdminJobs />} />
                    <Route path="wins" element={<AdminWins />} />
                    <Route path="feed" element={<AdminFeed />} />
                    <Route path="audit" element={<AuditLog />} />
                    <Route path="sessions" element={<AdminSessions />} />
                    <Route path="matches" element={<AdminMatches />} />
                    <Route path="analytics" element={<AdminAnalytics />} />
                    <Route path="analytics/funnels" element={<AdminFunnels />} />
                    <Route path="analytics/reports" element={<AdminAnalyticReports />} />
                    <Route path="news" element={<AdminNews />} />
                    <Route path="events" element={<AdminEvents />} />
                    <Route path="courses" element={<AdminCourses />} />
                    <Route path="courses/:id" element={<AdminCourseManage />} />
                    <Route path="course-requests" element={<AdminCourseRequests />} />
                    <Route path="certificates" element={<AdminCertificates />} />
                    <Route path="learning/certificate-template" element={<AdminCertificateTemplate />} />
                    <Route path="email" element={<AdminEmail />} />
                    <Route path="lists" element={<AdminLists />} />
                    <Route path="settings" element={<AdminSettings />} />
                    <Route path="search" element={<SearchPage scope="admin" />} />
                    <Route path="support" element={<AdminSupport />} />
                    <Route path="support/replies" element={<AdminSupportReplies />} />
                    <Route path="design" element={<AdminDesign />} />
                    <Route path="security" element={<AdminSecurity />} />
                    <Route path="*" element={<AdminStub />} />
                  </Route>
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
