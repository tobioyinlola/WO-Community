import QRCode from "qrcode";
import { useMemo } from "react";
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
  signatoryTitle: string;
  signatureUrl?: string | null;
  verifyUrl: string;
}

/** The QR code for the verification page, drawn here as an SVG in the sheet's ink colour. */
function Qr({ url, label }: { url: string; label: string }) {
  const modules = useMemo(() => {
    try {
      const code = QRCode.create(url, { errorCorrectionLevel: "M" });
      const size = code.modules.size;
      let path = "";
      for (let row = 0; row < size; row += 1) {
        for (let col = 0; col < size; col += 1) {
          if (code.modules.get(row, col)) path += `M${col} ${row}h1v1h-1z`;
        }
      }
      return { size, path };
    } catch {
      return null;
    }
  }, [url]);
  if (!modules) return <span className="wo-cert__qrgap" />;
  return (
    <svg className="wo-cert__qr" viewBox={`0 0 ${modules.size} ${modules.size}`} role="img" aria-label={label} shapeRendering="crispEdges">
      <path d={modules.path} fill="currentColor" />
    </svg>
  );
}

const hoursText = (hours: number) => `${Number.isInteger(hours) ? hours : hours.toFixed(1)} ${hours === 1 ? "hour" : "hours"}`;

/**
 * The certificate on screen, laid out like the PDF: A4 landscape, a cream canvas with a thin forest border,
 * the learner and course on the left, the brand shapes on the right and a QR code that opens the
 * verification page. It scales with its container, and it never follows the dark theme because a
 * certificate is a printed object.
 */
export function CertificateSheet({ holder, course, issuedAt, number, hours, titleText, signatoryName, signatoryTitle, signatureUrl, verifyUrl }: CertificateSheetProps) {
  const host = (() => {
    try {
      return new URL(verifyUrl).host;
    } catch {
      return "wo.community";
    }
  })();
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
          <Logo on="light" height={34} />
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
          {signatureUrl ? <img src={signatureUrl} alt="" className="wo-cert__signature" /> : <span className="wo-cert__signature" />}
          <span className="wo-cert__line" />
          {signatoryName ? <strong>{signatoryName}</strong> : null}
          {signatoryTitle ? <span>{signatoryTitle}</span> : null}
          <span>WO Community</span>
        </div>
        <div className="wo-cert__verify">
          <Qr url={verifyUrl} label={`QR code that opens ${verifyUrl}`} />
          <span>Verify at {host}/verify</span>
        </div>
        <p className="wo-cert__footer">The future of Africa is being built here.</p>
      </div>
    </figure>
  );
}
