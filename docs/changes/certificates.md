# Certificates

A certificate of completion is issued automatically when a member finishes every lecture of a course
that offers one. The design follows the certificate specification; see ADR 0051 for how it is drawn.

## Members

- On finishing a course the player shows a calm confirmation with **Download certificate**, **View
  certificate** and **Share** (copies the public verification link, or opens the device's share sheet).
  The certificate is drawn by a worker a moment after the last lecture, so the card says it is being
  prepared and then fills in.
- `/app/learn/certificates` lists every certificate; `/app/learn/certificates/:id` shows one as the page
  members receive, with the number and the ways to download and share it.
- The name is taken from the member's profile on the day the certificate is issued, so it can be
  corrected in the profile before the first certificate. Later profile changes do not alter it.

## Public verification

`/verify/:number` (API `GET /api/v1/public/certificates/{number}`) says **Valid** with the learner's
name, the course, the date and the course length, and nothing else. A revoked certificate says
**Revoked** and shows nothing about the person. An unknown number says **Not found**.

## Console

| Route | What it is |
| --- | --- |
| `/admin/learning/certificate-template` | Title and signatory name (default Onyeka Akumah), with a live preview and a PDF preview |
| `/admin/certificates` | Every issued certificate: search, filter, revoke (reason required), reissue or restore |

Template changes apply to certificates issued afterwards. **Reissue** draws one again with the current
template, keeps its number, can correct the name and tells the member. Reissuing a revoked certificate
makes it valid again.

## API

| Method and path | Who |
| --- | --- |
| `GET /me/certificates`, `GET /certificates`, `GET /certificates/{id}` | The member, their own only |
| `GET /certificates/{id}/download` | The member: a short lived link to the PDF; 409 when revoked |
| `GET /public/certificates/{number}` | Anyone |
| `GET`, `PUT /admin/certificate-settings` | Course managers |
| `POST /admin/certificate-settings/preview` | Course managers: a PDF with sample details and unsaved edits |
| `GET /admin/certificates` | Course managers |
| `POST /admin/certificates/{id}/revoke`, `POST /admin/certificates/{id}/reissue` | Course managers |

Events: `certificate_issued`, `certificate_downloaded`, `certificate_revoked`, `certificate_reissued`.

## On the member profile (opt in)

A certificate is listed on its holder's profile only when the holder turns on **Show on my profile** on
the certificate page (`Certificate.show_on_profile`, off by default). The profile screens belong to a
lower layer than learning, so the profile response is left alone and the member page asks learning for the
list: `GET /members/{id}/certificates`. It answers 404 to anyone who may not see the member's basics, lists
only certificates that are on and not revoked, and returns the course, the date, the hours and the
verification link, and no more than the public page already says. The holder changes the choice with
`PATCH /certificates/{id}` (`{"show_on_profile": true}`).

| Endpoint | Who |
|---|---|
| `PATCH /certificates/{id}` | The holder only; anyone else gets 404 |
| `GET /members/{id}/certificates` | A signed in member who may see that profile |

## Layout (current)

The certificate carries no QR code and no web address. The signatory is printed as a name only, taken from the settings (default **Onyeka Akumah**), over a small uppercase "WO COMMUNITY" label. The certificate ID stays in the details row; it is looked up on the verification page. The learner name and course title are copied onto the record when it is issued. Downloads and reissues are drawn from that record with the current layout and signatory.
