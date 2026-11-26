/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  poweredByHeader: false,
  eslint: { ignoreDuringBuilds: true },
  async rewrites() {
    // Local development without Caddy: API_ORIGIN=http://localhost:8000 npm run dev
    const origin = process.env.API_ORIGIN;
    return origin
      ? [
          { source: '/api/:path*', destination: `${origin}/api/:path*` },
          { source: '/docs', destination: `${origin}/docs` },
          { source: '/docs/:path*', destination: `${origin}/docs/:path*` },
          { source: '/openapi.json', destination: `${origin}/openapi.json` },
          { source: '/redoc', destination: `${origin}/redoc` },
        ]
      : [];
  },
};
export default nextConfig;
