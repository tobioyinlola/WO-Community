# 0051. Certificates are drawn with ReportLab from a shared layout, not through an HTML engine

Status: accepted

## Context

The certificate design is specified as an HTML template rendered to an A4 landscape PDF, plus a
responsive web view. Rendering HTML to PDF needs a browser engine or a library with system
dependencies (Cairo, Pango, or a headless browser). The platform's servers and the Windows
development machines have none of these, and adding one means a heavier image, a larger attack
surface (a renderer that fetches and interprets markup) and output that differs between machines.
ReportLab is already a dependency for the venture exports.

## Decision

- **The PDF is drawn directly with ReportLab** (`apps/learning/pdf.py`) following the specification
  measure for measure: cream canvas, thin forest inset border 10 mm from the edge, logo and eyebrow
  along the top, the learner and course in the left 60 percent, a forest arch with the ochre ring,
  periwinkle capsule and peach circle on the right, signature area bottom left, QR code and
  "Verify at" caption bottom right and the footer line.
- **The web view is React** (`CertificateSheet`), laid out in container-query units so it scales
  like the page. The admin preview shows that same component live as the form is edited; the "Open
  the PDF preview" button draws the real PDF with the unsaved settings.
- **Fonts are embedded.** Hanken Grotesk (regular, bold, extra bold) and JetBrains Mono, converted
  once from the web font files to TrueType and merged across the latin, latin-extended and
  vietnamese subsets so Yoruba, Igbo and Hausa names set correctly. A letter a font still lacks falls
  back to its plain form. The text is real text and can be selected; the file is about 40 KB, well
  under the 500 KB limit. The fonts are under the SIL Open Font License (`assets/fonts/OFL.txt`).
- **Colours are the design tokens converted to hex** in one table; a test fails if a value drifts
  from `frontend/src/styles/tokens.css`. There is no dark version: a certificate is printed.
- **The logo** is read from `apps/learning/assets/wo-logo-on-light.png` when the brand file is
  supplied, and the wordmark is set in the brand face until then.
- **Storage.** The PDF is drawn by the issuing worker and kept in the private bucket under a random
  key. Members receive a short lived signed link (`GET /certificates/{id}/download`), never the key.
  If the file is asked for before the worker has drawn it, it is drawn then.
- **Template snapshot.** A certificate copies the template (title, signatory, signature, version)
  when it is issued. Changing the settings affects new certificates only; an administrator can
  reissue one to give it the current template, optionally correcting the name.
- **Numbers.** `WO-C-YYYY-NNNNNN` with six random digits, unique, retried on a clash. Older
  twelve character codes keep working. The public lookup is rate limited like other public reads.
- **Revoking** needs a reason, is audited, makes the public page say "Revoked" and show nothing
  about the person, and stops downloads. Reissuing a revoked certificate restores it.

## Consequences

The layout exists twice (ReportLab and CSS). They are kept aligned by using the same measurements,
and a change to the design means changing both. In exchange nothing new has to be installed or
patched on the servers, and the output is identical everywhere.
