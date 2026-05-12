/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  // Static export → out/. We copy out/* into ../web/dist/ to keep
  // the existing Cloudflare deploy target stable.
};

module.exports = nextConfig;
