// Builds a valid podcast RSS 2.0 feed with the iTunes namespace from D1 rows.

export interface Show {
  title: string;
  author: string;
  description: string;
  email: string;
  image: string;
  language: string;
  category: string;
  link: string;
}

export interface Episode {
  guid: string;
  slug: string;
  title: string;
  description: string;
  audio_url: string;
  audio_bytes: number;
  duration_sec: number;
  pub_date: string; // ISO 8601
  transcript_url?: string | null;
}

export const xmlEscape = (s: string): string =>
  s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");

// RSS requires RFC 822 dates. toUTCString() produces a compliant form.
const toRfc822 = (iso: string): string => {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? new Date().toUTCString() : d.toUTCString();
};

const durationHms = (totalSec: number): string => {
  const s = Math.max(0, Math.round(totalSec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
};

function item(ep: Episode): string {
  const transcript = ep.transcript_url
    ? `\n      <podcast:transcript url="${xmlEscape(ep.transcript_url)}" type="text/vtt" />`
    : "";
  return `    <item>
      <title>${xmlEscape(ep.title)}</title>
      <description>${xmlEscape(ep.description)}</description>
      <itunes:summary>${xmlEscape(ep.description)}</itunes:summary>
      <enclosure url="${xmlEscape(ep.audio_url)}" length="${ep.audio_bytes}" type="audio/mpeg" />${transcript}
      <guid isPermaLink="false">${xmlEscape(ep.guid)}</guid>
      <pubDate>${toRfc822(ep.pub_date)}</pubDate>
      <itunes:duration>${durationHms(ep.duration_sec)}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>`;
}

export function buildFeed(show: Show, episodes: Episode[], selfUrl: string): string {
  const imageTag = show.image
    ? `    <itunes:image href="${xmlEscape(show.image)}" />
    <image>
      <url>${xmlEscape(show.image)}</url>
      <title>${xmlEscape(show.title)}</title>
      <link>${xmlEscape(show.link)}</link>
    </image>\n`
    : "";

  const lastBuild =
    episodes.length > 0 ? toRfc822(episodes[0].pub_date) : new Date().toUTCString();

  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:podcast="https://podcastindex.org/namespace/1.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>${xmlEscape(show.title)}</title>
    <link>${xmlEscape(show.link)}</link>
    <atom:link href="${xmlEscape(selfUrl)}" rel="self" type="application/rss+xml" />
    <description>${xmlEscape(show.description)}</description>
    <language>${xmlEscape(show.language)}</language>
    <lastBuildDate>${lastBuild}</lastBuildDate>
    <itunes:author>${xmlEscape(show.author)}</itunes:author>
    <itunes:summary>${xmlEscape(show.description)}</itunes:summary>
    <itunes:type>episodic</itunes:type>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="${xmlEscape(show.category)}" />
    <itunes:owner>
      <itunes:name>${xmlEscape(show.author)}</itunes:name>
      <itunes:email>${xmlEscape(show.email)}</itunes:email>
    </itunes:owner>
${imageTag}${episodes.map(item).join("\n")}
  </channel>
</rss>
`;
}
