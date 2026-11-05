export {};

declare global {
  interface Window {
    kccBoard?: {
      saveReportPdf(options: { suggestedFileName: string }): Promise<{
        success: boolean;
        canceled: boolean;
        path?: string;
        error?: string;
      }>;
      // Electron 메인 프로세스가 할당한 동적 포트의 API 주소 (2차 심사의견 E-3)
      getApiBaseUrl?(): Promise<string>;
    };
  }
}
