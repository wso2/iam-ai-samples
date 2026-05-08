#!/usr/bin/env node
const path = require('node:path');
const fs = require('node:fs');
const { spawn } = require('node:child_process');

const pkg = require('../package.json');

const DEFAULTS = {
  port: 4829,
  host: 'localhost',
  open: true,
};

function printHelp() {
  process.stdout.write(
    `agent-auth-playground v${pkg.version}\n\n` +
      `Visual AI workflow builder — runs a local server in your browser.\n\n` +
      `Usage:\n` +
      `  npx agent-auth-playground [options]\n\n` +
      `Options:\n` +
      `  --port <number>   Port to listen on (default: ${DEFAULTS.port})\n` +
      `  --host <string>   Host to bind to     (default: ${DEFAULTS.host})\n` +
      `  --no-open         Don't open the browser automatically\n` +
      `  -h, --help        Show this help\n` +
      `  -v, --version     Show version\n`
  );
}

function parseArgs(argv) {
  const out = { ...DEFAULTS };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case '-h':
      case '--help':
        out._help = true;
        break;
      case '-v':
      case '--version':
        out._version = true;
        break;
      case '--no-open':
        out.open = false;
        break;
      case '--open':
        out.open = true;
        break;
      case '--port': {
        const v = Number(argv[++i]);
        if (!Number.isInteger(v) || v <= 0 || v > 65535) {
          console.error(`Invalid --port: ${argv[i]}`);
          process.exit(1);
        }
        out.port = v;
        break;
      }
      case '--host':
        out.host = argv[++i];
        if (!out.host) {
          console.error('Missing value for --host');
          process.exit(1);
        }
        break;
      default:
        console.error(`Unknown argument: ${a}`);
        printHelp();
        process.exit(1);
    }
  }
  return out;
}

function openBrowser(url) {
  const platform = process.platform;
  const cmd = platform === 'win32' ? 'cmd' : platform === 'darwin' ? 'open' : 'xdg-open';
  const args = platform === 'win32' ? ['/c', 'start', '""', url] : [url];
  try {
    const child = spawn(cmd, args, { stdio: 'ignore', detached: true, shell: false });
    child.on('error', () => {});
    child.unref();
  } catch {
    // ignore — the URL is also printed
  }
}

const args = parseArgs(process.argv.slice(2));

if (args._help) {
  printHelp();
  process.exit(0);
}
if (args._version) {
  process.stdout.write(`${pkg.version}\n`);
  process.exit(0);
}

const standaloneDir = path.resolve(__dirname, '..', '.next', 'standalone');
const serverPath = path.join(standaloneDir, 'server.js');

if (!fs.existsSync(serverPath)) {
  console.error(
    `[agent-auth-playground] Build artifact not found at ${serverPath}.\n` +
      `If you're running from source, run \`pnpm build && node scripts/postbuild.js\` first.`
  );
  process.exit(1);
}

const url = `http://${args.host}:${args.port}`;

process.env.PORT = String(args.port);
process.env.HOSTNAME = args.host;
process.env.NEXT_PUBLIC_APP_URL = url;

// server.js calls process.chdir(__dirname) itself — no need to do it here.

process.stdout.write(
  `\n  agent-auth-playground v${pkg.version}\n` +
    `  ➜  Local:   ${url}\n` +
    `  ➜  Press Ctrl+C to stop\n\n`
);

if (args.open) {
  setTimeout(() => openBrowser(url), 600);
}

const shutdown = (signal) => () => {
  process.stdout.write(`\n[agent-auth-playground] received ${signal}, shutting down\n`);
  process.exit(0);
};
process.on('SIGINT', shutdown('SIGINT'));
process.on('SIGTERM', shutdown('SIGTERM'));

require(serverPath);
