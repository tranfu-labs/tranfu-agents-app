const MAX_SKILL_NAME = 160;
const BLOCK_RE = /<(skills?|available_skills|agent_skills)\b[^>]*>[\s\S]*?<\/\1>|<skill\b[^>]*(?:\/>|>[\s\S]*?<\/skill>)/gi;
const NAME_ATTR_RE = /<skill\b[^>]*\bname\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s/>]+))/gi;
const SKILL_BODY_RE = /<skill\b([^>]*)>([\s\S]*?)<\/skill>/gi;
const NAME_TAG_RE = /<(?:name|slug|id)\b[^>]*>([\s\S]*?)<\/(?:name|slug|id)>/i;

function decodeXml(value) {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

function cleanName(value) {
  if (typeof value !== "string") return "";
  const name = decodeXml(value).replace(/\s+/g, " ").trim();
  if (!name || name.length > MAX_SKILL_NAME) return "";
  return name;
}

function maybeTextName(value) {
  const stripped = value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  if (!stripped || stripped.length > MAX_SKILL_NAME) return "";
  if (stripped.split(/\s+/).length > 8) return "";
  if (!/^[\w .:@/+~,-]+$/u.test(stripped)) return "";
  return cleanName(stripped);
}

export function extractSkillNames(input) {
  try {
    const text = typeof input === "string" ? input : String(input || "");
    if (!text) return { names: [], blockSeen: false, blockLength: 0 };

    const blocks = [];
    for (const match of text.matchAll(BLOCK_RE)) {
      blocks.push(match[0]);
    }
    const blockSeen = blocks.length > 0 || /<\/?skills?\b/i.test(text) || /<skill\b/i.test(text);
    if (!blockSeen) return { names: [], blockSeen: false, blockLength: 0 };

    const source = blocks.length ? blocks.join("\n") : text;
    const names = new Set();
    for (const match of source.matchAll(NAME_ATTR_RE)) {
      const name = cleanName(match[1] || match[2] || match[3] || "");
      if (name) names.add(name);
    }
    for (const match of source.matchAll(SKILL_BODY_RE)) {
      const attrs = match[1] || "";
      if (/\bname\s*=/i.test(attrs)) continue;
      const body = match[2] || "";
      const tag = body.match(NAME_TAG_RE);
      const name = tag ? cleanName(tag[1]) : maybeTextName(body);
      if (name) names.add(name);
    }

    return {
      names: Array.from(names).sort(),
      blockSeen: true,
      blockLength: source.length,
    };
  } catch {
    return { names: [], blockSeen: false, blockLength: 0 };
  }
}
