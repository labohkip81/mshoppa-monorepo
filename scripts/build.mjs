import { spawnSync } from 'node:child_process';
for (const app of ['marketing', 'merchant-admin', 'platform-admin', 'storefront', 'payments']) {
  const result = spawnSync('node', ['node_modules/@angular/cli/bin/ng.js', 'build', app], { stdio: 'inherit', env: { ...process.env, NG_CLI_ANALYTICS: 'false' } });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
