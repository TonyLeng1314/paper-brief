// @ts-check
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://TonyLeng1314.github.io',
  base: '/paper-brief',
  output: 'static',
  build: {
    format: 'directory',
  },
  trailingSlash: 'always',
  vite: {
    server: { host: true },
  },
});
