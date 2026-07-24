/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Host-side typecheck builds (`NEXT_DIST_DIR=.next-build npm run build`) must
  // not write into the same .next the containerized dev server owns — both see
  // this directory through the bind mount, and a host build corrupts dev state.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
