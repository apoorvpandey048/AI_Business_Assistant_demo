/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Same-origin API proxy: the browser calls /api/* (the UI's own origin) and the Next
  // server forwards to the backend. This means the whole app works behind a single public
  // origin (e.g. a Cloudflare tunnel) with no CORS and no second exposed port.
  async rewrites() {
    const target = process.env.API_PROXY_TARGET || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${target}/:path*` }];
  },
};
module.exports = nextConfig;
