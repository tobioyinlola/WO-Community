# 0043. Prototypes: a specification, never code

Status: accepted (toolkit stage T4, prototypes)

## Decisions

- **A prototype is a tree of registry components.** The registry (`prototypes/registry.py`) lists
  more than forty components in seven groups (layout, text, input, action, data, navigation,
  feedback) and, for each, the properties it accepts with their kind and limits. The front end
  draws from the same names, so the registry is the contract. Nothing outside it can be stored.
- **No code, no markup, no addresses.** Text is plain; properties are text, enums, bounded numbers
  or short lists; navigation is only `navigate` to another screen of the same prototype, `back`
  or nothing. A component without children cannot hold any; one that cannot act cannot navigate.
- **Limits.** Between 1 and `PROTOTYPE_MAX_SCREENS` (20) screens, nesting up to 8, 120 components a
  screen and 800 overall. A request over a limit is refused naming where.
- **Edits are JSON patch**, the same all or nothing mechanism as decks (`apps/core/jsonpatch.py`),
  over `/screens`, `/theme`, `/start`, `/kind`, validated as a whole, with `base_version` and 409.
- **Nine templates** (landing, onboarding, dashboard, marketplace, booking, learning, settings,
  admin, updates feed) seed the database and are admin managed. The product document's list was
  not available, so these are an assumption.
- **A model may draft a prototype** from the profile and an optional brief. Its answer is validated
  like any edit; if it cannot be made valid after one retry that names the problem, the member gets
  a template (flagged `fallback`) instead of an error. A brief that asks for made up proof is
  declined before any model is called.
- **Sharing** reuses share links: a prototype link shows the specification read only.
