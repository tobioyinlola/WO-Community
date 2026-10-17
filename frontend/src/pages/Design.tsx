import { useState, type ReactNode } from "react";
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  CardLink,
  CardText,
  CardTitle,
  Checkbox,
  ChoiceGroup,
  Input,
  MemberCard,
  Modal,
  Radio,
  Select,
  StatTile,
  Switch,
  Tabs,
  Textarea,
  TopNav,
} from "../components";
import { useTheme, type ThemeChoice } from "../theme/ThemeProvider";

const LOGO = {
  fullOnLight: "/brand/wo-logo-on-light.png",
  fullOnDark: "/brand/wo-logo-on-dark.png",
  markOnLight: "/brand/wo-mark-on-light.png",
  markOnDark: "/brand/wo-mark-on-dark.png",
};

/** Renders its content on a themed ground, so one page shows both themes side by side. */
function ThemePanel({ theme, children }: { theme: "light" | "dark"; children: ReactNode }) {
  return (
    <div
      data-theme={theme}
      style={{
        background: "var(--bg-canvas)",
        color: "var(--text-primary)",
        padding: "var(--space-6)",
        borderRadius: "var(--radius-xl)",
        border: "var(--stroke-1) solid var(--border-default)",
      }}
    >
      <p className="eyebrow" style={{ color: "var(--text-accent)", margin: "0 0 var(--space-4)" }}>
        {theme} theme
      </p>
      <div className="wo-stack">{children}</div>
    </div>
  );
}

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: () => ReactNode;
}) {
  return (
    <section aria-labelledby={id} style={{ marginTop: "var(--space-16)" }}>
      <h2 className="h2" id={id} style={{ margin: "0 0 var(--space-6)" }}>
        {title}
      </h2>
      <div
        style={{
          display: "grid",
          gap: "var(--gutter)",
          gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
        }}
      >
        <ThemePanel theme="light">{children()}</ThemePanel>
        <ThemePanel theme="dark">{children()}</ThemePanel>
      </div>
    </section>
  );
}

function ThemeSwitcher() {
  const { choice, setChoice } = useTheme();
  const options: ThemeChoice[] = ["system", "light", "dark"];
  return (
    <Tabs
      label="Theme"
      variant="segment"
      value={choice}
      onChange={(id) => setChoice(id as ThemeChoice)}
      items={options.map((id) => ({ id, label: id.charAt(0).toUpperCase() + id.slice(1) }))}
    />
  );
}

function ModalDemo() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Open dialog
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        eyebrow="Mentorship"
        title="Book this session?"
        actions={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => setOpen(false)}>Confirm booking</Button>
          </>
        }
      >
        Thursday 16 Oct, 15:00 WAT with Amaka Obi. A meeting link will be emailed.
      </Modal>
    </>
  );
}

/** Every component in both themes. Placeholder names and figures are not real people or data. */
export function Design() {
  return (
    <div className="wo-container" style={{ paddingTop: "var(--space-8)", paddingBottom: "var(--space-24)" }}>
      <div className="wo-page-rule">
        <hr />
        <span className="wo-eyebrow">Design system</span>
      </div>
      <div className="wo-row" style={{ justifyContent: "space-between", marginTop: "var(--space-6)" }}>
        <h1 className="h1" style={{ margin: 0 }}>
          Components
        </h1>
        <ThemeSwitcher />
      </div>

      <section style={{ marginTop: "var(--space-12)" }} aria-label="Headline">
        <div className="wo-on-brand" style={{ padding: "var(--space-12)", borderRadius: "var(--radius-2xl)" }}>
          <span className="wo-eyebrow">Intentional</span>
          <p className="display-lg" style={{ margin: "var(--space-4) 0 0" }}>
            The future of Africa is being <span className="wo-hl">built</span> here.
          </p>
        </div>
      </section>

      <Section id="buttons" title="Button">
        {() => (
          <>
            <div className="wo-row">
              <Button>Become a member</Button>
              <Button variant="secondary">View programme</Button>
              <Button variant="ghost">Skip for now</Button>
              <Button variant="danger">Remove member</Button>
            </div>
            <div className="wo-row">
              <Button size="sm">Small</Button>
              <Button>Default</Button>
              <Button size="lg">Large</Button>
              <Button disabled>Disabled</Button>
              <Button loading>Saving</Button>
            </div>
            <div className="wo-on-brand wo-row" style={{ padding: "var(--space-6)", borderRadius: "var(--radius-xl)" }}>
              <Button variant="accent" size="lg">Join the launchpad</Button>
              <Button variant="white" size="lg">Apply now</Button>
              <Button variant="onBrand">Learn more</Button>
            </div>
          </>
        )}
      </Section>

      <Section id="inputs" title="Input">
        {() => (
          <>
            <Input label="Full name" placeholder="Amaka Obi" />
            <Input label="Work email" defaultValue="amaka@" error="Enter a full email address." />
            <Select
              label="Stage"
              hint="We use this to match you with mentors."
              options={[
                { value: "pre-seed", label: "Pre-seed" },
                { value: "seed", label: "Seed" },
                { value: "series-a", label: "Series A" },
              ]}
            />
            <Input label="Invite code" defaultValue="WO-2026-00418" disabled />
            <Textarea label="About you" placeholder="What are you building?" />
          </>
        )}
      </Section>

      <Section id="choices" title="Checkbox, radio and switch">
        {() => (
          <>
            <ChoiceGroup legend="Notifications">
              <Checkbox label="Share my profile with members" defaultChecked />
              <Checkbox label="Email me about demo days" />
              <Checkbox label="Locked option" disabled />
            </ChoiceGroup>
            <ChoiceGroup legend="Profile visibility">
              <Radio name="visibility" label="Members only" defaultChecked />
              <Radio name="visibility" label="Public" />
              <Radio name="visibility" label="Private" />
            </ChoiceGroup>
            <ChoiceGroup legend="Alerts">
              <Switch label="New mentor matches" defaultChecked />
              <Switch label="Weekly digest" />
            </ChoiceGroup>
          </>
        )}
      </Section>

      <Section id="badges" title="Badge">
        {() => (
          <>
            <div className="wo-row">
              <Badge variant="founder">Founder</Badge>
              <Badge variant="operator">Operator</Badge>
              <Badge variant="investor">Investor</Badge>
              <Badge variant="mentor">Mentor</Badge>
              <Badge variant="pro">Pro</Badge>
              <Badge variant="solid">Featured</Badge>
            </div>
            <div className="wo-row">
              <Badge variant="success" dot>Approved</Badge>
              <Badge variant="warning" dot>Pending review</Badge>
              <Badge variant="danger" dot>Rejected</Badge>
              <Badge variant="info" dot>Invited</Badge>
            </div>
          </>
        )}
      </Section>

      <Section id="avatars" title="Avatar">
        {() => (
          <div className="wo-row" style={{ alignItems: "flex-end" }}>
            <Avatar name="Amaka Obi" shape="arch" size="lg" tint="peach" />
            <Avatar name="Tunde Kolade" shape="capsule" size="lg" tint="periwinkle" />
            <Avatar name="Ngozi Eze" shape="bloom" size="lg" tint="lilac" />
            <Avatar name="Jide Okafor" size="lg" tint="mint" />
            <Avatar name="Chidi Bello" tint="amber" />
            <Avatar name="Funmi Adeyemi" size="sm" tint="peach" />
          </div>
        )}
      </Section>

      <Section id="cards" title="Card">
        {() => (
          <>
            <Card>
              <Badge variant="operator">Programme</Badge>
              <CardTitle style={{ marginTop: "var(--space-3)" }}>Founder Fundamentals</CardTitle>
              <CardText>Six weeks on traction, fundraising and hiring.</CardText>
            </Card>
            <CardLink href="#cards">
              <Badge variant="investor">Event</Badge>
              <CardTitle style={{ marginTop: "var(--space-3)" }}>Demo Day, Lagos</CardTitle>
              <CardText>Twelve teams. One evening.</CardText>
            </CardLink>
            <Card variant="brand">
              <span className="wo-eyebrow">Featured</span>
              <CardTitle style={{ marginTop: "var(--space-3)" }}>Join the launchpad</CardTitle>
              <CardText>Apply for the next cohort.</CardText>
            </Card>
            <Card variant="white">
              <CardTitle>Pure white</CardTitle>
              <CardText>For testimonials and photo mats.</CardText>
            </Card>
            <Card variant="accent">
              <CardTitle>Invite-only week</CardTitle>
              <p style={{ margin: 0, color: "var(--text-accent-strong)" }}>
                Admin invites are approved instantly.
              </p>
            </Card>
          </>
        )}
      </Section>

      <Section id="members" title="MemberCard">
        {() => (
          <>
            <MemberCard
              id="m-1"
              name="Amaka Obi"
              title="CEO"
              company="Kuda Foods"
              location="Lagos, Nigeria"
              roles={["founder", "mentor"]}
              mutualConnections={12}
              onConnect={() => undefined}
            />
            <MemberCard
              id="m-2"
              name="Tunde Kolade"
              title="Partner"
              company="Delta Capital"
              location="Nairobi, Kenya"
              roles={["investor"]}
              mutualConnections={4}
              onConnect={() => undefined}
            />
          </>
        )}
      </Section>

      <Section id="tabs" title="Tabs">
        {() => (
          <>
            <Tabs
              label="Profile sections"
              items={[
                { id: "about", label: "About", panel: <p className="body">About this member.</p> },
                { id: "activity", label: "Activity", panel: <p className="body">Recent activity.</p> },
                { id: "mentorship", label: "Mentorship", panel: <p className="body">Mentoring.</p> },
              ]}
            />
            <Tabs
              label="Directory filter"
              variant="segment"
              items={[
                { id: "all", label: "All" },
                { id: "founders", label: "Founders" },
                { id: "investors", label: "Investors" },
              ]}
            />
          </>
        )}
      </Section>

      <Section id="alerts" title="Alert">
        {() => (
          <>
            <Alert tone="info" title="Application received">
              An admin will review your registration. We will email you.
            </Alert>
            <Alert tone="success" title="You're approved">
              Welcome to WO Community. Finish your profile.
            </Alert>
            <Alert tone="warning" title="Session time clash">
              Your mentor is booked at 14:00. Pick another slot.
            </Alert>
            <Alert tone="danger" title="Registration not approved">
              Contact the community team if this is a mistake.
            </Alert>
          </>
        )}
      </Section>

      <Section id="modal" title="Modal">
        {() => <ModalDemo />}
      </Section>

      <Section id="nav" title="TopNav">
        {() => (
          <>
            <TopNav
              logo={LOGO}
              links={[
                { label: "Directory", href: "#nav", current: true },
                { label: "Programmes", href: "#nav" },
                { label: "Jobs", href: "#nav" },
                { label: "Events", href: "#nav" },
              ]}
              tail={
                <>
                  <Button variant="ghost" size="sm">Sign in</Button>
                  <Button size="sm">Become a member</Button>
                </>
              }
            />
            <TopNav
              variant="brand"
              logo={LOGO}
              links={[
                { label: "About", href: "#nav", current: true },
                { label: "Programmes", href: "#nav" },
                { label: "Partners", href: "#nav" },
              ]}
              tail={<Button variant="accent" size="sm">Join us</Button>}
            />
          </>
        )}
      </Section>

      <Section id="stats" title="StatTile">
        {() => (
          <div className="wo-row" style={{ alignItems: "stretch" }}>
            <StatTile variant="brand" label="Members" value="4,200+" delta="+12% this month" />
            <StatTile label="Sessions booked" value="318" delta="+24 this week" />
            <StatTile label="Startups funded" value="57" delta="Since 2023" />
          </div>
        )}
      </Section>
    </div>
  );
}
