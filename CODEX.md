# CLAUDE.md

건식벽체(석고보드·스터드 부분합성) 면외 구조검토 Electron 데스크톱 앱. Claude Code 작업 시 본 문서를 먼저 읽고 진행할 것.

## 1. 프로젝트 개요
- 경량 스터드 + 전·후면 석고보드 부분합성 단면의 **면외 휨·처짐·지진 검토** 엔진과, **단면 자동선정·계산서 자동생성** 데스크톱 앱이다.
- 원본 엑셀(`refs/계산_SHEET_260528_.xlsx` VAR. 시트)의 검증된 역학 로직을 이관한다.
- 상세 요구사항은 `docs/PRD.md`, 계산식은 `docs/var_formula_spec.md` 를 참조한다.

## 2. 기술 스택 / 아키텍처
- **Electron 데스크톱 앱**: Shell=Electron(main/preload), Renderer=Next.js, Local Backend=FastAPI 사이드카.
- Renderer ↔ Backend 는 localhost HTTP(JSON, 127.0.0.1 임의포트). 파일 저장 등 OS 연동은 Electron IPC(preload + contextIsolation) 경유.
- FastAPI 사이드카는 Electron main이 spawn·관리. 배포 시 PyInstaller 번들 또는 프로세스 spawn.
- 계산엔진은 **UI/Electron 비종속 순수함수 파이프라인**으로 분리한다. (DY_MIDAS_PROJECT의 Electron+Next.js+FastAPI / pure functions + Repository/DI + 테스트 우선 패턴과 동일)
- 최적화 모듈은 계산엔진을 **재사용**하며 로직을 중복 구현하지 않는다.
- DB는 **로컬 SQLite**(사용자 데이터 경로). 외부 서버/RDS/Supabase 미사용, 전 기능 오프라인 동작.

```
repo/
├─ CLAUDE.md
├─ docs/        PRD.md, var_formula_spec.md, (kds_references.md)
├─ tests/golden/cases.json    ← 엑셀 회귀 골든값
├─ data/seed/   stud_section / board_property / bolt_material / stud_method (.json)
├─ refs/        원본 xlsx, 단면 시각화 png
└─ (src/)
    ├─ electron/   main, preload (윈도우·IPC·사이드카 관리)
    ├─ renderer/   Next.js (UI)
    └─ backend/    FastAPI(api) + engine(순수함수) + repository + report
```

## 3. 단위계 규약 (엄수)
- 내부 단위: 길이 mm, 면적 mm², 단면계수 mm³, 단면2차 mm⁴, 힘 N/kN, 모멘트 kN·m, 응력 N/mm²
- 표시단위 변환은 표현계층에서만 수행한다. 엔진 내부는 단일 단위계를 유지한다.

## 4. 계산 파이프라인 (11단계, var_formula_spec.md 상세)
1. 탄성계수비 n=E_board/E_stud → 2. 환산유효폭·환산단면적 → 3. 단위·총중량 →
4. 중립축 N15=ΣAy/ΣA → 5. 완전합성 I_full(평행축) → 6. 볼트 전단·지압 →
7. 전단연계 누계·합성률 η(min) → 8. 유효강성 I_eff=I_s+√η·(I_f−I_s) →
9. 공칭휨강도 Mn → 10. 처짐 δ=5wL⁴/384EI(수평하중, 지진제외) →
11. 지진력 Fp(집중하중)·하중조합 → 판정(Ω·Mu/Mn≤1, δ≤L/240)

## 5. 확정된 설계 의도 (변경 금지)
- 24 kg/m² 는 **수평하중**(활하중과 동일 성격), 처짐·휨에 일관 적용.
- 지진하중은 **집중하중**으로 고려 → 면외 모멘트 계수 1/4 적용은 의도된 값.
- 처짐 검토에서 지진은 **제외**.
- ASD 안전계수 Ω=1.5, 처짐한계 기본 L/240. (둘 다 설정값으로 분리, 하드코딩 금지)

## 6. 자재 DB (data/seed)
- `stud_section.json`: 정본 = `스터드_단면성능_2.xlsx` (9그룹·69규격). 컬럼 H,B,t,A,cx,cy,Ix,Iy,Sx,Sy,rx,ry + section_class.
- section_class: closed(직접적분) / thin_plate(T.silent, 박판) / composite_channel(MP·RV, 2채널 합).
- `board_property.json`: 종류×두께 → mass, Fy, E_GPa (E는 *10³ 후 N/mm²).
- `bolt_material.json`, `stud_method.json`.
- DB 조회는 **그룹+단면명 키** 사용(엑셀 VLOOKUP 인덱스 의존 제거). 미스 시 **명시적 예외**(silent #N/A 금지).

## 7. 검증 규칙 (필수)
- `tests/golden/cases.json` 의 expected 와 엔진 출력을 **상대오차 ≤ 0.1%** 로 대조하는 회귀테스트를 포함한다.
- 골든값은 현재 엑셀(FIX-01 반영: `N13=SUM(G13:M13)`) 기준이다.
- 단면값 변동(신규 단면성능의 T.silent 등) 케이스를 추가할 때는 골든값을 재산정한다.
- 모든 계산 단계의 중간값을 반환하여(계산서·디버깅) 셀 단위 대조가 가능해야 한다.

## 8. 기존 엑셀 로직 개선 항목 (승인 기반 반영)
- FIX-01 지진중량 후면보드 포함: **현재 엑셀에 이미 반영됨**(`SUM(G13:M13)`). 엔진도 전 레이어 합산.
- FIX-02 합성률 η 분모 비일관 → 완전합성 필요전단력 정의를 단일 규칙으로 통일(승인 후).
- FIX-03 중립축 IF 분기(`OR(C5,C6)→1`) → 시공방식 무관 적층높이 누계 적용.
- FIX-04 SCREWBOLT `#REF!` → 볼트강도식 재바인딩/재정식화.
- FIX-05 빈 레이어 `----` 제거 → 가변 레이어 모델.
- **결과(판정)에 영향하는 변경은 사용자 승인 후 반영한다. 무단 변경 금지.**

## 9. 출처 표기 의무 (Open Issues)
KDS/AISC 인용 시 기준명+조항번호를 코드 주석·계산서에 명시한다. 미확정 항목은 "확인 필요" 표기.
- OI-01 부분합성 √η (AISC 360 / KDS 41 30 30 — 확인 필요)
- OI-02 지진력 Sds 2.5·Fp 0.48 (KDS 41 17 00 — 확인 필요)
- OI-08 박판 유효폭 (KDS 41 30 30 — 반영 여부 확인 필요)

## 10. 코드 스타일 / 금지사항
- 한국어 주석 허용(기술용어·변수명 영문). 응답·문서는 보고서체(~이다/~임).
- 파일 단위 작성, 변경 전/후 및 테스트 방법 명시. 50줄 이하 단순수정만 인라인.
- 기존 아키텍처 패턴을 사전 파악하고, 불명확하면 질문한다. **무단 아키텍처 변경 금지.**
- 하드코딩 금지(상수는 설정 분리). silent 실패 금지(예외 명시).
- 작업 전 단계별 계획 제시 후 진행.
