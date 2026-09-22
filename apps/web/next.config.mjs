/** @type {import('next').NextConfig} */
const nextConfig = {
  // Cloud Run can image nho; standalone gom san runtime vao .next/standalone
  output: "standalone",
  reactStrictMode: true,
  // `next dev` tu sinh AGENTS.md + CLAUDE.md trong apps/web khi phat hien
  // AI agent chay lenh (bien moi truong CLAUDECODE, CURSOR_AGENT…). Tat
  // di: hai file do khong phai cua du an, va Next tu ghi de chung moi lan
  // chay. Tai lieu cua du an nam o README.md va docs/.
  agentRules: false,
};

export default nextConfig;
