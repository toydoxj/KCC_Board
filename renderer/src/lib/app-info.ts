// 화면 표시용 앱 버전. package.json version을 단일 기준으로 사용한다.
import packageJson from "../../package.json";

export const APP_VERSION: string = packageJson.version;

// 통일 제목(기술인증 신청명, 2차 심사의견 E-2·B-3). package.json programTitle 단일 기준
export const APP_TITLE: string = packageJson.programTitle;
export const APP_SHORT_NAME = "KCC Board";
export const APP_FULL_TITLE = `${APP_TITLE} (${APP_SHORT_NAME})`;
