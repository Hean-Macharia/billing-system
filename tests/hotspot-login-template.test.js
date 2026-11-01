const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const MikrotikLogin = require('../hotspot/mikrotik-login.js');

const template = fs.readFileSync(path.join(__dirname, '../hotspot/login.html'), 'utf8');

test('RouterOS login template forwards all captive parameters without rewriting CHAP bytes', () => {
  for (const [name, variable] of [
    ['link-login-only', '$(link-login-only)'],
    ['link-orig', '$(link-orig-esc)'],
    ['chap-id', '$(chap-id)'],
    ['chap-challenge', '$(chap-challenge)'],
    ['client_ip', '$(ip)'],
    ['client_mac', '$(mac)'],
  ]) {
    assert.match(template, new RegExp(`name="${name}" value="${variable.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"`));
  }

  assert.match(template, /https:\/\/billing-system-5ckp\.onrender\.com\/hotspot\//);
  assert.match(template, /Do not decode, hex-encode, or otherwise rewrite CHAP fields/);
  assert.doesNotMatch(template, /normalizeChap|parseInt\([^)]*,\s*8\)|toString\(16\)/);
});

test('RouterOS-style form encoding preserves octal CHAP and double-encoded original destination for the hosted parser', () => {
  const fields = new URLSearchParams({
    'link-login-only': 'http://login.hean.local/login',
    'link-orig': 'http%3A%2F%2Fconnectivitycheck.gstatic.com%2Fgenerate_204',
    'chap-id': '\\213',
    'chap-challenge': '\\277\\154\\110\\145\\127\\347\\223\\373\\157\\252\\232\\270\\110\\011\\006\\314',
    client_ip: '192.168.89.200',
    client_mac: 'AA:BB:CC:DD:EE:FF',
  });
  const parsed = MikrotikLogin.parseRedirectParameters(`?${fields.toString()}`);

  assert.equal(parsed.ok, true);
  assert.equal(parsed.chapId, '\\213');
  assert.equal(parsed.chapChallenge, '\\277\\154\\110\\145\\127\\347\\223\\373\\157\\252\\232\\270\\110\\011\\006\\314');
  assert.equal(parsed.destination, 'http://connectivitycheck.gstatic.com/generate_204');
  const submission = MikrotikLogin.createLoginSubmission(parsed, 'TEST-VOUCHER');
  assert.equal(submission.action, 'http://login.hean.local/login');
  assert.equal(submission.fields.username, 'TEST-VOUCHER');
  assert.match(submission.fields.password, /^[0-9a-f]{32}$/);
  assert.equal(submission.fields.dst, 'http://connectivitycheck.gstatic.com/generate_204');
});
