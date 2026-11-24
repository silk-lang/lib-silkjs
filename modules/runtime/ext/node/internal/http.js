// Copyright Joyent, Inc. and other Node contributors. MIT license (see vendor/node-api/LICENSE).
// Adapted from Node.js v24.22.1 lib/internal/http.js (primordials replaced by plain calls).
'use strict';

const httpNative = require('internal/host').httpParserNative;
const traceEvents = require('internal/trace_events');

const { URL } = require('internal/url');
const { Buffer } = require('buffer');
const { ERR_PROXY_INVALID_CONFIG } = require('internal/errors').codes;

function utcDate() {
  return httpNative(23, false);
}

let traceEventId = 0;

function getNextTraceEventId() {
  return ++traceEventId;
}

function isTraceHTTPEnabled() {
  return traceEvents.enabled('node.http');
}

const traceEventCategory = 'node,node.http';

function traceBegin(name, id, args) {
  traceEvents.emit(traceEventCategory, name, 'b', args, id);
}

function traceEnd(name, id, args) {
  traceEvents.emit(traceEventCategory, name, 'e', args, id);
}

// There are two factors in play when proxying the request:
// 1. What the request protocol is, that is, whether users are sending it via
//    http.request or https.request, or whether they are sending
//    the request to a https:// URL or a http:// URL. HTTPS requests should be
//    proxied by the proxy specified using the HTTPS_PROXY environment variable.
//    HTTP requests should be proxied by the proxy specified using the HTTP_PROXY
//    environment variable.
// 2. What the proxy protocol is. This depends on the value of the environment variables,
//    for example.
//
// When proxying a HTTP request, the following needs to be done:
// https://datatracker.ietf.org/doc/html/rfc7230#section-5.3.2
// 1. Rewrite the request path to absolute-form.
// 2. Add proxy-connection and proxy-authorization headers appropriately.
//
// When proxying a HTTPS request, the following needs to be done:
// https://datatracker.ietf.org/doc/html/rfc9110#CONNECT
// 1. Send a CONNECT request to the proxy server.
// 2. Wait for 200 connection established response to establish the tunnel.
// 3. Perform TLS handshake with the endpoint through the tunnel.
// 4. Tunnel the request using the established connection.
//
// When the proxy protocol is HTTP, the modified HTTP request can just be sent over
// the TCP socket to the proxy server, and the HTTPS request tunnel can be established
// over the TCP socket to the proxy server.
// When the proxy protocol is HTTPS, the modified request needs to be sent after
// TLS handshake with the proxy server. Same goes to the HTTPS request tunnel establishment.

/**
 * Represents the proxy configuration for an agent. The built-in http and https agent
 * implementation have one of this when they are configured to use a proxy.
 * @property {string} href - Proxy server URL with credentials redacted.
 * @property {string} protocol - Proxy protocol used to talk to the proxy server.
 * @property {string|undefined} auth - proxy-authorization header value, if username or password is provided.
 * @property {Array<string>} bypassList - List of hosts to bypass the proxy.
 * @property {object} proxyConnectionOptions - Options for connecting to the proxy server.
 */
class ProxyConfig {
  constructor(proxyUrl, keepAlive, noProxyList) {
    let parsedURL;
    try {
      parsedURL = new URL(proxyUrl);
    } catch {
      throw new ERR_PROXY_INVALID_CONFIG(`Invalid proxy URL: ${proxyUrl}`);
    }
    const { hostname, port, protocol, username, password } = parsedURL;

    if (username || password) {
      parsedURL.username = '';
      parsedURL.password = '';
      this.href = parsedURL.href;
    } else {
      this.href = proxyUrl;
    }
    this.protocol = protocol;

    if (username || password) {
      // If username or password is provided, prepare the proxy-authorization header.
      const auth = `${decodeURIComponent(username)}:${decodeURIComponent(password)}`;
      this.auth = `Basic ${Buffer.from(auth).toString('base64')}`;
    }
    this._rawNoProxy = noProxyList || '';
    if (noProxyList) {
      this.bypassList = noProxyList.split(',').map((entry) => entry.trim().toLowerCase());
    } else {
      this.bypassList = []; // No bypass list provided.
    }

    this.proxyConnectionOptions = {
      // The host name comes from parsed URL so if it starts with '[' it must be an IPv6 address
      // ending with ']'. Remove the brackets for net.connect().
      host: hostname[0] === '[' ? hostname.slice(1, -1) : hostname,
      // The port comes from parsed URL so it is either '' or a valid number string.
      port: port ? Number(port) : (protocol === 'https:' ? 443 : 80),
    };
  }

  // See: https://about.gitlab.com/blog/we-need-to-talk-no-proxy
  // TODO(joyeecheung): share code with undici.
  shouldUseProxy(hostname, port) {
    if (this.bypassList.length === 0) {
      return true; // No bypass list, always use the proxy.
    }
    return httpNative(25, this._rawNoProxy, hostname, port ? Number(port) : 0);
  }
}

function parseProxyUrl(env, protocol) {
  // Get the proxy url - following the most popular convention, lower case takes precedence.
  // See https://about.gitlab.com/blog/we-need-to-talk-no-proxy/#http_proxy-and-https_proxy
  const proxyUrl = (protocol === 'https:') ?
    (env.https_proxy || env.HTTPS_PROXY) : (env.http_proxy || env.HTTP_PROXY);
  // No proxy settings from the environment, ignore.
  if (!proxyUrl) {
    return null;
  }

  if (proxyUrl.includes('\r') || proxyUrl.includes('\n')) {
    throw new ERR_PROXY_INVALID_CONFIG(`Invalid proxy URL: ${proxyUrl}`);
  }

  return proxyUrl;
}

function parseProxyConfigFromEnv(env, protocol, keepAlive) {
  // We only support proxying for HTTP and HTTPS requests.
  if (protocol !== 'http:' && protocol !== 'https:') {
    return null;
  }

  const proxyUrl = parseProxyUrl(env, protocol);
  if (proxyUrl === null) {
    return null;
  }

  // Only http:// and https:// proxies are supported.
  // Ignore instead of throw, in case other protocols are supposed to be
  // handled by the user land.
  if (!proxyUrl.startsWith('http://') && !proxyUrl.startsWith('https://')) {
    return null;
  }

  const noProxyList = env.no_proxy || env.NO_PROXY;
  return new ProxyConfig(proxyUrl, keepAlive, noProxyList);
}

/**
 * @param {ProxyConfig} proxyConfig
 * @param {object} reqOptions
 * @returns {boolean}
 */
function checkShouldUseProxy(proxyConfig, reqOptions) {
  if (!proxyConfig) {
    return false;
  }
  if (reqOptions.socketPath) {
    // If socketPath is set, the endpoint is a Unix domain socket, which can't
    // be proxied.
    return false;
  }
  return proxyConfig.shouldUseProxy(reqOptions.host || 'localhost', reqOptions.port);
}

function filterEnvForProxies(env) {
  return {
    __proto__: null,
    http_proxy: env.http_proxy,
    HTTP_PROXY: env.HTTP_PROXY,
    https_proxy: env.https_proxy,
    HTTPS_PROXY: env.HTTPS_PROXY,
    no_proxy: env.no_proxy,
    NO_PROXY: env.NO_PROXY,
  };
}

function getGlobalAgent(proxyEnv, Agent) {
  return new Agent({
    keepAlive: true, scheduling: 'lifo', timeout: 5000,
    proxyEnv,
  });
}

module.exports = {
  kOutHeaders: Symbol('kOutHeaders'),
  kNeedDrain: Symbol('kNeedDrain'),
  kProxyConfig: Symbol('kProxyConfig'),
  kWaitForProxyTunnel: Symbol('kWaitForProxyTunnel'),
  checkShouldUseProxy,
  parseProxyConfigFromEnv,
  utcDate,
  traceBegin,
  traceEnd,
  getNextTraceEventId,
  isTraceHTTPEnabled,
  filterEnvForProxies,
  getGlobalAgent,
  parseProxyUrl,
};
