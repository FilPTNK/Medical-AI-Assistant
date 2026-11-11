const pagePaths = ['/thuoc', '/hoi-dap', '/chan-doan', '/quan-tri', '/dang-nhap', '/dieu-khoan'];
const apiPath = '/api/:path*';
const backendOrigin = process.env.FIL_BACKEND_ORIGIN?.trim();
const backend = backendOrigin && URL.canParse(backendOrigin) ? new URL(backendOrigin) : null;

if (backendOrigin && (!backend || backend.protocol !== 'https:' || backend.pathname !== '/'
    || backend.username || backend.password || backend.search || backend.hash)) {
  throw new Error('FIL_BACKEND_ORIGIN must be an HTTPS origin such as https://api.example.com.');
}

export const config = {
  $schema: 'https://openapi.vercel.sh/vercel.json',
  rewrites: [
    ...(backend ? [{ source: apiPath, destination: backend.origin + apiPath }] : []),
    ...pagePaths.map(source => ({ source, destination: '/index.html' })),
  ],
  ...(backend && {
    headers: [{
      source: apiPath,
      headers: [
        { key: 'Cache-Control', value: 'private, no-store' },
        { key: 'x-vercel-enable-rewrite-caching', value: '0' },
      ],
    }],
  }),
};
