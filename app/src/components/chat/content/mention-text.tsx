/**
 * MentionText — renders text with @name mentions highlighted as styled chips.
 * Matches @expert (with colored avatar) and @file (with file icon).
 * Unrecognized @mentions are preserved as plain text.
 */
import React from "react";
import { FileText } from "lucide-react";
import i18n from "@/lib/i18n";
import type { Expert } from "@/lib/experts";
import { ExpertIcon, getCategoryHue } from "@/components/expert-icon";

// Match @ followed by Chinese chars, word chars, or hyphens
const MENTION_RE = /@([\u4e00-\u9fff\w-]+)/g;

export interface MentionFiles {
  /** File names that have been @mentioned. id is not used for matching — name match only. */
  names: Set<string>;
}

export function renderTextWithMentions(
  text: string,
  mentionedFiles?: MentionFiles,
  experts?: Expert[],
): React.ReactNode {
  const parts: React.ReactNode[] = [];
  let lastIdx = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = MENTION_RE.exec(text)) !== null) {
    // Preceding plain text
    if (match.index > lastIdx) {
      parts.push(<React.Fragment key={key++}>{text.slice(lastIdx, match.index)}</React.Fragment>);
    }

    const name = match[1];
    const expert = experts?.find((e) => e.name === name || e.id === name);
    const isFile = mentionedFiles?.names.has(name);

    if (expert) {
      parts.push(
        <span
          key={key++}
          className="inline-flex items-center gap-1 px-1 py-0.5 rounded bg-brand/10 text-brand font-medium cursor-default"
          title={`${expert.name} · ${expert.description}`}
        >
          <ExpertIcon
            emoji={expert.icon}
            hue={getCategoryHue(expert.category)}
            size="sm"
            className="!w-3.5 !h-3.5"
          />
          @{expert.name}
        </span>,
      );
    } else if (isFile) {
      parts.push(
        <span
          key={key++}
          className="inline-flex items-center gap-1 px-1 py-0.5 rounded bg-muted/60 text-muted-foreground font-medium cursor-default"
          title={i18n.t("mentionText.fileChip", { ns: "chatUi", name })}
        >
          <FileText className="w-3 h-3" />@{name}
        </span>,
      );
    } else {
      // Unrecognized @mention — keep as plain text
      parts.push(<React.Fragment key={key++}>@{name}</React.Fragment>);
    }

    lastIdx = MENTION_RE.lastIndex;
  }

  // Remaining text after last match
  if (lastIdx < text.length) {
    parts.push(<React.Fragment key={key++}>{text.slice(lastIdx)}</React.Fragment>);
  }

  return parts.length > 0 ? parts : text;
}
