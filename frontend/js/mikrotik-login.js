(function (root, factory) {
  const mikrotikLogin = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = mikrotikLogin;
  }
  root.MikrotikLogin = mikrotikLogin;
})(globalThis, function () {
  const LOGIN_ERROR = 'The MikroTik login URL is missing or invalid. Open the WiFi login page again, then retry.';
  const CHAP_ERROR = 'The MikroTik CHAP challenge is missing or invalid. Open the WiFi login page again, then retry.';

  function isRouterHost(hostname) {
    const host = hostname.toLowerCase();
    const parts = host.split('.');
    const ipv4 = parts.map(Number);
    const privateIpv4 = parts.length === 4
      && ipv4.every((part) => Number.isInteger(part) && part >= 0 && part <= 255)
      && (
        ipv4[0] === 10
        || (ipv4[0] === 172 && ipv4[1] >= 16 && ipv4[1] <= 31)
        || (ipv4[0] === 192 && ipv4[1] === 168)
      );
    const localDnsName = /(?:^|\.)[\w-]+\.(?:lan|local|hotspot)$/.test(host);
    return privateIpv4 || localDnsName;
  }

  function getSafeDestination(rawDestination) {
    if (!rawDestination) return { destination: '', invalid: false };
    try {
      const destination = new URL(rawDestination);
      if (!['http:', 'https:'].includes(destination.protocol)) {
        return { destination: '', invalid: true };
      }
      return { destination: destination.href, invalid: false };
    } catch {
      return { destination: '', invalid: true };
    }
  }

  function parseRedirectParameters(search) {
    const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
    const hasRouterParameters = [
      'link-login-only',
      'link-login',
      'login_url',
      'chap-id',
      'chap-challenge',
    ].some((name) => params.has(name));
    const rawLoginUrl = params.get('link-login-only')
      || params.get('link-login')
      || params.get('login_url');

    if (!rawLoginUrl) {
      return {
        ok: false,
        state: hasRouterParameters ? 'invalid' : 'missing',
        message: hasRouterParameters ? LOGIN_ERROR : '',
      };
    }

    let loginUrl;
    try {
      loginUrl = new URL(rawLoginUrl);
    } catch {
      return { ok: false, state: 'invalid', message: LOGIN_ERROR };
    }

    const expectedPath = loginUrl.pathname === '/login' || loginUrl.pathname === '/login/';
    if (
      !['http:', 'https:'].includes(loginUrl.protocol)
      || loginUrl.username
      || loginUrl.password
      || !expectedPath
      || !['', '80', '443'].includes(loginUrl.port)
      || !isRouterHost(loginUrl.hostname)
    ) {
      return { ok: false, state: 'invalid', message: LOGIN_ERROR };
    }

    const chapId = params.get('chap-id');
    const chapChallenge = params.get('chap-challenge');
    if (
      !chapId
      || chapId.length > 16
      || !/^[\x20-\x7e]+$/.test(chapId)
      || !chapChallenge
      || chapChallenge.length > 128
      || !/^[\x20-\x7e]+$/.test(chapChallenge)
    ) {
      return { ok: false, state: 'invalid', message: CHAP_ERROR };
    }

    const rawDestination = params.get('link-orig')
      || params.get('link-orig-esc')
      || params.get('dst')
      || '';
    const { destination, invalid: invalidDestination } = getSafeDestination(rawDestination);

    return {
      ok: true,
      state: 'ready',
      action: loginUrl.href,
      destination,
      chapId,
      chapChallenge,
      message: invalidDestination
        ? 'The requested destination was invalid; you can still connect and browse.'
        : '',
    };
  }

  function md5Hex(value) {
    const bytes = Array.from(new TextEncoder().encode(value));
    const bitLength = bytes.length * 8;
    bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);

    const lowLength = bitLength >>> 0;
    const highLength = Math.floor(bitLength / 0x100000000);
    for (let i = 0; i < 4; i += 1) bytes.push((lowLength >>> (i * 8)) & 0xff);
    for (let i = 0; i < 4; i += 1) bytes.push((highLength >>> (i * 8)) & 0xff);

    const shifts = [
      7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
      5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
      4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
      6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21,
    ];
    const constants = Array.from({ length: 64 }, (_, i) => (
      Math.floor(Math.abs(Math.sin(i + 1)) * 0x100000000) | 0
    ));
    let a0 = 0x67452301;
    let b0 = 0xefcdab89 | 0;
    let c0 = 0x98badcfe | 0;
    let d0 = 0x10325476;

    for (let offset = 0; offset < bytes.length; offset += 64) {
      const words = new Array(16);
      for (let i = 0; i < 16; i += 1) {
        const index = offset + i * 4;
        words[i] = (
          bytes[index]
          | (bytes[index + 1] << 8)
          | (bytes[index + 2] << 16)
          | (bytes[index + 3] << 24)
        );
      }

      let a = a0;
      let b = b0;
      let c = c0;
      let d = d0;

      for (let i = 0; i < 64; i += 1) {
        let f;
        let g;
        if (i < 16) {
          f = (b & c) | (~b & d);
          g = i;
        } else if (i < 32) {
          f = (d & b) | (~d & c);
          g = (5 * i + 1) % 16;
        } else if (i < 48) {
          f = b ^ c ^ d;
          g = (3 * i + 5) % 16;
        } else {
          f = c ^ (b | ~d);
          g = (7 * i) % 16;
        }

        const sum = (a + f + constants[i] + words[g]) | 0;
        const rotated = (sum << shifts[i]) | (sum >>> (32 - shifts[i]));
        a = d;
        d = c;
        c = b;
        b = (b + rotated) | 0;
      }

      a0 = (a0 + a) | 0;
      b0 = (b0 + b) | 0;
      c0 = (c0 + c) | 0;
      d0 = (d0 + d) | 0;
    }

    return [a0, b0, c0, d0]
      .map((word) => [0, 8, 16, 24]
        .map((shift) => ((word >>> shift) & 0xff).toString(16).padStart(2, '0'))
        .join(''))
      .join('');
  }

  function createLoginSubmission(redirect, voucherCode) {
    if (!redirect.ok) throw new Error(redirect.message || LOGIN_ERROR);
    const code = String(voucherCode ?? '').trim();
    if (!code) throw new Error('Enter your WiFi voucher code before connecting.');

    return {
      action: redirect.action,
      method: 'post',
      fields: {
        username: code,
        password: md5Hex(`${redirect.chapId}${code}${redirect.chapChallenge}`),
        ...(redirect.destination ? { dst: redirect.destination } : {}),
      },
    };
  }

  return { parseRedirectParameters, createLoginSubmission };
});
