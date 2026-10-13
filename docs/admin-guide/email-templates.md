# Email templates

**Where:** Admin > Email > Email templates. **Who:** community and super admins
(`email.templates.manage`).

Every email the platform sends uses one of 19 templates (verification, welcome, invitation, account
approved or not, password reset, news, job approved or rejected, mentor decision, support received and
reply, course access, certificate, admin approval needed and digest, event reminder, digest, and a
general notice for other updates). The layout, logo, colours and the sign off are fixed; **only the
words are editable**.

- Edit the subject, the preview text (the grey line beside the subject) and the body.
- Write paragraphs with a blank line between them. `**bold**`, `[a link](https://…)`, lines starting
  with `- ` for a list, and one `[button: Label | {{variable}}]`.
- Click a detail chip (such as `{{verify_url}}`) to insert it. Chips marked "keep" must stay in the
  body or the email stops working. A paragraph that uses an optional detail is left out when there is
  nothing to show.
- The preview updates as you type, at desktop and phone width, with the plain text version below it.
  **Send me a test** sends the draft to you.
- Saving checks the wording (no HTML, https links only, no all capital or "!!" subjects). Every save
  is kept in the **History**; **Restore** puts an earlier one back, and **Reset to default** returns
  to the built in wording. Edits are audited.

Every email ends "Best regards, The WO Community Team" (the `EMAIL_SIGNOFF` setting). Newsletters are
written in Admin > Email > Newsletters and use the same layout, with the unsubscribe link and your
organisation line in the footer.
