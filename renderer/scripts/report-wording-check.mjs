// 산출 문서(상세 계산서·요약페이지) 프로그램 문구 검사 (APP_DEV item 182, 2026-11-26)
//
// 사용법: node scripts/report-wording-check.mjs <fixtures.json> [--dump-text]
//   fixtures.json: [{ "name": "...", "data": CalculationReportData, "userInputs": ["사용자·로컬 DB 원문", ...] }, ...]
//   (tests/test_report_wording.py 가 실제 /api/check 응답으로 만든다)
//
// 동작: CalculationReport·SummaryReport 컴포넌트를 react-dom/server 로 렌더링하여 실제 출력 텍스트를 얻는다.
// ① 프로그램 문구 검사: 텍스트에서 userInputs 원문을 빼고 PROGRAM_TEXT_PATTERN(아래, 화면 경고 검출식과 독립)으로 찾는다.
//    1곳이라도 있으면 종료 코드 1. 렌더링 실패는 종료 코드 2.
// ② 사용자 입력: 원문이 그대로 인쇄됐는지(userInputsPrinted)와 화면 경고 목록(findReservationFields)을 함께 낸다.
// ③ 출력 절차: runGuardedReportOutput 에 확인 거절·승인 대역을 넣어 저장 호출 횟수를 낸다(output).
//    사용자 자유입력·식별 필드는 지우거나 바꾸지 않는다(소유자 결정 2026-11-26).
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

// 프로그램 문구 검사식 — src/lib/report-wording.ts(화면 경고 검출식)와 독립적으로 둔다. tests/test_report_wording.py 가 이 원문을 읽는다
export const PROGRAM_TEXT_PATTERN = /확인\s*필요|확인이\s*필요|확인을\s*요|확인\s*(해|하여)\s*주|확인\s*바|확인하시기|확인하십시오|근거\s*없|미검증|미확인|미확정|검증\s*(하지|되지)|초안|보류|잠정|확정\s*필요|검토\s*(가|를)?\s*(필요|요)|검토\s*(해|하여)\s*주|추후|별도\s*(확인|검토)|주의|유의|경고|판정\s*불가|결과\s*적용에|warn|caution|draft|tbd|tbc|todo|pending|unverified|please\s*(verify|confirm|check)|(verify|confirm|check)\s*(before|prior)/giu;

function normalizeForCheck(text) {
  return text.normalize("NFKC").replace(/[\u200B-\u200D\u2060\uFEFF\u00AD]/g, "").replace(/\s+/g, " ").trim();
}

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

// userInputs 원문을 지운 뒤 프로그램 문구만 남겨 검사한다(정규화형 + 공백 제거형)
function findProgramHits(text, userInputs) {
  const hits = [];
  // 줄바꿈·폭 없는 문자가 든 원문은 줄로 나누기 전에 원형 그대로 먼저 뺀다
  let body = text;
  for (const input of userInputs) {
    if (input) body = body.split(input).join(" ");
  }
  for (const rawLine of body.split("\n")) {
    let line = normalizeForCheck(rawLine);
    for (const input of userInputs) {
      const normalizedInput = normalizeForCheck(input);
      if (normalizedInput) line = line.split(normalizedInput).join(" ");
    }
    const words = new Set();
    for (const candidate of [line, line.replace(/\s+/g, "")]) {
      for (const match of candidate.match(PROGRAM_TEXT_PATTERN) ?? []) words.add(match);
    }
    if (words.size > 0) hits.push({ words: [...words], line: line.slice(0, 200) });
  }
  return hits;
}

async function main() {
  const fixturePath = process.argv.slice(2).find((arg) => !arg.startsWith("--"));
  const dumpText = process.argv.includes("--dump-text");
  if (!fixturePath) {
    console.error("사용법: node scripts/report-wording-check.mjs <fixtures.json>");
    process.exit(2);
  }
  const cases = JSON.parse(readFileSync(fixturePath, "utf8"));
  if (!Array.isArray(cases) || cases.length === 0) {
    console.error(`예제가 없음: ${fixturePath}`);
    process.exit(2);
  }
  const reservation = await import(pathToFileURL(path.join(srcDir, "lib/report-reservation.ts")).href);
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { CalculationReport } = await import(pathToFileURL(path.join(srcDir, "components/calculation-report.tsx")).href);
  const { SummaryReport } = await import(pathToFileURL(path.join(srcDir, "components/summary-report.tsx")).href);

  const report = [];
  const screen = [];
  let total = 0;
  for (const item of cases) {
    const printed = {};
    for (const [kind, Component] of [["detail", CalculationReport], ["summary", SummaryReport]]) {
      const html = renderToStaticMarkup(createElement(Component, { data: item.data }));
      const text = htmlToText(html);
      if (text.trim().length < 200) {
        throw new Error(`${item.name}/${kind}: 렌더링 텍스트가 비정상적으로 짧음(${text.trim().length}자)`);
      }
      const userInputs = Array.isArray(item.userInputs) ? item.userInputs : [];
      const hits = findProgramHits(text, userInputs);
      total += hits.length;
      const normalizedText = normalizeForCheck(text);
      const userInputsPrinted = userInputs.map((input) => ({ input, printed: normalizedText.includes(normalizeForCheck(input)) }));
      report.push({ name: item.name, kind, chars: text.length, hits, userInputsPrinted, ...(dumpText ? { text } : {}) });
      printed[kind] = text;
    }
    // PDF 출력 전 화면 경고 목록(page.tsx 와 같은 함수, 문서 종류별 렌더링 텍스트로 인쇄 여부 판별)
    const fields = reservation.findReservationFields(item.data, printed);
    // 앱 저장 버튼 경로(runGuardedReportOutput): 확인 거절/승인 시 저장 호출 횟수
    const output = {};
    for (const kind of ["detail", "summary"]) {
      output[kind] = {};
      for (const answer of [false, true]) {
        let saves = 0;
        let prompts = 0;
        let message = null;
        const status = await reservation.runGuardedReportOutput({
          kind,
          fields,
          confirm: (text) => { prompts += 1; message = text; return answer; },
          save: () => { saves += 1; },
        });
        output[kind][answer ? "approve" : "cancel"] = { status, saves, prompts, message };
      }
    }
    screen.push({ name: item.name, reservationFields: fields, reservationTitle: reservation.reservationWarningTitle(fields), output });
  }
  // 큰 출력이 파이프에서 잘리지 않도록 process.exit 대신 exitCode 로 끝낸다
  process.stdout.write(JSON.stringify({ total, report, screen }, null, 2) + "\n");
  process.exitCode = total === 0 ? 0 : 1;
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exit(2);
});
