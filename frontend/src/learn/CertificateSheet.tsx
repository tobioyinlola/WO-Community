import { Logo } from "../components";
import { formatDate } from "../lib/format";
import "../styles/learn.css";

export interface CertificateSheetProps {
  holder: string;
  course: string;
  issuedAt: string | Date;
  number: string;
  hours: number;
  titleText: string;
  signatoryName: string;
  /** An uploaded signature. Without one, Onyeka's own signature is shown when the certificate names him. */
  signatureUrl?: string | null;
}

const DEFAULT_SIGNATORY = "Onyeka Akumah";
const DEFAULT_SIGNATURE = "/brand/signature-onyeka.png";

const hoursText = (hours: number) => `${Number.isInteger(hours) ? hours : hours.toFixed(1)} ${hours === 1 ? "hour" : "hours"}`;

/**
 * The certificate on screen, laid out like the PDF: A4 landscape, a cream canvas with a thin forest border,
 * the learner and course on the left, the brand shapes on the right and the signatory's name. It scales with its container, and it never follows the dark theme because a
 * certificate is a printed object.
 */
export function CertificateSheet({ holder, course, issuedAt, number, hours, titleText, signatoryName, signatureUrl }: CertificateSheetProps) {
  const signer = signatoryName.trim() || DEFAULT_SIGNATORY;
  const signature = signatureUrl || (signer === DEFAULT_SIGNATORY ? DEFAULT_SIGNATURE : null);
  return (
    <figure className="wo-certwrap" aria-label={`${titleText} for ${holder}`}>
      <div className="wo-cert">
        <div className="wo-cert__frame" aria-hidden="true" />
        <div className="wo-cert__art" aria-hidden="true">
          <span className="wo-cert__ring" />
          <span className="wo-cert__eye" />
          <span className="wo-cert__capsule" />
          <span className="wo-cert__dot" />
        </div>
        <header className="wo-cert__top">
          <Logo on="light" height={104} />
          <p className="wo-cert__eyebrow">{titleText}</p>
        </header>
        <div className="wo-cert__body">
          <p className="wo-cert__small">This certifies that</p>
          <p className="wo-cert__name">{holder}</p>
          <p className="wo-cert__small">has successfully completed</p>
          <p className="wo-cert__course">{course}</p>
          <dl className="wo-cert__facts">
            <div>
              <dt>Date of completion</dt>
              <dd>{formatDate(issuedAt)}</dd>
            </div>
            <div>
              <dt>Course length</dt>
              <dd>{hoursText(hours)}</dd>
            </div>
            <div>
              <dt>Certificate ID</dt>
              <dd className="wo-cert__mono">{number}</dd>
            </div>
          </dl>
        </div>
        <div className="wo-cert__sign">
          {signature ? <img className="wo-cert__signature" src={signature} alt={`Signature of ${signer}`} /> : <span className="wo-cert__signature" />}
          <span className="wo-cert__line" />
          <strong>{signer}</strong>
          <span className="wo-cert__label">WO COMMUNITY</span>
        </div>
        <p className="wo-cert__footer">The future of Africa is being built here.</p>
      </div>
    </figure>
  );
}
