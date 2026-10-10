# 0022. Link preview cards and server-side request forgery controls

Status: accepted (Stage 2)

## Context

A link preview means our server fetches a web address a member chose. If that fetch is not
constrained, a member can make it call an address they cannot reach themselves: a cloud metadata
service, an internal API, localhost. This is server-side request forgery, and it is the main risk of
the feature.

## Decisions

- **The fetcher is an adapter** (`integrations/linkpreview`) with a real implementation and a fake.
  The real one never runs in a web request: fetching is queued through the outbox as
  `LinkPreviewRequested` and handled by the `feed.fetch_link_preview` task on the `media` queue, with
  a 45 second soft limit. The design calls for that queue to run with no network access except an
  allow list; that is an infrastructure task for the hardening stage (see the runbook).
- **Controls on every request and every redirect hop** (`safe_http.py`):
  - only `http` and `https`, only ports 80, 443, 8080 and 8443, no credentials in the address;
  - named hosts only. IP literals in any notation (`127.0.0.1`, `2130706433`, `0x7f.0.0.1`, `[::1]`),
    single-label names and internal suffixes (`localhost`, `.local`, `.internal`, `.lan`,
    `.home.arpa`) are refused before any lookup;
  - the name is resolved once and **every** answer must be publicly routable. Private, loopback,
    link-local (including `169.254.169.254`), shared (`100.64/10`), multicast, reserved, documentation,
    IPv4-mapped IPv6 and the NAT64 and 6to4 ranges all refuse the whole name, not just that answer;
  - the connection is made to the address we checked, not to the name, so a name that changes its
    answer between check and connect (DNS rebinding) cannot reach an internal host. The `Host`
    header and the TLS server name remain the real host, so certificates are still verified;
  - redirects are followed by hand, at most three, each hop checked from the start;
  - 3 second connect timeout, 4 second read timeout, 8 second overall deadline;
  - responses are requested uncompressed and the size cap (512 KB for a page, 3 MB for an image) is
    counted after decompression, so a compression bomb cannot exhaust memory;
  - no cookies, no proxy or certificate settings from the environment, and only listed content
    types (`text/html`, `application/xhtml+xml`; JPEG, PNG and WebP for images).
- **What is kept.** Title, description and site name are reduced to plain text, shortened and shown
  as text by clients. The picture is never hot-linked: it is downloaded through the same safe client,
  virus scanned, decoded and re-encoded exactly like a member upload, and served from our media
  domain. A page's head is read only up to `</head>`, so content later in the page cannot supply tags.
- **When we ask.** Only posts carry previews. The first two distinct web addresses in the cleaned
  post body are used, after offline checks (so `http://localhost/` is never even queued). One shared
  `LinkPreview` per address serves every post that links to it; it is refreshed after a week, and a
  failed one is retried after an hour when someone links it again. A failed or slow site never
  affects the post: the card simply does not appear. An existing card keeps its content if a refresh
  fails. Previews no post links to are deleted after a week with their pictures.
- **Abuse limits.** The existing daily post allowance bounds how many fetches a member can cause (at
  most two per post).

## Consequences

Rendering a preview from a page that needs JavaScript is not supported (such pages usually have
Open Graph tags anyway). An admin cannot yet block a domain or force a refresh; a block list is easy
to add in `parse_url`. Comments do not get previews. The fetch worker's network isolation is not
enforced in code, so until the infrastructure rule exists these checks are the only barrier, which
is why they are deliberately strict and thoroughly tested.
