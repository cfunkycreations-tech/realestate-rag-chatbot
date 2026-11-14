import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTypeScript from 'eslint-config-next/typescript';

const config = [
  ...nextVitals,
  ...nextTypeScript,
  { ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts'] },
  // The existing monolithic page clears stale chat state on Bot changes.
  // Refactor that lifecycle when the page is split into components.
  { files: ['app/page.tsx'], rules: { 'react-hooks/set-state-in-effect': 'off' } },
];
export default config;
