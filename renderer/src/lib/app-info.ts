// 화면 표시용 앱 버전. package.json version을 단일 기준으로 사용한다.
import packageJson from "../../package.json";

export const APP_VERSION: string = packageJson.version;
