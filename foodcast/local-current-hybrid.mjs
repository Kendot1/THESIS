// Read-only localhost:3000: incumbent daily + genuine current frozen weekly/monthly.
import { spawn } from 'node:child_process';
const child = spawn(process.execPath, ['node_modules/dotenv-cli/cli.js', '-e', '../.env', '--', process.execPath, 'node_modules/next/dist/bin/next', 'dev', '--webpack', '--port', '3000'], {
 cwd: 'D:/THESIS/foodcast', stdio: 'inherit',
 env: { ...process.env, NODE_ENV: 'development', NEXT_PUBLIC_FOODCAST_LOCAL_MODEL: 'current-hybrid', FOODCAST_LOCAL_RESEARCH: 'current-hybrid', FOODCAST_LOCAL_READ_ONLY: '1' },
});
child.on('exit', code => { process.exitCode = code ?? 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
