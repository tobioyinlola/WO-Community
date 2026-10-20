import { ExternalLink } from "lucide-react";

export interface LinkCardData {
  url: string;
  title: string;
  description: string;
  site_name: string;
  image?: { thumb: string; large: string } | null;
}

/**
 * What a link in a post says before it is opened: the site, the page's title and a few words, with
 * its picture when it has one. A link whose page could not be read still names the site. The whole
 * card is the link, and it opens in a new tab.
 */
export function LinkCard({ preview }: { preview: LinkCardData }) {
  const { url, title, description, site_name, image } = preview;
  return (
    <a className="wo-linkcard" href={url} target="_blank" rel="noopener noreferrer nofollow">
      {image ? <img className="wo-linkcard__img" src={image.thumb} alt="" loading="lazy" /> : null}
      <span className="wo-linkcard__body">
        {site_name && site_name !== title ? <span className="wo-linkcard__site">{site_name}</span> : null}
        <strong className="wo-linkcard__title">{title || url}</strong>
        {description ? <span className="wo-linkcard__desc">{description}</span> : null}
      </span>
      <ExternalLink className="wo-linkcard__icon" size={18} strokeWidth={1.5} aria-hidden="true" />
      <span className="wo-visually-hidden">Opens in a new tab</span>
    </a>
  );
}
