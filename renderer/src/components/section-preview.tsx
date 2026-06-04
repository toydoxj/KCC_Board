import type { BoardProperty, StudSection } from "@/lib/api";

interface SectionPreviewProps {
  rearBoards: BoardProperty[];
  frontBoards: BoardProperty[];
  stud: StudSection | undefined;
}

export function SectionPreview({ rearBoards, frontBoards, stud }: SectionPreviewProps) {
  const boardUnit = 12;
  const rearHeight = rearBoards.reduce((sum, board) => sum + board.thickness * 2.2, 0);
  const studHeight = Math.max((stud?.H ?? 50) * 1.2, 48);
  const frontHeight = frontBoards.reduce((sum, board) => sum + board.thickness * 2.2, 0);
  const totalHeight = rearHeight + studHeight + frontHeight;
  const viewHeight = Math.max(totalHeight + 32, 180);
  let cursor = 16;

  const rearRects = rearBoards.map((board, index) => {
    const height = Math.max(board.thickness * 2.2, boardUnit);
    const y = cursor;
    cursor += height;
    return { key: `rear-${index}`, y, height, label: `${board.thickness}T` };
  });
  const studY = cursor;
  cursor += studHeight;
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
      <rect x="104" y={studY} width="112" height={studHeight} rx="2" fill="#d7e5ee" stroke="#1f6f8b" />
      <rect x="126" y={studY + 12} width="68" height={Math.max(studHeight - 24, 20)} rx="2" fill="#f8fafc" stroke="#1f6f8b" />
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
