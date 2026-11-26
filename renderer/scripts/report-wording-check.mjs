// 산출 문서(상세 계산서·요약페이지) 금지 문구 검사 (APP_DEV item 182, 2026-11-26)
//
// 사용법: node scripts/report-wording-check.mjs <fixtures.json>
//   fixtures.json: [{ "name": "...", "data": CalculationReportData }, ...]
//   (tests/test_report_wording.py 가 실제 /api/check 응답으로 만든다)
//
// 동작: CalculationReport·SummaryReport 컴포넌트를 react-dom/server 로 렌더링하여 실제 출력 텍스트를 얻고,
// 금지 문구 정규식에 맞는 곳을 모두 출력한다. 1곳이라도 있으면 종료 코드 1, 렌더링 실패는 종료 코드 2.
// TS/TSX 는 renderer 의 typescript 로 즉시 변환한다(추가 의존성 없음). "@/..." 경로는 src 로 해석한다.

import { readFileSync, existsSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { registerHooks } from "node:module";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const rendererDir = path.resolve(here, "..");
const srcDir = path.join(rendererDir, "src");
const nodeModulesDir = path.join(rendererDir, "node_modules");
// 변환 대상: renderer 소스(src, package.json 등). node_modules 는 Node 기본 로더에 맡긴다
const isOwnFile = (filePath) => filePath.startsWith(rendererDir) && !filePath.startsWith(nodeModulesDir);
const sourceExtensions = [".ts", ".tsx", ".json"];

// tests/test_report_wording.py FORBIDDEN_PATTERN 과 같은 목록을 유지한다(소유자 상시 지시)
export const FORBIDDEN_PATTERN =
  /확인\s*필요|확인이\s*필요|근거\s*없음|미검증|검증하지\s*않|검증되지\s*않|초안|보류|확정\s*필요|검토\s*필요|추후\s*확인|별도\s*확인|확인하시기|주의|WARN|판정\s*불가/g;

function resolveFile(basePath) {
  if (existsSync(basePath) && statSync(basePath).isFile()) return basePath;
  for (const ext of sourceExtensions) {
    if (existsSync(basePath + ext)) return basePath + ext;
  }
  for (const ext of sourceExtensions) {
    const indexPath = path.join(basePath, `index${ext}`);
    if (existsSync(indexPath)) return indexPath;
  }
  return null;
}

registerHooks({
  resolve(specifier, context, nextResolve) {
    let basePath = null;
    if (specifier.startsWith("@/")) {
      basePath = path.join(srcDir, specifier.slice(2));
    } else if ((specifier.startsWith("./") || specifier.startsWith("../")) && context.parentURL?.startsWith("file:")) {
      basePath = fileURLToPath(new URL(specifier, context.parentURL));
    }
    if (basePath !== null && isOwnFile(basePath)) {
      const resolved = resolveFile(basePath);
      if (resolved === null) {
        throw new Error(`모듈을 찾을 수 없음: ${specifier} (from ${context.parentURL})`);
      }
      return { url: pathToFileURL(resolved).href, shortCircuit: true };
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.startsWith("file:") && isOwnFile(fileURLToPath(url)) && /\.(tsx?|json)$/.test(url)) {
      const filePath = fileURLToPath(url);
      const source = readFileSync(filePath, "utf8");
      if (filePath.endsWith(".json")) {
        return { format: "module", source: `export default ${source};`, shortCircuit: true };
      }
      const output = ts.transpileModule(source, {
        fileName: filePath,
        compilerOptions: {
          module: ts.ModuleKind.ESNext,
          target: ts.ScriptTarget.ES2022,
          jsx: ts.JsxEmit.ReactJSX,
          esModuleInterop: true,
        },
      });
      return { format: "module", source: output.outputText, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});

function htmlToText(html) {
  return html
    .replace(/<(br|\/p|\/div|\/tr|\/li|\/h[1-6])\b[^>]*>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;|&#39;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/[ \t]+/g, " ");
}

function findHits(text) {
  const hits = [];
  for (const line of text.split("\n")) {
    const matches = line.match(FORBIDDEN_PATTERN);
    if (matches) hits.push({ words: matches, line: line.trim().slice(0, 200) });
  }
  return hits;
}

async function main() {
  const fixturePath = process.argv[2];
  if (!fixturePath) {
    console.error("사용법: node scripts/report-wording-check.mjs <fixtures.json>");
    process.exit(2);
  }
  const cases = JSON.parse(readFileSync(fixturePath, "utf8"));
  if (!Array.isArray(cases) || cases.length === 0) {
    console.error(`예제가 없음: ${fixturePath}`);
    process.exit(2);
  }
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { CalculationReport } = await import(pathToFileURL(path.join(srcDir, "components/calculation-report.tsx")).href);
  const { SummaryReport } = await import(pathToFileURL(path.join(srcDir, "components/summary-report.tsx")).href);

  const report = [];
  let total = 0;
  for (const item of cases) {
    for (const [kind, Component] of [["detail", CalculationReport], ["summary", SummaryReport]]) {
      const html = renderToStaticMarkup(createElement(Component, { data: item.data }));
      const text = htmlToText(html);
      if (text.trim().length < 200) {
        throw new Error(`${item.name}/${kind}: 렌더링 텍스트가 비정상적으로 짧음(${text.trim().length}자)`);
      }
      const hits = findHits(text);
      total += hits.length;
      report.push({ name: item.name, kind, chars: text.length, hits });
    }
  }
  console.log(JSON.stringify({ total, report }, null, 2));
  process.exit(total === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exit(2);
});
