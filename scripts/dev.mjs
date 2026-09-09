import { spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { parseEnv } from 'node:util';
import { resolve } from 'node:path';

const python = resolve('services/core/.venv/bin/python');
if (!existsSync(python)) {
  console.error('Install the backend first: cd services/core && uv sync');
  process.exit(1);
}
const children = [];
let stopping = false;
function stop() {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill('SIGTERM');
}
function start(command, args, cwd) {
  const paymentEnv = resolve('services/payments/.env');
  const env = cwd === 'services/payments' && existsSync(paymentEnv) ? { ...parseEnv(readFileSync(paymentEnv,'utf8')), ...process.env } : process.env;
  const child = spawn(command, args, { cwd, stdio:'inherit', env });
  children.push(child);
  child.on('error', error => { console.error(error.message); process.exitCode = 1; stop(); });
  child.on('exit', code => { if (!stopping) { process.exitCode = code || 1; stop(); } });
}
start(python, ['manage.py','runserver','127.0.0.1:8000','--noreload'], 'services/core');
start(python, ['manage.py','runserver','127.0.0.1:8001','--noreload'], 'services/payments');
start(python, ['manage.py','process_jobs'], 'services/core');
for (const [name, port] of [['marketing',4200],['merchant-admin',4201],['platform-admin',4202],['storefront',4203],['payments',4204]]) {
  start(process.execPath, ['node_modules/@angular/cli/bin/ng.js','serve',name,'--port',String(port), ...(name === 'payments' ? ['--proxy-config','apps/payments/proxy.conf.json'] : [])], process.cwd());
}
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
console.log('\nMSHOPPA local development:');
console.log('Landing: http://localhost:4200');
console.log('Business: http://admin.localhost:4201');
console.log('Platform: http://platform.localhost:4202');
console.log('Stores: http://<store-slug>.localhost:4203');
console.log('Payments: http://payments.localhost:4204\n');
