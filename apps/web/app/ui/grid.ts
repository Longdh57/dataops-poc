"use client";

// AG Grid v36 khong tu nap module nua — phai dang ky ro rang. Dang ky mot
// lan o day roi moi luoi import tu day, trong khong nap trung.

import { AllCommunityModule, ModuleRegistry, themeQuartz } from "ag-grid-community";

ModuleRegistry.registerModules([AllCommunityModule]);

/** Theme khop bang mau cua ung dung — khong nap file CSS cua AG Grid. */
export const gridTheme = themeQuartz.withParams({
  accentColor: "#0f6b7b",
  backgroundColor: "#ffffff",
  borderColor: "#e4eaef",
  browserColorScheme: "light",
  foregroundColor: "#3c4853",
  headerBackgroundColor: "#f5f7f9",
  headerTextColor: "#6b7884",
  headerFontSize: 11,
  headerFontWeight: 600,
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  fontSize: 13,
  rowHeight: 34,
  headerHeight: 36,
  oddRowBackgroundColor: "#fbfcfd",
  selectedRowBackgroundColor: "#dceef1",
  wrapperBorderRadius: 10,
  spacing: 6,
});
