import type { ReactNode } from "react";

import type { BoardProperty, StudSection } from "@/lib/api";

const centralJointStudGapMm = 25;
const rStudBoardStudClearGapMm = 12;

interface SectionPreviewProps {
  rearBoards: BoardProperty[];
  frontBoards: BoardProperty[];
  stud: StudSection | undefined;
  studMethod?: string;
}

export function SectionPreview({ rearBoards, frontBoards, stud, studMethod }: SectionPreviewProps) {
  const boardUnit = 12;
  const isChStud = isChStudGroup(stud?.group);
  const hasFixedRearBoard = isChStud || isIStudGroup(stud?.group);
  const isRStud = isRStudGroup(stud?.group);
  const rStudPreviewGap = rStudBoardStudClearGapMm * 2.2;
  const rearStudGap = isRStud && rearBoards.length > 0 ? rStudPreviewGap : 0;
  const frontStudGap = isRStud && frontBoards.length > 0 ? rStudPreviewGap : 0;
  const rearHeight = rearBoards.reduce((sum, board) => sum + board.thickness * 2.2, 0);
  const studSectionHeight = studPreviewHeight(stud, studMethod);
  const studHeight = Math.max(studSectionHeight * 1.2, 48);
  const studWidth = Math.max(Math.min((stud?.B ?? 45) * 2.3, 128), 76);
  const studX = (320 - studWidth) / 2;
  const frontHeight = frontBoards.reduce((sum, board) => sum + board.thickness * 2.2, 0);
  const totalHeight = (hasFixedRearBoard ? Math.max(rearHeight, studHeight) : rearHeight + rearStudGap + studHeight + frontStudGap) + frontHeight;
  const viewHeight = Math.max(totalHeight + 32, 180);
  let cursor = 16;

  const rearRects = rearBoards.map((board, index) => {
    const height = Math.max(board.thickness * 2.2, boardUnit);
    const y = cursor;
    if (!hasFixedRearBoard) {
      cursor += height;
    }
    return { key: `rear-${index}`, y, height, label: `${board.thickness}T` };
  });
  if (!hasFixedRearBoard) {
    cursor += rearStudGap;
  }
  const studY = cursor;
  cursor += hasFixedRearBoard ? Math.max(rearHeight, studHeight) : studHeight;
  if (!hasFixedRearBoard) {
    cursor += frontStudGap;
  }
  const frontRects = frontBoards.map((board, index) => {
    const height = Math.max(board.thickness * 2.2, boardUnit);
    const y = cursor;
    cursor += height;
    return { key: `front-${index}`, y, height, label: `${board.thickness}T` };
  });

  return (
    <svg className="h-full min-h-[180px] w-full" viewBox={`0 0 320 ${viewHeight}`} role="img" aria-label="단면 구성">
      <rect x="0" y="0" width="320" height={viewHeight} fill="#f8fafc" />
      <line x1="40" x2="280" y1="16" y2="16" stroke="#94a3b8" strokeWidth="1" />
      {rearRects.map((rect) => (
        <g key={rect.key}>
          <rect x="76" y={rect.y} width="168" height={rect.height} rx="2" fill="#d9eadf" stroke="#4b8b64" />
          <text x="254" y={rect.y + rect.height / 2 + 4} fill="#334155" fontSize="11">
            {rect.label}
          </text>
        </g>
      ))}
      <StudShape x={studX} y={studY} width={studWidth} height={studHeight} stud={stud} studMethod={studMethod} />
      <text x="224" y={studY + studHeight / 2 + 4} fill="#334155" fontSize="11">
        {stud?.name ?? "STUD"}
      </text>
      {frontRects.map((rect) => (
        <g key={rect.key}>
          <rect x="76" y={rect.y} width="168" height={rect.height} rx="2" fill="#f2e3c5" stroke="#a97930" />
          <text x="254" y={rect.y + rect.height / 2 + 4} fill="#334155" fontSize="11">
            {rect.label}
          </text>
        </g>
      ))}
      <line x1="40" x2="280" y1={cursor} y2={cursor} stroke="#94a3b8" strokeWidth="1" />
    </svg>
  );
}

function StudShape({
  x,
  y,
  width,
  height,
  stud,
  studMethod,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  stud: StudSection | undefined;
  studMethod?: string;
}) {
  const shape = studShape(stud, studMethod);
  const strokeWidth = Math.max(Math.min((stud?.t ?? 0.8) * 3.2, 4), 2.2);
  const stroke = "#1f6f8b";
  const secondaryStroke = "#c47a2c";
  const centralGapRatio = shape === "centralJoint" && stud ? centralJointStudGapMm / (2 * stud.H + centralJointStudGapMm) : null;

  return (
    <g>
      {renderStudShape({
        shape,
        x,
        y,
        width,
        height,
        stroke,
        secondaryStroke,
        strokeWidth,
        centralGapRatio,
      })}
    </g>
  );
}

function studPreviewHeight(stud: StudSection | undefined, studMethod?: string) {
  const baseHeight = stud?.H ?? 50;
  if (isButtJointMethod(studMethod)) {
    return Math.max(baseHeight, 92);
  }
  return isCentralJointMethod(studMethod) ? 2 * baseHeight + centralJointStudGapMm : baseHeight;
}

function studShape(stud: StudSection | undefined, studMethod?: string) {
  const group = (stud?.group ?? "").toUpperCase();
  if (group.includes("C-STUD") && isButtJointMethod(studMethod)) {
    return "buttJoint";
  }
  if (group.includes("C-STUD") && isCentralJointMethod(studMethod)) {
    return "centralJoint";
  }
  if (group.includes("I-STUD")) {
    return "i";
  }
  if (group.includes("MP-STUD")) {
    return "mp";
  }
  if (group.includes("RV-STUD")) {
    return "rv";
  }
  if (group.includes("HR-STUD")) {
    return "hr";
  }
  if (group.includes("T.SILENT")) {
    return "silent";
  }
  if (group.includes("CH-STUD")) {
    return "ch";
  }
  return "c";
}

function renderStudShape({
  shape,
  x,
  y,
  width,
  height,
  stroke,
  secondaryStroke,
  strokeWidth,
  centralGapRatio,
}: {
  shape: string;
  x: number;
  y: number;
  width: number;
  height: number;
  stroke: string;
  secondaryStroke: string;
  strokeWidth: number;
  centralGapRatio: number | null;
}): ReactNode {
  if (shape === "buttJoint") {
    return <ButtJointStudPath x={x} y={y} width={width} height={height} />;
  }
  if (shape === "centralJoint") {
    return (
      <CentralJointStudPath
        x={x}
        y={y}
        width={width}
        height={height}
        stroke={stroke}
        secondaryStroke={secondaryStroke}
        strokeWidth={strokeWidth}
        centralGapRatio={centralGapRatio ?? 0.2}
      />
    );
  }
  if (shape === "i") {
    return <IStudPath x={x} y={y} width={width} height={height} stroke={stroke} strokeWidth={strokeWidth} />;
  }
  if (shape === "mp" || shape === "rv") {
    return (
      <>
        <ChannelPath x={x} y={y} width={width} height={height / 2 - 2} stroke={stroke} strokeWidth={strokeWidth} openSide="center" />
        <ChannelPath
          x={x}
          y={y + height / 2 + 2}
          width={width}
          height={height / 2 - 2}
          stroke={secondaryStroke}
          strokeWidth={strokeWidth}
          openSide="center"
          flipY
        />
      </>
    );
  }
  if (shape === "hr") {
    return <HrStudPath x={x} y={y} width={width} height={height} stroke={stroke} strokeWidth={strokeWidth} />;
  }
  if (shape === "silent") {
    return <SilentStudPath x={x} y={y} width={width} height={height} stroke={stroke} strokeWidth={strokeWidth} />;
  }
  if (shape === "ch") {
    return <ChStudPath x={x} y={y} width={width} height={height} stroke={stroke} strokeWidth={strokeWidth} />;
  }
  return <ChannelPath x={x} y={y} width={width} height={height} stroke={stroke} strokeWidth={strokeWidth} openSide="left" />;
}

function isCentralJointMethod(studMethod?: string) {
  return (studMethod ?? "").replace(/\s/g, "").includes("중앙부이음");
}

function isButtJointMethod(studMethod?: string) {
  return (studMethod ?? "").replace(/\s/g, "").includes("맞댐");
}

function isChStudGroup(group?: string) {
  return (group ?? "").replace(/\s/g, "").toUpperCase().startsWith("CH-STUD");
}

function isIStudGroup(group?: string) {
  return (group ?? "").replace(/\s/g, "").toUpperCase() === "I-STUD";
}

function isRStudGroup(group?: string) {
  return (group ?? "").replace(/[.\s]/g, "-").replace(/-+/g, "-").toUpperCase() === "R-STUD";
}

function ButtJointStudPath({ x, y, width, height }: { x: number; y: number; width: number; height: number }) {
  const baseLeft = x + width * 0.06;
  const baseRight = x + width * 0.84;
  const baseTop = y + height * 0.74;
  const baseDepth = Math.min(width * 0.18, 16);
  const baseHeight = Math.min(height * 0.16, 18);
  const studLeft = x + width * 0.42;
  const studWidth = Math.min(width * 0.3, 34);
  const studDepth = Math.min(width * 0.15, 15);
  const studTop = y + height * 0.12;
  const studBottom = baseTop - 4;
  const sideStudLeft = x + width * 0.28;
  const sideStudWidth = Math.min(width * 0.14, 16);
  const sideStudTop = y + height * 0.25;
  const arrowColor = "#3b82c4";

  return (
    <g strokeLinecap="round" strokeLinejoin="round">
      <polygon
        points={`${baseLeft},${baseTop} ${baseRight},${baseTop} ${baseRight + baseDepth},${baseTop - baseDepth * 0.58} ${baseLeft + baseDepth},${baseTop - baseDepth * 0.58}`}
        fill="#eef2f7"
        stroke="#64748b"
        strokeWidth="1.4"
      />
      <polygon
        points={`${baseLeft},${baseTop} ${baseRight},${baseTop} ${baseRight},${baseTop + baseHeight} ${baseLeft},${baseTop + baseHeight}`}
        fill="#d8dee6"
        stroke="#64748b"
        strokeWidth="1.4"
      />
      <polygon
        points={`${baseRight},${baseTop} ${baseRight + baseDepth},${baseTop - baseDepth * 0.58} ${baseRight + baseDepth},${baseTop + baseHeight - baseDepth * 0.58} ${baseRight},${baseTop + baseHeight}`}
        fill="#cbd5e1"
        stroke="#64748b"
        strokeWidth="1.4"
      />

      <polygon
        points={`${sideStudLeft},${sideStudTop} ${sideStudLeft + sideStudWidth},${sideStudTop - 6} ${sideStudLeft + sideStudWidth},${studBottom - 6} ${sideStudLeft},${studBottom}`}
        fill="#cbd5e1"
        stroke="#475569"
        strokeWidth="1.3"
      />
      <polygon
        points={`${sideStudLeft + sideStudWidth},${sideStudTop - 6} ${sideStudLeft + sideStudWidth + 7},${sideStudTop - 2} ${sideStudLeft + sideStudWidth + 7},${studBottom - 2} ${sideStudLeft + sideStudWidth},${studBottom - 6}`}
        fill="#e5e7eb"
        stroke="#475569"
        strokeWidth="1.3"
      />

      <polygon
        points={`${studLeft},${studTop} ${studLeft + studWidth},${studTop - 10} ${studLeft + studWidth},${studBottom - 10} ${studLeft},${studBottom}`}
        fill="#d1d5db"
        stroke="#334155"
        strokeWidth="1.5"
      />
      <polygon
        points={`${studLeft + studWidth},${studTop - 10} ${studLeft + studWidth + studDepth},${studTop - 2} ${studLeft + studWidth + studDepth},${studBottom - 2} ${studLeft + studWidth},${studBottom - 10}`}
        fill="#f1f5f9"
        stroke="#334155"
        strokeWidth="1.5"
      />
      <polyline
        points={`${studLeft + 7},${studTop + 4} ${studLeft + 7},${studBottom - 6} ${studLeft + studWidth - 6},${studBottom - 14}`}
        fill="none"
        stroke="#64748b"
        strokeWidth="1.1"
      />
      <polyline
        points={`${studLeft + studWidth - 7},${studTop - 2} ${studLeft + studWidth - 7},${studBottom - 16}`}
        fill="none"
        stroke="#64748b"
        strokeWidth="1.1"
      />
      <line x1={studLeft + studWidth + 4} x2={studLeft + studWidth + studDepth - 4} y1={studTop + 6} y2={studTop + 1} stroke="#64748b" strokeWidth="1.1" />
      <line x1={studLeft + studWidth + 4} x2={studLeft + studWidth + studDepth - 4} y1={studBottom - 20} y2={studBottom - 25} stroke="#64748b" strokeWidth="1.1" />

      <ArrowLine color={arrowColor} x1={x + width * 0.08} x2={studLeft + 4} y1={y + height * 0.26} y2={y + height * 0.43} />
      <ArrowLine color={arrowColor} x1={x + width * 0.1} x2={baseLeft + baseDepth + 8} y1={y + height * 0.67} y2={baseTop + 3} />
    </g>
  );
}

function ArrowLine({
  color,
  x1,
  x2,
  y1,
  y2,
}: {
  color: string;
  x1: number;
  x2: number;
  y1: number;
  y2: number;
}) {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const headLength = 7;
  const leftAngle = angle - Math.PI / 7;
  const rightAngle = angle + Math.PI / 7;
  const headLeftX = x2 - headLength * Math.cos(leftAngle);
  const headLeftY = y2 - headLength * Math.sin(leftAngle);
  const headRightX = x2 - headLength * Math.cos(rightAngle);
  const headRightY = y2 - headLength * Math.sin(rightAngle);

  return (
    <g>
      <line x1={x1} x2={x2} y1={y1} y2={y2} stroke={color} strokeWidth="2" />
      <polygon points={`${x2},${y2} ${headLeftX},${headLeftY} ${headRightX},${headRightY}`} fill={color} />
    </g>
  );
}

function ChannelPath({
  x,
  y,
  width,
  height,
  stroke,
  strokeWidth,
  openSide,
  flipY = false,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  stroke: string;
  strokeWidth: number;
  openSide: "left" | "center";
  flipY?: boolean;
}) {
  const left = x + 10;
  const right = x + width - 10;
  const top = y + 8;
  const bottom = y + height - 8;
  const lip = openSide === "left" ? Math.min(width * 0.11, 9) : Math.min(width * 0.22, 18);
  const transform = flipY ? `translate(0 ${top + bottom}) scale(1 -1)` : undefined;
  const path =
    openSide === "left"
      ? `M ${left + lip} ${top} H ${right} V ${bottom} H ${left + lip} M ${left + lip} ${top} V ${top + lip} M ${left + lip} ${bottom} V ${bottom - lip}`
      : `M ${left} ${top} H ${right} V ${top + lip} M ${left} ${top} V ${bottom} H ${right} V ${bottom - lip}`;
  return (
    <path
      d={path}
      fill="none"
      stroke={stroke}
      strokeLinecap="square"
      strokeLinejoin="miter"
      strokeWidth={strokeWidth}
      transform={transform}
      vectorEffect="non-scaling-stroke"
    />
  );
}

function CentralJointStudPath({
  x,
  y,
  width,
  height,
  stroke,
  secondaryStroke,
  strokeWidth,
  centralGapRatio,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  stroke: string;
  secondaryStroke: string;
  strokeWidth: number;
  centralGapRatio: number;
}) {
  const gapHeight = Math.max(Math.min(height * centralGapRatio, 24), 10);
  const studHeight = (height - gapHeight) / 2;
  const topStudY = y;
  const bottomStudY = y + studHeight + gapHeight;
  const mid = y + height / 2;
  const runnerHeight = Math.min(gapHeight * 0.72, 12);
  const runnerWidth = Math.min(width * 0.88, 104);
  const runnerX = x + (width - runnerWidth) / 2;
  const runnerStrokeWidth = Math.max(strokeWidth * 0.72, 1.8);

  return (
    <>
      <ChannelPath x={x} y={topStudY} width={width} height={studHeight} stroke={stroke} strokeWidth={strokeWidth} openSide="left" />
      <ChannelPath
        x={x}
        y={bottomStudY}
        width={width}
        height={studHeight}
        stroke="#64748b"
        strokeWidth={strokeWidth}
        openSide="left"
        flipY
      />
      <g transform={`rotate(-7 ${x + width / 2} ${mid})`}>
        <rect
          x={runnerX}
          y={mid - runnerHeight - 2}
          width={runnerWidth}
          height={runnerHeight}
          fill="#e2e8f0"
          stroke={secondaryStroke}
          strokeWidth={runnerStrokeWidth}
        />
        <rect
          x={runnerX + 8}
          y={mid + 2}
          width={runnerWidth - 16}
          height={runnerHeight}
          fill="#f8fafc"
          stroke={secondaryStroke}
          strokeWidth={runnerStrokeWidth}
        />
        <line
          x1={runnerX + 10}
          x2={runnerX + runnerWidth - 10}
          y1={mid - runnerHeight / 2 - 2}
          y2={mid - runnerHeight / 2 - 2}
          stroke="#94a3b8"
          strokeWidth={1}
        />
      </g>
    </>
  );
}

function ChStudPath({
  x,
  y,
  width,
  height,
  stroke,
  strokeWidth,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  stroke: string;
  strokeWidth: number;
}) {
  const left = x + 10;
  const right = x + width - 10;
  const top = y + 8;
  const bottom = y + height - 8;
  const lip = Math.min(width * 0.18, 16);
  const mid = x + width / 2;
  const path = `M ${left} ${top} H ${right} V ${bottom} H ${mid} V ${bottom - height * 0.35} M ${left} ${top} V ${top + lip} M ${mid} ${bottom} H ${left}`;
  return <path d={path} fill="none" stroke={stroke} strokeLinecap="square" strokeLinejoin="miter" strokeWidth={strokeWidth} vectorEffect="non-scaling-stroke" />;
}

function IStudPath({
  x,
  y,
  width,
  height,
  stroke,
  strokeWidth,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  stroke: string;
  strokeWidth: number;
}) {
  const left = x + 12;
  const right = x + width - 12;
  const top = y + 8;
  const bottom = y + height - 8;
  const mid = x + width / 2;
  const path = `M ${left} ${top} H ${right} M ${mid} ${top} V ${bottom} M ${left} ${bottom} H ${right}`;
  return <path d={path} fill="none" stroke={stroke} strokeLinecap="square" strokeLinejoin="miter" strokeWidth={strokeWidth} vectorEffect="non-scaling-stroke" />;
}

function HrStudPath({
  x,
  y,
  width,
  height,
  stroke,
  strokeWidth,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  stroke: string;
  strokeWidth: number;
}) {
  const left = x + 12;
  const right = x + width - 12;
  const top = y + 8;
  const bottom = y + height - 8;
  const webLeft = x + width * 0.38;
  const webRight = x + width * 0.62;
  const path = `M ${left} ${top} H ${right} V ${top + 10} M ${right} ${bottom} H ${left} V ${bottom - 10} M ${webRight} ${top} V ${y + height * 0.34} L ${webLeft} ${y + height * 0.46} V ${y + height * 0.56} L ${webRight} ${y + height * 0.68} V ${bottom}`;
  return <path d={path} fill="none" stroke={stroke} strokeLinecap="square" strokeLinejoin="miter" strokeWidth={strokeWidth} vectorEffect="non-scaling-stroke" />;
}

function SilentStudPath({
  x,
  y,
  width,
  height,
  stroke,
  strokeWidth,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  stroke: string;
  strokeWidth: number;
}) {
  const left = x + 10;
  const right = x + width - 10;
  const top = y + 8;
  const bottom = y + height - 8;
  const notch = width * 0.26;
  const path = `M ${left} ${top} H ${right} V ${y + height * 0.28} H ${right - notch} V ${y + height * 0.38} H ${right} V ${y + height * 0.62} H ${right - notch} V ${y + height * 0.72} H ${right} V ${bottom} H ${left} V ${bottom - 10} M ${left} ${top} V ${top + 10}`;
  return <path d={path} fill="none" stroke={stroke} strokeLinecap="square" strokeLinejoin="miter" strokeWidth={strokeWidth} vectorEffect="non-scaling-stroke" />;
}
