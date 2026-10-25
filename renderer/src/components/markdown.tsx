// 사용 매뉴얼(docs/user_manual.md) 표시용 간이 마크다운 변환기.
// 매뉴얼에서 쓰는 문법만 처리한다: 제목(#~###), 문단, 인용(>), 목록(-, 1.), 표(|), 단독 이미지 줄, 굵게(**), 코드(`).
// 처리하지 못하는 문법은 문단 텍스트로 그대로 표시한다.
import type { ReactNode } from "react";

export interface MarkdownHeading {
  id: string;
  level: number;
  text: string;
}

export interface MarkdownDocument {
  headings: MarkdownHeading[];
  content: ReactNode[];
}

type ImageResolver = (src: string) => string;

const IMAGE_LINE = /^!\[([^\]]*)\]\(([^)]+)\)$/;
const HEADING_LINE = /^(#{1,3})\s+(.*)$/;
const ORDERED_ITEM = /^\d+\.\s+(.*)$/;
const UNORDERED_ITEM = /^-\s+(.*)$/;
const NESTED_ITEM = /^\s{2,}-\s+(.*)$/;

export function renderMarkdown(source: string, resolveImage: ImageResolver): MarkdownDocument {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const headings: MarkdownHeading[] = [];
  const content: ReactNode[] = [];
  let index = 0;
  let key = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (trimmed === "") {
      index += 1;
      continue;
    }

    const heading = HEADING_LINE.exec(trimmed);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2];
      const id = `section-${headings.length + 1}`;
      headings.push({ id, level, text });
      content.push(renderHeading(level, id, text, key++));
      index += 1;
      continue;
    }

    const image = IMAGE_LINE.exec(trimmed);
    if (image) {
      content.push(
        <figure key={key++} className="my-4">
          {/* eslint-disable-next-line @next/next/no-img-element -- 빌드 시 내장한 data URI 이미지 */}
          <img src={resolveImage(image[2])} alt={image[1]} className="max-w-full rounded-md border border-border shadow-sm" />
          <figcaption className="mt-1 text-xs text-muted-foreground">{image[1]}</figcaption>
        </figure>,
      );
      index += 1;
      continue;
    }

    if (trimmed.startsWith(">")) {
      const block: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        block.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      content.push(
        <blockquote key={key++} className="my-4 rounded-md border-l-4 border-primary bg-cyan-50 px-4 py-3 text-sm text-slate-700">
          {renderInline(block.join(" "))}
        </blockquote>,
      );
      continue;
    }

    if (trimmed.startsWith("|")) {
      const rows: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        rows.push(lines[index].trim());
        index += 1;
      }
      content.push(renderTable(rows, key++));
      continue;
    }

    if (UNORDERED_ITEM.test(trimmed) || ORDERED_ITEM.test(trimmed)) {
      const ordered = ORDERED_ITEM.test(trimmed);
      const items: { text: string; children: string[] }[] = [];
      while (index < lines.length) {
        const current = lines[index];
        const nested = NESTED_ITEM.exec(current);
        const item = ordered ? ORDERED_ITEM.exec(current.trim()) : UNORDERED_ITEM.exec(current);
        if (nested && items.length > 0) {
          items[items.length - 1].children.push(nested[1]);
        } else if (item && !/^\s/.test(current)) {
          items.push({ text: item[1], children: [] });
        } else {
          break;
        }
        index += 1;
      }
      if (items.length === 0) {
        // 부모 항목 없이 들여쓴 목록 줄: 문단 텍스트로 표시하고 다음 줄로 진행(무한 반복 방지)
        content.push(
          <p key={key++} className="my-3 text-sm leading-6">
            {renderInline(trimmed)}
          </p>,
        );
        index += 1;
        continue;
      }
      const ListTag = ordered ? "ol" : "ul";
      content.push(
        <ListTag key={key++} className={`my-3 grid gap-1 pl-6 text-sm leading-6 ${ordered ? "list-decimal" : "list-disc"}`}>
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>
              {renderInline(item.text)}
              {item.children.length > 0 ? (
                <ul className="mt-1 grid list-[circle] gap-1 pl-5">
                  {item.children.map((child, childIndex) => (
                    <li key={childIndex}>{renderInline(child)}</li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ListTag>,
      );
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() !== "" && !isBlockStart(lines[index].trim())) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    if (paragraph.length === 0) {
      // 블록 시작 기호지만 위 규칙에 맞지 않는 줄: 텍스트로 표시하고 진행
      paragraph.push(trimmed);
      index += 1;
    }
    content.push(
      <p key={key++} className="my-3 text-sm leading-6">
        {renderInline(paragraph.join(" "))}
      </p>,
    );
  }

  return { headings, content };
}

function isBlockStart(line: string) {
  return (
    HEADING_LINE.test(line)
    || IMAGE_LINE.test(line)
    || line.startsWith(">")
    || line.startsWith("|")
    || UNORDERED_ITEM.test(line)
    || ORDERED_ITEM.test(line)
  );
}

function renderHeading(level: number, id: string, text: string, key: number) {
  const inline = renderInline(text);
  if (level === 1) {
    return (
      <h1 key={key} id={id} className="mb-4 scroll-mt-4 text-2xl font-semibold">
        {inline}
      </h1>
    );
  }
  if (level === 2) {
    return (
      <h2 key={key} id={id} className="mt-10 mb-3 scroll-mt-4 border-b border-border pb-2 text-xl font-semibold">
        {inline}
      </h2>
    );
  }
  return (
    <h3 key={key} id={id} className="mt-6 mb-2 scroll-mt-4 text-base font-semibold">
      {inline}
    </h3>
  );
}

function splitRow(row: string) {
  return row
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderTable(rows: string[], key: number) {
  const [header, separator, ...body] = rows;
  const hasHeader = separator !== undefined && /^\|?\s*:?-{3,}/.test(separator);
  const headerCells = hasHeader ? splitRow(header) : [];
  const bodyRows = (hasHeader ? body : rows).map(splitRow);
  return (
    <div key={key} className="my-4 overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        {hasHeader ? (
          <thead>
            <tr>
              {headerCells.map((cell, cellIndex) => (
                <th key={cellIndex} className="border border-slate-300 bg-slate-100 px-3 py-2 text-left font-semibold">
                  {renderInline(cell)}
                </th>
              ))}
            </tr>
          </thead>
        ) : null}
        <tbody>
          {bodyRows.map((cells, rowIndex) => (
            <tr key={rowIndex}>
              {cells.map((cell, cellIndex) => (
                <td key={cellIndex} className="border border-slate-300 px-3 py-2 align-top">
                  {renderInline(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderInline(text: string): ReactNode[] {
  // `코드`와 **굵게**만 처리한다
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter((part) => part !== "");
  return parts.map((part, partIndex) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={partIndex} className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={partIndex}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}
