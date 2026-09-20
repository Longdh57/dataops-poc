/** @type {import('next').NextConfig} */
const nextConfig = {
  // Cloud Run can image nho; standalone gom san runtime vao .next/standalone
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
