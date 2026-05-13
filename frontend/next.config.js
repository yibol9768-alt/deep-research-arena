/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  // Allow reading data files from the parent project directory at build time.
  experimental: {
    outputFileTracingRoot: require('path').join(__dirname, '..'),
  },
}

module.exports = nextConfig
