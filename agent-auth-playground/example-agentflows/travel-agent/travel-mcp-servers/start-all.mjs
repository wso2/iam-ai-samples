/**
 * Copyright (c) 2026, WSO2 LLC. (https://www.wso2.com).
 *
 * WSO2 LLC. licenses this file to you under the Apache License,
 * Version 2.0 (the "License"); you may not use this file except
 * in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { spawn } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import process from 'node:process';

const envFile = '.env';
const childEnv = { ...process.env };
if (existsSync(envFile)) {
    for (const raw of readFileSync(envFile, 'utf8').split(/\r?\n/)) {
        const line = raw.trim();
        if (!line || line.startsWith('#')) continue;
        const eq = line.indexOf('=');
        if (eq === -1) continue;
        const key = line.slice(0, eq).trim();
        let val = line.slice(eq + 1).trim();
        if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
            val = val.slice(1, -1);
        }
        if (childEnv[key] === undefined) childEnv[key] = val;
    }
}

const servers = [
    { name: 'flight-search    ', file: 'flight-search-mcp.ts',        color: '\x1b[36m' },
    { name: 'hotel-search     ', file: 'hotel-search-mcp.ts',         color: '\x1b[35m' },
    { name: 'currency-convert ', file: 'currency-converter-mcp.ts',   color: '\x1b[33m' },
    { name: 'booking-manager  ', file: 'booking-manager-mcp.ts', color: '\x1b[32m' },
    { name: 'airport-lounge   ', file: 'airport-lounge-mcp.ts',  color: '\x1b[34m' },
];
const RESET = '\x1b[0m';

const children = servers.map(({ name, file, color }) => {
    const child = spawn(`npx tsx ${file}`, {
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: true,
        env: childEnv,
    });

    const prefix = (line) => `${color}[${name}]${RESET} ${line}`;
    const pipe = (stream, out) => {
        let buf = '';
        stream.on('data', (chunk) => {
            buf += chunk.toString();
            const lines = buf.split('\n');
            buf = lines.pop();
            for (const line of lines) out.write(prefix(line) + '\n');
        });
    };
    pipe(child.stdout, process.stdout);
    pipe(child.stderr, process.stderr);

    child.on('exit', (code) => {
        process.stdout.write(prefix(`exited with code ${code}`) + '\n');
    });

    return child;
});

const shutdown = () => {
    for (const c of children) {
        if (!c.killed) c.kill();
    }
    process.exit(0);
};
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
