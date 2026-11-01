import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const walk = (directory) => readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
  const full = path.join(directory, entry.name);
  return entry.isDirectory() ? walk(full) : [full];
});
const htmlFiles = ['hotspot', 'admin', 'portal'].flatMap((app) => walk(path.join(root, app)).filter((file) => file.endsWith('.html')));

test('FastAPI mounted application entry points and shared assets are present', () => {
  for (const file of ['hotspot/index.html', 'admin/index.html', 'portal/index.html', 'js/shared-api.js', 'js/shared-ui.js', 'css/brand-system.css']) {
    assert.ok(existsSync(path.join(root, file)), `Missing mounted asset: ${file}`);
  }
});

test('local HTML scripts and styles resolve from every mounted page', () => {
  const failures = [];
  for (const file of htmlFiles) {
    const source = readFileSync(file, 'utf8');
    const refs = [
      ...[...source.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/gi)].map((match) => match[1]),
      ...[...source.matchAll(/<link\b[^>]*\bhref=["']([^"']+)["']/gi)].map((match) => match[1]),
    ];
    for (const reference of refs) {
      if (/^(?:https?:|data:|#|javascript:)/i.test(reference)) continue;
      const assetPath = reference.split(/[?#]/, 1)[0];
      const resolved = assetPath.startsWith('/')
        ? path.resolve(root, assetPath.slice(1))
        : path.resolve(path.dirname(file), assetPath);
      if (!existsSync(resolved)) failures.push(`${path.relative(root, file)} → ${reference}`);
    }
  }
  assert.deepEqual(failures, []);
});

test('mounted HotSpot purchase accepts a target MAC only for router re-attestation', () => {
  const source = readFileSync(path.join(root, 'hotspot/js/app.js'), 'utf8');
  assert.match(source, /data-device-type="tv"/);
  assert.match(source, /data-device-type="other"/);
  assert.match(source, /id="target-device-mac"/);
  assert.match(source, /device_mac: targetMac/);
  assert.match(source, /router can verify it before payment/i);
  assert.match(source, /X-Hotspot-Context/);
  assert.match(source, /device verification is required/i);
});
