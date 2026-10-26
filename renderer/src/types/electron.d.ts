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
    };
  }
}
