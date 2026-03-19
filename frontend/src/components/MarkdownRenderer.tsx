"use client";

/**
 * Zero-dependency markdown renderer for clinical answer text.
 * Handles: headings, bold, italic, inline code, bullet lists,
 * numbered lists, horizontal rules, and paragraphs.
 * No ESM/CJS compatibility issues.
 */

import React from "react";

interface Props {
  content: string;
  className?: string;
}

type Block =
  | { type: "h1" | "h2" | "h3"; text: string }
  | { type: "hr" }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] }
  | { type: "p"; text: string };

/** Parse inline markdown: **bold**, *italic*, `code` */
function parseInline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  // Combined regex for **bold**, *italic*, `code`
  const regex = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    if (match[2] !== undefined) {
      parts.push(<strong key={match.index} className="font-semibold text-gray-900">{match[2]}</strong>);
    } else if (match[3] !== undefined) {
      parts.push(<em key={match.index}>{match[3]}</em>);
    } else if (match[4] !== undefined) {
      parts.push(
        <code key={match.index} className="bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-xs font-mono">
          {match[4]}
        </code>
      );
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    parts.push(text.slice(last));
  }
  return parts.length > 0 ? parts : [text];
}

/** Group raw lines into structured blocks */
function parseBlocks(markdown: string): Block[] {
  const lines = markdown.split("\n");
  const blocks: Block[] = [];
  let listType: "ul" | "ol" | null = null;
  let listItems: string[] = [];

  const flushList = () => {
    if (listType && listItems.length > 0) {
      blocks.push({ type: listType, items: [...listItems] });
      listType = null;
      listItems = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();

    // Heading
    const h3 = line.match(/^### (.+)/);
    const h2 = line.match(/^## (.+)/);
    const h1 = line.match(/^# (.+)/);
    if (h1 || h2 || h3) {
      flushList();
      const level = h3 ? "h3" : h2 ? "h2" : "h1";
      blocks.push({ type: level, text: (h1 || h2 || h3)![1] });
      continue;
    }

    // HR
    if (/^[-*_]{3,}$/.test(line.trim())) {
      flushList();
      blocks.push({ type: "hr" });
      continue;
    }

    // Unordered list item
    const ulMatch = line.match(/^[-*+] (.+)/);
    if (ulMatch) {
      if (listType === "ol") flushList();
      listType = "ul";
      listItems.push(ulMatch[1]);
      continue;
    }

    // Ordered list item
    const olMatch = line.match(/^\d+\. (.+)/);
    if (olMatch) {
      if (listType === "ul") flushList();
      listType = "ol";
      listItems.push(olMatch[1]);
      continue;
    }

    // Empty line — flush list, end paragraph
    if (line.trim() === "") {
      flushList();
      continue;
    }

    // Continuation of list item (indented)
    if (listType && (line.startsWith("  ") || line.startsWith("\t"))) {
      listItems[listItems.length - 1] += " " + line.trim();
      continue;
    }

    // Plain paragraph line — flush any list first
    flushList();
    blocks.push({ type: "p", text: line });
  }

  flushList();
  return blocks;
}

export function MarkdownRenderer({ content, className = "" }: Props) {
  if (!content) return null;
  const blocks = parseBlocks(content);

  return (
    <div className={`space-y-2 text-gray-800 text-sm leading-relaxed ${className}`}>
      {blocks.map((block, i) => {
        switch (block.type) {
          case "h1":
            return <h2 key={i} className="text-lg font-bold text-gray-900 mt-4 mb-1">{parseInline(block.text)}</h2>;
          case "h2":
            return <h3 key={i} className="text-base font-semibold text-gray-900 mt-3 mb-1">{parseInline(block.text)}</h3>;
          case "h3":
            return <h4 key={i} className="text-sm font-semibold text-gray-800 mt-2 mb-0.5">{parseInline(block.text)}</h4>;
          case "hr":
            return <hr key={i} className="border-gray-200 my-3" />;
          case "ul":
            return (
              <ul key={i} className="list-disc list-outside pl-5 space-y-1">
                {block.items.map((item, j) => (
                  <li key={j} className="text-gray-700">{parseInline(item)}</li>
                ))}
              </ul>
            );
          case "ol":
            return (
              <ol key={i} className="list-decimal list-outside pl-5 space-y-1">
                {block.items.map((item, j) => (
                  <li key={j} className="text-gray-700">{parseInline(item)}</li>
                ))}
              </ol>
            );
          case "p":
            return <p key={i} className="text-gray-800">{parseInline(block.text)}</p>;
          default:
            return null;
        }
      })}
    </div>
  );
}
