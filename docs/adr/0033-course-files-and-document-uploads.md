# 0033. Course files and document uploads

Status: accepted (Stage 3, closing slice)

## Decisions

- **Documents are a second kind of upload**, not a variation of images. Images are decoded and
  rebuilt from their pixels, which removes anything hidden in them. A PDF or Office file cannot be
  rebuilt that way, so it is kept as it arrived and made safe by what happens around it.
- **Same pipeline, different last step.** A document uses the same reserve, direct upload to
  quarantine and complete steps as an image (purpose `course_file`). A worker then reads it,
  scans it for malware and inspects it (below); a file that passes is written, unchanged, to a
  third bucket, `private` (`STORAGE_PRIVATE_BUCKET`), and the quarantine copy is deleted. Nothing
  in `private` is public: the bucket has no CDN address, and `Upload.urls` is never filled for
  documents.
- **What is inspected.** The type must be what the bytes are (a PDF starts `%PDF-` and ends with
  `%%EOF`; an Office file is a zip with its main part, for example `word/document.xml`), and must be
  one of PDF, DOCX, XLSX or PPTX. PDFs with scripts, launch actions, embedded files, rich media or
  forms scripting are refused, including names hidden with `#xx` escapes, as are encrypted PDFs.
  Office files with macros, ActiveX or embedded objects, executables, path tricks, encryption, more
  than 5,000 parts or more than 200 MB unpacked are refused. Rejections carry a reason code the
  uploader sees (`active_content`, `corrupt`, `encrypted`, `type_mismatch`, `malware_detected`...).
  This is a net, not a proof: active content inside compressed PDF object streams is not seen, which
  is why delivery matters as much as inspection.
- **Delivery is the control.** Members are given a signed address that lasts 5 minutes
  (`DOCUMENT_LINK_TTL_SECONDS`) and makes the browser save the file (`Content-Disposition:
  attachment`, the type fixed by us), never display it from our origin. The address comes from
  `GET /lessons/{id}/file`, which applies exactly the same access rule as opening the lesson
  (enrolled, or a free course opened to visitors, with the visitor rate limit), is `no-store`, and
  is asked for again when it lapses. The saved file is named after the lesson's display name with
  the right extension, never a name the uploader's browser supplied.
- **Who may upload.** Only people with `courses.manage` can reserve a `course_file` upload (403
  otherwise); documents are up to 25 MB (`UPLOAD_DOCUMENT_MAX_BYTES`) and count toward the daily
  upload limit. An upload can be attached once, only by its owner, and only to the purpose it was
  made for; an unused ready document is deleted by housekeeping after 24 hours, like an unused
  image.
- **In a lesson.** A resource lesson holds either a link (`resource_url`) or a stored file
  (`upload_id` when creating or editing). Giving a link lets go of a stored file and the other way
  round; the display name defaults to the uploaded file's name. Lesson detail says
  `resource.kind` is `link` or `file`; for a file there is no address in it, only name, size and
  type. Changing a lesson to another type, replacing its file or deleting it deletes the stored
  object, unless a duplicated course's lesson still points at the same object (duplicates share
  files rather than copy them, and the last user deletes it).

## Consequences

Files are not versioned, previewed in the browser, counted per download or watermarked. A member
who has been given a link can pass it on for five minutes; paid-course files rely on enrolment and
that short lifetime, which is the same level of protection the paid-video decision accepts
(ADR 0034). Antivirus runs only if `MALWARE_SCANNER` is the real scanner (production requires it).
