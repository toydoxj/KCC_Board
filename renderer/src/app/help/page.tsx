// 사용 매뉴얼 화면. 정본은 docs/user_manual.md이며, 빌드 시점에 읽어 정적 페이지로 만든다.
// 이미지는 data URI로 내장한다(설치본에 docs 폴더가 없으므로).
import fs from "node:fs";
import path from "node:path";

import type { Metadata } from "next";

import { renderMarkdown } from "@/components/markdown";

export const metadata: Metadata = {
  title: "KCC Board 사용 매뉴얼",
};

// next build·next dev는 renderer 폴더에서 실행한다
const DOCS_DIR = path.resolve(process.cwd(), "..", "docs");
const MANUAL_PATH = path.join(DOCS_DIR, "user_manual.md");

const IMAGE_MIME: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
};

function readManual() {
  if (!fs.existsSync(MANUAL_PATH)) {
    throw new Error(`사용 매뉴얼을 찾을 수 없습니다: ${MANUAL_PATH}`);
  }
  return fs.readFileSync(MANUAL_PATH, "utf8");
}

function embedImage(src: string) {
  const imagePath = path.resolve(DOCS_DIR, src);
  if (!imagePath.startsWith(DOCS_DIR) || !fs.existsSync(imagePath)) {
    throw new Error(`사용 매뉴얼 이미지를 찾을 수 없습니다: ${src}`);
  }
  const mime = IMAGE_MIME[path.extname(imagePath).toLowerCase()];
  if (!mime) {
    throw new Error(`지원하지 않는 매뉴얼 이미지 형식입니다: ${src}`);
  }
  return `data:${mime};base64,${fs.readFileSync(imagePath).toString("base64")}`;
}

export default function HelpPage() {
  const { headings, content } = renderMarkdown(readManual(), embedImage);
  const toc = headings.filter((heading) => heading.level === 2);

  return (
    <main className="min-h-screen bg-slate-50">
      <div className="mx-auto grid max-w-6xl gap-6 px-5 py-6 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav className="h-fit rounded-md border border-border bg-white p-4 text-sm shadow-panel lg:sticky lg:top-6">
          <div className="mb-2 font-semibold">목차</div>
          <ol className="grid gap-1">
            {toc.map((heading) => (
              <li key={heading.id}>
                <a className="text-muted-foreground hover:text-primary" href={`#${heading.id}`}>
                  {heading.text}
                </a>
              </li>
            ))}
          </ol>
        </nav>
        <article className="min-w-0 rounded-md border border-border bg-white px-6 py-6 shadow-panel">{content}</article>
      </div>
    </main>
  );
}
