// Copyright Joyent, Inc. and other Node contributors.
// Adapted from Node.js v24.22.1 lib/_http_outgoing.js (primordials replaced by plain calls).
//
// Permission is hereby granted, free of charge, to any person obtaining a
// copy of this software and associated documentation files (the
// "Software"), to deal in the Software without restriction, including
// without limitation the rights to use, copy, modify, merge, publish,
// distribute, sublicense, and/or sell copies of the Software, and to permit
// persons to whom the Software is furnished to do so, subject to the
// following conditions:
//
// The above copyright notice and this permission notice shall be included
// in all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
// OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
// NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
// DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
// OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
// USE OR OTHER DEALINGS IN THE SOFTWARE.

'use strict';

const { getDefaultHighWaterMark } = require('internal/streams/state');
const assert = require('internal/assert');
const EE = require('events');
const Stream = require('stream');
const { streamHooks } = require('internal/streams/utils');
const { kOutHeaders, kNeedDrain } = require('internal/http');
const httpNative = require('internal/host').httpParserNative;
const { Buffer } = require('buffer');
const {
  _checkIsHttpToken: checkIsHttpToken,
  _checkInvalidHeaderChar: checkInvalidHeaderChar,
  isLenient,
} = require('_http_common');
const {
  defaultTriggerAsyncIdScope,
  symbols: { async_id_symbol },
} = require('internal/async_hooks');
const {
  codes: {
    ERR_HTTP_BODY_NOT_ALLOWED,
    ERR_HTTP_CONTENT_LENGTH_MISMATCH,
    ERR_HTTP_HEADERS_SENT,
    ERR_HTTP_INVALID_HEADER_VALUE,
    ERR_HTTP_TRAILER_INVALID,
    ERR_INVALID_ARG_TYPE,
    ERR_INVALID_ARG_VALUE,
    ERR_INVALID_CHAR,
    ERR_INVALID_HTTP_TOKEN,
    ERR_METHOD_NOT_IMPLEMENTED,
    ERR_STREAM_ALREADY_FINISHED,
    ERR_STREAM_CANNOT_PIPE,
    ERR_STREAM_DESTROYED,
    ERR_STREAM_NULL_VALUES,
    ERR_STREAM_WRITE_AFTER_END,
    ERR_UNKNOWN_ENCODING,
  },
  hideStackFrames,
} = require('internal/errors');
const { validateString } = require('internal/validators');
const { assignFunctionName } = require('internal/util');
const { isUint8Array } = require('internal/util/types');

let debug = require('internal/util/debuglog').debuglog('http', (fn) => {
  debug = fn;
});

const kCorked = Symbol('corked');
const kSocket = Symbol('kSocket');
const kChunkedBuffer = Symbol('kChunkedBuffer');
const kChunkedLength = Symbol('kChunkedLength');
const kUniqueHeaders = Symbol('kUniqueHeaders');
const kBytesWritten = Symbol('kBytesWritten');
const kErrored = Symbol('errored');
const kWritableFinished = Symbol('kWritableFinished');
const kEndCallbacks = Symbol('kEndCallbacks');
const kFlushError = Symbol('kFlushError');
const kHighWaterMark = Symbol('kHighWaterMark');
const kRejectNonStandardBodyWrites = Symbol('kRejectNonStandardBodyWrites');

const nop = () => {};

// isCookieField performs a case-insensitive comparison of a provided string
// against the word "cookie." As of V8 6.6 this is faster than handrolling or
// using a case-insensitive RegExp.
function isCookieField(s) {
  return s.length === 6 && s.toLowerCase() === 'cookie';
}

function isContentDispositionField(s) {
  return s.length === 19 && s.toLowerCase() === 'content-disposition';
}

function OutgoingMessage(options) {
  Stream.call(this);

  // Queue that holds all currently pending data, until the response will be
  // assigned to the socket (until it will its turn in the HTTP pipeline).
  this.outputData = [];

  // `outputSize` is an approximate measure of how much data is queued on this
  // response. `_onPendingData` will be invoked to update similar global
  // per-connection counter. That counter will be used to pause/unpause the
  // TCP socket and HTTP Parser and thus handle the backpressure.
  this.outputSize = 0;

  this.writable = true;
  this.destroyed = false;

  this._last = false;
  this.chunkedEncoding = false;
  this.shouldKeepAlive = true;
  this.maxRequestsOnConnectionReached = false;
  this._defaultKeepAlive = true;
  this.useChunkedEncodingByDefault = true;
  this.sendDate = false;
  this._removedConnection = false;
  this._removedContLen = false;
  this._removedTE = false;

  this.strictContentLength = false;
  this[kBytesWritten] = 0;
  this._contentLength = null;
  this._hasBody = true;
  this._trailer = '';
  this[kNeedDrain] = false;

  this.finished = false;
  this._headerSent = false;
  this[kCorked] = 0;
  this[kChunkedBuffer] = [];
  this[kChunkedLength] = 0;
  this._closed = false;

  this[kSocket] = null;
  this._header = null;
  this[kOutHeaders] = null;

  this._keepAliveTimeout = 0;

  this._onPendingData = nop;

  this[kErrored] = null;
  this[kWritableFinished] = false;
  this[kEndCallbacks] = null;
  this[kFlushError] = null;
  this[kHighWaterMark] = options?.highWaterMark ?? getDefaultHighWaterMark();
  this[kRejectNonStandardBodyWrites] = options?.rejectNonStandardBodyWrites ?? false;
}
Object.setPrototypeOf(OutgoingMessage.prototype, Stream.prototype);
Object.setPrototypeOf(OutgoingMessage, Stream);

// Check if lenient header validation should be used.
// For ClientRequest: checks this.httpValidation or this.insecureHTTPParser
// For ServerResponse: checks the server's httpValidation or insecureHTTPParser
// Falls back to global --insecure-http-parser flag.
OutgoingMessage.prototype._isLenientHeaderValidation = function() {
  // New httpValidation option takes priority (ClientRequest case)
  if (this.httpValidation !== undefined) {
    return this.httpValidation !== 'strict';
  }
  // ServerResponse: check server's httpValidation option
  const serverHttpValidation = this.req?.socket?.server?.httpValidation;
  if (serverHttpValidation !== undefined) {
    return serverHttpValidation !== 'strict';
  }
  // Legacy insecureHTTPParser - ClientRequest has it directly
  if (typeof this.insecureHTTPParser === 'boolean') {
    return this.insecureHTTPParser;
  }
  // ServerResponse can access via req.socket.server
  const serverOption = this.req?.socket?.server?.insecureHTTPParser;
  if (typeof serverOption === 'boolean') {
    return serverOption;
  }
  // Fall back to global option
  return isLenient();
};

Object.defineProperty(OutgoingMessage.prototype, 'errored', {
  __proto__: null,
  get() {
    return this[kErrored];
  },
});

Object.defineProperty(OutgoingMessage.prototype, 'closed', {
  __proto__: null,
  get() {
    return this._closed;
  },
});

Object.defineProperty(OutgoingMessage.prototype, 'writableFinished', {
  __proto__: null,
  get() {
    return this[kWritableFinished];
  },
});

Object.defineProperty(OutgoingMessage.prototype, 'writableObjectMode', {
  __proto__: null,
  get() {
    return false;
  },
});

Object.defineProperty(OutgoingMessage.prototype, 'writableLength', {
  __proto__: null,
  get() {
    let bufferedLength = this[kChunkedLength];
    if (bufferedLength !== 0) {
      bufferedLength += bufferedLength.toString(16).length + 4 +
        (!this._headerSent && this._header !== null ? this._header.length : 0);
    }
    return this.outputSize + bufferedLength + (this[kSocket] ? this[kSocket].writableLength : 0);
  },
});

Object.defineProperty(OutgoingMessage.prototype, 'writableHighWaterMark', {
  __proto__: null,
  get() {
    return this[kSocket] ? this[kSocket].writableHighWaterMark : this[kHighWaterMark];
  },
});

Object.defineProperty(OutgoingMessage.prototype, 'writableCorked', {
  __proto__: null,
  get() {
    return this[kCorked];
  },
});

Object.defineProperty(OutgoingMessage.prototype, 'connection', {
  __proto__: null,
  get: function() {
    return this[kSocket];
  },
  set: function(val) {
    this.socket = val;
  },
});

Object.defineProperty(OutgoingMessage.prototype, 'socket', {
  __proto__: null,
  get: function() {
    return this[kSocket];
  },
  set: function(val) {
    for (let n = 0; n < this[kCorked]; n++) {
      val?.cork();
      this[kSocket]?.uncork();
    }
    this[kSocket] = val;
  },
});

OutgoingMessage.prototype._renderHeaders = function _renderHeaders() {
  if (this._header) {
    throw new ERR_HTTP_HEADERS_SENT('render');
  }

  const headersMap = this[kOutHeaders];
  const headers = {};

  if (headersMap !== null) {
    const keys = Object.keys(headersMap);
    // Retain for(;;) loop for performance reasons
    // Refs: https://github.com/nodejs/node/pull/30958
    for (let i = 0, l = keys.length; i < l; i++) {
      const key = keys[i];
      headers[headersMap[key][0]] = headersMap[key][1];
    }
  }
  return headers;
};

OutgoingMessage.prototype.cork = function cork() {
  this[kCorked]++;
  if (this[kSocket]) {
    this[kSocket].cork();
  }
};

OutgoingMessage.prototype.uncork = function uncork() {
  this[kCorked]--;
  const socket = this[kSocket];
  try {
    if (this[kCorked] || this[kChunkedBuffer].length === 0) {
      return;
    }

    const len = this[kChunkedLength];
    const buf = this[kChunkedBuffer];
    if (this.destroyed || socket?.destroyed) {
      const error = this[kErrored] || socket?._writableState?.errored || new ERR_STREAM_DESTROYED('write');
      for (let n = 2; n < buf.length; n += 3) {
        if (buf[n] !== nop) {
          process.nextTick(buf[n], error);
        }
      }
      buf.length = 0;
      this[kChunkedLength] = 0;
      return;
    }
    assert(this.chunkedEncoding);

    const callbacks = [];
    this._send(len.toString(16), 'latin1', null);
    this._send(crlf_buf, null, null);
    for (let n = 0; n < buf.length; n += 3) {
      this._send(buf[n + 0], buf[n + 1], null);
      callbacks.push(buf[n + 2]);
    }
    this._send(crlf_buf, null, (err) => {
      for (const callback of callbacks) {
        callback(err);
      }
    });

    this[kChunkedBuffer].length = 0;
    this[kChunkedLength] = 0;
  } finally {
    socket?.uncork();
  }

  // If we had a pending drain and flushed all data, emit the drain event.
  if (this[kNeedDrain] && this.writableLength === 0) {
    this[kNeedDrain] = false;
    this.emit('drain');
  }
};

OutgoingMessage.prototype.setTimeout = function setTimeout(msecs, callback) {

  if (callback) {
    this.on('timeout', callback);
  }

  if (!this[kSocket]) {
    this.once('socket', function socketSetTimeoutOnConnect(socket) {
      socket.setTimeout(msecs);
    });
  } else {
    this[kSocket].setTimeout(msecs);
  }
  return this;
};


// It's possible that the socket will be destroyed, and removed from
// any messages, before ever calling this.  In that case, just skip
// it, since something else is destroying this connection anyway.
OutgoingMessage.prototype.destroy = function destroy(error) {
  if (this.destroyed) {
    return this;
  }
  this.destroyed = true;

  this[kErrored] = error;
  if (this[kChunkedBuffer].length !== 0) {
    this[kCorked] = 1;
    this.uncork();
  }

  if (this[kSocket]) {
    this[kSocket].destroy(error);
  } else {
    process.nextTick(emitDestroyNT, this);
  }

  return this;
};

function emitDestroyNT(self) {
  if (!self._closed) {
    self._closed = true;
    self.emit('close');
  }
}


// This abstract either writing directly to the socket or buffering it.
OutgoingMessage.prototype._send = function _send(data, encoding, callback, byteLength) {
  // This is a shameful hack to get the headers and first body chunk onto
  // the same packet. Future versions of Node are going to take care of
  // this at a lower level and in a more general way.
  if (!this._headerSent && this._header !== null) {
    // `this._header` can be null if OutgoingMessage is used without a proper Socket
    // See: /test/parallel/test-http-outgoing-message-inheritance.js
    if (typeof data === 'string' &&
        (encoding === 'utf8' || encoding === 'latin1' || !encoding)) {
      data = this._header + data;
    } else {
      const header = this._header;
      this.outputData.unshift({
        data: header,
        encoding: 'latin1',
        callback: null,
      });
      this.outputSize += header.length;
      this._onPendingData(header.length);
    }
    this._headerSent = true;
  }
  return this._writeRaw(data, encoding, callback, byteLength);
};

OutgoingMessage.prototype._writeRaw = _writeRaw;
function _writeRaw(data, encoding, callback, size) {
  const conn = this[kSocket];
  // A net socket's destroyed and writable come from its states in one call.
  const known = conn != null ? streamHooks.socketState(conn) : -1;
  if (known === -1 ? conn?.destroyed : known === 0) {
    // The socket was destroyed. If we're still trying to write to it,
    // then we haven't gotten the 'close' event yet.
    return false;
  }

  if (typeof encoding === 'function') {
    callback = encoding;
    encoding = null;
  }

  if (conn && conn._httpMessage === this && (known === -1 ? conn.writable : known === 1)) {
    // There might be pending data in the this.output buffer.
    if (this.outputData.length) {
      this._flushOutput(conn);
    }
    // Directly write to socket.
    return streamHooks.socketWrite(conn, data, encoding, callback) ??
      conn.write(data, encoding, callback);
  }
  // Buffer, as long as we're not destroyed.
  this.outputData.push({ data, encoding, callback });
  this.outputSize += data.length;
  this._onPendingData(data.length);
  return this.outputSize < this[kHighWaterMark];
}


function pushHeaderPair(self, pairs, key, value, validate, hasCL) {
  if (validate && (typeof key !== 'string' || !key)) {
    validateHeaderName(key);
  }

  // If key is content-disposition and there is content-length
  // encode the value in latin1
  // https://www.rfc-editor.org/rfc/rfc6266#section-4.3
  // Refs: https://github.com/nodejs/node/pull/46528
  if (hasCL && isContentDispositionField(key)) {
    if (Array.isArray(value)) {
      for (let i = 0; i < value.length; i++) {
        value[i] = Buffer.from(value[i], 'latin1');
      }
    } else {
      value = Buffer.from(value, 'latin1');
    }
  }

  if (Array.isArray(value)) {
    if (validate && value.length === 0) {
      validateHeaderName(key);
      return hasCL;
    }
    if (
      (value.length < 2 || !isCookieField(key)) &&
      (!self[kUniqueHeaders] || !self[kUniqueHeaders].has(key.toLowerCase()))
    ) {
      for (let i = 0; i < value.length; i++) {
        pairs.push(key, value[i]);
      }
      return hasCL;
    }
    value = value.join('; ');
  }
  pairs.push(key, value);
  if (key.length === 14 && key.toLowerCase() === 'content-length') {
    return Boolean(+value);
  }
  return hasCL;
}

OutgoingMessage.prototype._storeHeader = _storeHeader;
function _storeHeader(firstLine, headers) {
  // firstLine in the case of request is: 'GET /index.html HTTP/1.1\r\n'
  // in the case of response it is: 'HTTP/1.1 200 OK\r\n'
  const hasCL = typeof this._contentLength === 'number';
  if (!headers &&
      hasCL &&
      this.shouldKeepAlive &&
      !this._removedConnection &&
      !this.maxRequestsOnConnectionReached &&
      this._defaultKeepAlive &&
      this._hasBody &&
      this.useChunkedEncodingByDefault &&
      !this._removedContLen &&
      !this.chunkedEncoding) {
    this._header = httpNative(
      42,
      firstLine,
      this._contentLength,
      this._keepAliveTimeout ? Math.floor(this._keepAliveTimeout / 1000) : -1,
      ~~this._maxRequestsPerSocket,
      Boolean(this.sendDate)
    );
    this._headerSent = false;
    return;
  }

  let pairs = null;
  let pairCount = 0;
  let validate = false;
  let seenCL = Boolean(this._contentLength);

  if (headers) {
    pairs = [];
    if (headers === this[kOutHeaders]) {
      for (const key in headers) {
        const entry = headers[key];
        seenCL = pushHeaderPair(this, pairs, entry[0], entry[1], false, seenCL);
      }
    } else if (Array.isArray(headers)) {
      validate = true;
      if (headers.length && Array.isArray(headers[0])) {
        for (let i = 0; i < headers.length; i++) {
          const entry = headers[i];
          seenCL = pushHeaderPair(this, pairs, entry[0], entry[1], true, seenCL);
        }
      } else {
        if (headers.length % 2 !== 0) {
          throw new ERR_INVALID_ARG_VALUE('headers', headers);
        }

        for (let n = 0; n < headers.length; n += 2) {
          seenCL = pushHeaderPair(this, pairs, headers[n + 0], headers[n + 1], true, seenCL);
        }
      }
    } else {
      validate = true;
      for (const key in headers) {
        if (Object.hasOwn(headers, key)) {
          seenCL = pushHeaderPair(this, pairs, key, headers[key], true, seenCL);
        }
      }
    }
    pairCount = pairs.length;
  }

  const inFlags =
    (this.sendDate ? 1 : 0) |
    (this.shouldKeepAlive ? 2 : 0) |
    (this.useChunkedEncodingByDefault ? 4 : 0) |
    (this.agent ? 8 : 0) |
    (this.maxRequestsOnConnectionReached ? 16 : 0) |
    (this._defaultKeepAlive ? 32 : 0) |
    (this._removedConnection ? 64 : 0) |
    (this._removedContLen ? 128 : 0) |
    (this._removedTE ? 256 : 0) |
    (this._hasBody ? 512 : 0) |
    (hasCL ? 1024 : 0) |
    (this._isLenientHeaderValidation() ? 2048 : 0) |
    (validate ? 4096 : 0) |
    ((this.statusCode === 204 || this.statusCode === 304) ? 8192 : 0) |
    (this.chunkedEncoding ? 16384 : 0) |
    (this._last ? 32768 : 0);

  const keepAliveTimeoutSeconds = this._keepAliveTimeout ?
    Math.floor(this._keepAliveTimeout / 1000) : -1;
  const maxRequestsPerSocket = ~~this._maxRequestsPerSocket;

  const res = httpNative(
    37,
    firstLine,
    pairs,
    pairCount,
    inFlags,
    hasCL ? this._contentLength : 0,
    keepAliveTimeoutSeconds,
    maxRequestsPerSocket
  );

  const errCode = res[0];
  if (errCode !== 0) {
    if (errCode === 1) throw new ERR_INVALID_HTTP_TOKEN('Header name', res[1]);
    if (errCode === 2) throw new ERR_HTTP_INVALID_HEADER_VALUE(res[2], res[1]);
    if (errCode === 3) {
      debug('Header "%s" contains invalid characters', res[1]);
      throw new ERR_INVALID_CHAR('header content', res[1]);
    }
    throw new ERR_HTTP_TRAILER_INVALID();
  }

  const outFlags = res[2];
  this._last = (outFlags & 1) !== 0;
  this.shouldKeepAlive = (outFlags & 2) !== 0;
  this.chunkedEncoding = (outFlags & 4) !== 0;
  this._removedConnection = (outFlags & 8) !== 0;
  this._removedContLen = (outFlags & 16) !== 0;
  this._removedTE = (outFlags & 32) !== 0;
  this._defaultKeepAlive = (outFlags & 64) !== 0;
  if ((outFlags & 256) !== 0) {
    this._contentLength = +res[3];
  }

  this._header = res[1];
  this._headerSent = false;

  // Wait until the first body chunk, or close(), is sent to flush,
  // UNLESS we're sending Expect: 100-continue.
  if ((outFlags & 128) !== 0) this._send('');
}

const validateHeaderName = assignFunctionName('validateHeaderName', hideStackFrames((name, label) => {
  if (typeof name !== 'string' || !name || !checkIsHttpToken(name)) {
    throw new ERR_INVALID_HTTP_TOKEN.HideStackFramesError(label || 'Header name', name);
  }
}));

const validateHeaderValue = assignFunctionName('validateHeaderValue', hideStackFrames((name, value, lenient) => {
  if (value === undefined) {
    throw new ERR_HTTP_INVALID_HEADER_VALUE.HideStackFramesError(value, name);
  }
  if (checkInvalidHeaderChar(value, lenient)) {
    debug('Header "%s" contains invalid characters', name);
    throw new ERR_INVALID_CHAR.HideStackFramesError('header content', name);
  }
}));

function parseUniqueHeadersOption(headers) {
  if (!Array.isArray(headers)) {
    return null;
  }

  const unique = new Set();
  const l = headers.length;
  for (let i = 0; i < l; i++) {
    unique.add(headers[i].toLowerCase());
  }

  return unique;
}

OutgoingMessage.prototype.setHeader = function setHeader(name, value) {
  if (this._header) {
    throw new ERR_HTTP_HEADERS_SENT('set');
  }
  validateHeaderName(name);
  if (value === undefined) {
    throw new ERR_HTTP_INVALID_HEADER_VALUE(value, name);
  }
  if (checkInvalidHeaderChar(value, this._isLenientHeaderValidation())) {
    debug('Header "%s" contains invalid characters', name);
    throw new ERR_INVALID_CHAR('header content', name);
  }

  let headers = this[kOutHeaders];
  if (headers === null)
    this[kOutHeaders] = headers = { __proto__: null };

  headers[name.toLowerCase()] = [name, value];
  return this;
};

OutgoingMessage.prototype.setHeaders = function setHeaders(headers) {
  if (this._header) {
    throw new ERR_HTTP_HEADERS_SENT('set');
  }


  if (
    !headers ||
    Array.isArray(headers) ||
    typeof headers.keys !== 'function' ||
    typeof headers.get !== 'function'
  ) {
    throw new ERR_INVALID_ARG_TYPE('headers', ['Headers', 'Map'], headers);
  }

  // Headers object joins multiple cookies with a comma when using
  // the getter to retrieve the value,
  // unless iterating over the headers directly.
  // We also cannot safely split by comma.
  // To avoid setHeader overwriting the previous value we push
  // set-cookie values in array and set them all at once.
  let cookies = null;

  for (const { 0: key, 1: value } of headers) {
    if (key === 'set-cookie') {
      if (Array.isArray(value)) {
        cookies ??= [];
        cookies.push(...value);
      } else {
        cookies ??= [];
        cookies.push(value);
      }
      continue;
    }
    this.setHeader(key, value);
  }
  if (cookies != null) {
    this.setHeader('set-cookie', cookies);
  }

  return this;
};

OutgoingMessage.prototype.appendHeader = function appendHeader(name, value) {
  if (this._header) {
    throw new ERR_HTTP_HEADERS_SENT('append');
  }
  validateHeaderName(name);
  if (value === undefined) {
    throw new ERR_HTTP_INVALID_HEADER_VALUE(value, name);
  }
  if (checkInvalidHeaderChar(value, this._isLenientHeaderValidation())) {
    debug('Header "%s" contains invalid characters', name);
    throw new ERR_INVALID_CHAR('header content', name);
  }

  const field = name.toLowerCase();
  const headers = this[kOutHeaders];
  if (headers === null || !headers[field]) {
    return this.setHeader(name, value);
  }

  // Prepare the field for appending, if required
  if (!Array.isArray(headers[field][1])) {
    headers[field][1] = [headers[field][1]];
  }

  const existingValues = headers[field][1];
  if (Array.isArray(value)) {
    for (let i = 0, length = value.length; i < length; i++) {
      existingValues.push(value[i]);
    }
  } else {
    existingValues.push(value);
  }

  return this;
};


OutgoingMessage.prototype.getHeader = function getHeader(name) {
  validateString(name, 'name');

  const headers = this[kOutHeaders];
  if (headers === null)
    return;

  const entry = headers[name.toLowerCase()];
  return entry?.[1];
};


// Returns an array of the names of the current outgoing headers.
OutgoingMessage.prototype.getHeaderNames = function getHeaderNames() {
  return this[kOutHeaders] !== null ? Object.keys(this[kOutHeaders]) : [];
};


// Returns an array of the names of the current outgoing raw headers.
OutgoingMessage.prototype.getRawHeaderNames = function getRawHeaderNames() {
  const headersMap = this[kOutHeaders];
  if (headersMap === null) return [];

  const values = Object.values(headersMap);
  const headers = Array(values.length);
  // Retain for(;;) loop for performance reasons
  // Refs: https://github.com/nodejs/node/pull/30958
  for (let i = 0, l = values.length; i < l; i++) {
    headers[i] = values[i][0];
  }

  return headers;
};


// Returns a shallow copy of the current outgoing headers.
OutgoingMessage.prototype.getHeaders = function getHeaders() {
  const headers = this[kOutHeaders];
  const ret = { __proto__: null };
  if (headers) {
    const keys = Object.keys(headers);
    // Retain for(;;) loop for performance reasons
    // Refs: https://github.com/nodejs/node/pull/30958
    for (let i = 0; i < keys.length; ++i) {
      const key = keys[i];
      const val = headers[key][1];
      ret[key] = val;
    }
  }
  return ret;
};


OutgoingMessage.prototype.hasHeader = function hasHeader(name) {
  validateString(name, 'name');
  return this[kOutHeaders] !== null &&
    !!this[kOutHeaders][name.toLowerCase()];
};


OutgoingMessage.prototype.removeHeader = function removeHeader(name) {
  validateString(name, 'name');

  if (this._header) {
    throw new ERR_HTTP_HEADERS_SENT('remove');
  }

  const key = name.toLowerCase();

  switch (key) {
    case 'connection':
      this._removedConnection = true;
      break;
    case 'content-length':
      this._removedContLen = true;
      break;
    case 'transfer-encoding':
      this._removedTE = true;
      break;
    case 'date':
      this.sendDate = false;
      break;
  }

  if (this[kOutHeaders] !== null) {
    delete this[kOutHeaders][key];
  }
};


OutgoingMessage.prototype._implicitHeader = function _implicitHeader() {
  throw new ERR_METHOD_NOT_IMPLEMENTED('_implicitHeader()');
};

Object.defineProperty(OutgoingMessage.prototype, 'headersSent', {
  __proto__: null,
  configurable: true,
  enumerable: true,
  get: function() { return !!this._header; },
});

Object.defineProperty(OutgoingMessage.prototype, 'writableEnded', {
  __proto__: null,
  get: function() { return this.finished; },
});

Object.defineProperty(OutgoingMessage.prototype, 'writableNeedDrain', {
  __proto__: null,
  get: function() {
    return !this.destroyed && !this.finished && this[kNeedDrain];
  },
});

const crlf_buf = Buffer.from('\r\n');
OutgoingMessage.prototype.write = function write(chunk, encoding, callback) {
  if (typeof encoding === 'function') {
    callback = encoding;
    encoding = null;
  }

  const ret = write_(this, chunk, encoding, callback, false);
  if (!ret)
    this[kNeedDrain] = true;
  return ret;
};

function onError(msg, err, callback) {
  if (msg.destroyed) {
    return;
  }

  const triggerAsyncId = msg.socket ? msg.socket[async_id_symbol] : undefined;
  defaultTriggerAsyncIdScope(triggerAsyncId,
                             process.nextTick,
                             emitErrorNt,
                             msg,
                             err,
                             callback);
}

function emitErrorNt(msg, err, callback) {
  callback(err);
  if (typeof msg.emit === 'function' && !msg.destroyed) {
    msg.emit('error', err);
  }
}

function strictContentLength(msg) {
  return (
    msg.strictContentLength &&
    msg._contentLength != null &&
    msg._hasBody &&
    !msg._removedContLen &&
    !msg.chunkedEncoding &&
    !msg.hasHeader('transfer-encoding')
  );
}

function write_(msg, chunk, encoding, callback, fromEnd) {
  if (typeof callback !== 'function')
    callback = nop;

  if (chunk === null) {
    throw new ERR_STREAM_NULL_VALUES();
  } else if (typeof chunk !== 'string' && !isUint8Array(chunk)) {
    throw new ERR_INVALID_ARG_TYPE(
      'chunk', ['string', 'Buffer', 'Uint8Array'], chunk);
  }

  let err;
  if (msg.finished) {
    err = new ERR_STREAM_WRITE_AFTER_END();
  } else if (msg.destroyed) {
    err = new ERR_STREAM_DESTROYED('write');
  }

  if (err) {
    if (!msg.destroyed) {
      onError(msg, err, callback);
    } else {
      process.nextTick(callback, err);
    }
    return false;
  }

  let len;

  if (msg.strictContentLength) {
    len ??= typeof chunk === 'string' ? Buffer.byteLength(chunk, encoding) : chunk.byteLength;

    if (
      strictContentLength(msg) &&
      (fromEnd ? msg[kBytesWritten] + len !== msg._contentLength : msg[kBytesWritten] + len > msg._contentLength)
    ) {
      throw new ERR_HTTP_CONTENT_LENGTH_MISMATCH(len + msg[kBytesWritten], msg._contentLength);
    }

    msg[kBytesWritten] += len;
  }

  if (!msg._header) {
    if (fromEnd) {
      len ??= typeof chunk === 'string' ? Buffer.byteLength(chunk, encoding) : chunk.byteLength;
      msg._contentLength = len;
    }
    msg._implicitHeader();
  }

  if (!msg._hasBody) {
    if (msg[kRejectNonStandardBodyWrites]) {
      throw new ERR_HTTP_BODY_NOT_ALLOWED();
    } else {
      debug('This type of response MUST NOT have a body. ' +
        'Ignoring write() calls.');
      process.nextTick(callback);
      return true;
    }
  }

  if (msg.chunkedEncoding && typeof chunk === 'string' && encoding && !Buffer.isEncoding(encoding)) {
    throw new ERR_UNKNOWN_ENCODING(encoding);
  }

  if (!fromEnd && msg.socket && !msg.socket.writableCorked) {
    msg.cork();
    process.nextTick(connectionCorkNT, msg);
  }

  let ret;
  if (msg.chunkedEncoding && chunk.length !== 0) {
    len ??= typeof chunk === 'string' ? Buffer.byteLength(chunk, encoding) : chunk.byteLength;
    if (msg[kCorked]) {
      if (typeof chunk !== 'string' && !(chunk instanceof Buffer)) {
        chunk = Stream._uint8ArrayToBuffer(chunk);
      }
      msg[kChunkedBuffer].push(chunk, encoding, callback);
      msg[kChunkedLength] += len;
      ret = msg.writableLength < msg.writableHighWaterMark;
    } else {
      msg._send(len.toString(16), 'latin1', null);
      msg._send(crlf_buf, null, null);
      msg._send(chunk, encoding, null, len);
      ret = msg._send(crlf_buf, null, callback);
    }
  } else if (msg.chunkedEncoding && msg[kCorked] && msg[kChunkedBuffer].length !== 0) {
    msg[kChunkedBuffer].push(chunk, encoding, callback);
    ret = msg.writableLength < msg.writableHighWaterMark;
  } else {
    ret = msg._send(chunk, encoding, callback, len);
  }

  debug('write ret = ' + ret);
  return ret;
}


// If this last write can be delivered immediately as the final chunk, this
// prepares to do so, and then returns true. If not, it returns false and
// a separate _send call and tick will be required to finish up.
function maybePrepareFinalChunk(msg, chunk, encoding) {
  if (typeof chunk !== 'string' && !isUint8Array(chunk))
    return false;

  if (msg.destroyed || msg.strictContentLength)
    return false;

  if (!msg._header) {
    msg._contentLength = typeof chunk === 'string' ?
      Buffer.byteLength(chunk, encoding) : chunk.byteLength;
    msg._implicitHeader();
  }

  return !!msg._header && msg._hasBody && !msg.chunkedEncoding;
}

function connectionCorkNT(msg) {
  if (msg[kCorked]) {
    msg.uncork();
  }
}

OutgoingMessage.prototype.addTrailers = function addTrailers(headers) {
  this._trailer = '';
  const keys = Object.keys(headers);
  const isArray = Array.isArray(headers);
  const pairs = [];
  for (let i = 0, l = keys.length; i < l; i++) {
    let field, value;
    const key = keys[i];
    if (isArray) {
      field = headers[key][0];
      value = headers[key][1];
    } else {
      field = key;
      value = headers[key];
    }
    if (typeof field !== 'string' || !field) {
      validateHeaderName(field, 'Trailer name');
    }
    const isArrayValue = Array.isArray(value);
    if (
      isArrayValue && value.length > 1 &&
      (!this[kUniqueHeaders] || !this[kUniqueHeaders].has(field.toLowerCase()))
    ) {
      for (let j = 0, vl = value.length; j < vl; j++) {
        pairs.push(field, value[j]);
      }
    } else {
      if (isArrayValue) {
        value = value.join('; ');
      }
      pairs.push(field, value);
    }
  }
  if (pairs.length === 0) return;
  const res = httpNative(38, pairs, pairs.length, Boolean(this._isLenientHeaderValidation()));
  if (res[0] !== 0) {
    if (res[0] === 1) throw new ERR_INVALID_HTTP_TOKEN('Trailer name', res[1]);
    debug('Trailer "%s" contains invalid characters', res[1]);
    throw new ERR_INVALID_CHAR('trailer content', res[1]);
  }
  this._trailer = res[1];
};

// Deliver end() callbacks, mirroring Writable: null on successful finish,
// otherwise the error that prevented all data from being flushed.
function flushEndCallbacks(msg, err) {
  const callbacks = msg[kEndCallbacks];
  if (callbacks === null)
    return;
  msg[kEndCallbacks] = null;
  for (let i = 0; i < callbacks.length; i++)
    callbacks[i](err);
}

function getEndCallbackError(msg) {
  return msg[kErrored] ??
    msg[kSocket]?.errored ??
    new ERR_STREAM_DESTROYED('end');
}

function queueEndCallback(msg, callback) {
  if (msg[kWritableFinished]) {
    callback(new ERR_STREAM_ALREADY_FINISHED('end'));
    return;
  }
  if (msg[kFlushError] !== null) {
    process.nextTick(callback, msg[kFlushError]);
    return;
  }
  msg[kEndCallbacks] ??= [];
  msg[kEndCallbacks].push(callback);
}

function onFinish(outmsg, err) {
  if (err ||
      outmsg[kErrored] ||
      outmsg[kSocket]?.errored ||
      outmsg[kSocket]?._hadError) {
    outmsg[kFlushError] = err ?? getEndCallbackError(outmsg);
    flushEndCallbacks(outmsg, outmsg[kFlushError]);
    return;
  }

  outmsg[kWritableFinished] = true;
  flushEndCallbacks(outmsg, null);
  outmsg.emit('finish');
}

OutgoingMessage.prototype.end = function end(chunk, encoding, callback) {
  if (typeof chunk === 'function') {
    callback = chunk;
    chunk = null;
    encoding = null;
  } else if (typeof encoding === 'function') {
    callback = encoding;
    encoding = null;
  }

  let finishCallback = null;

  if (chunk) {
    if (this.finished) {
      onError(this,
              new ERR_STREAM_WRITE_AFTER_END(),
              typeof callback !== 'function' ? nop : callback);
      return this;
    }

    // A string body that goes out with the implicit header is one socket write (_send
    // joins them), which corking cannot merge with anything: the socket is corked only
    // when more than one write may follow.
    const single = typeof chunk === 'string' && !this._header &&
      this.outputData.length === 0 && this[kChunkedBuffer].length === 0 &&
      (encoding === 'utf8' || encoding === 'latin1' || !encoding);
    if (this[kSocket] && !single) {
      this[kSocket].cork();
    }

    if (maybePrepareFinalChunk(this, chunk, encoding)) {
      // If just one final write is required, with nothing to follow, we
      // attach finish to the write to avoid a separate send() & tick step
      // later on - this is purely a performance optimization.
      if (typeof callback === 'function') {
        queueEndCallback(this, callback);
        callback = undefined;
      }
      finishCallback = onFinish.bind(undefined, this);
    } else if (single) {
      this[kSocket]?.cork();
    }

    write_(this, chunk, encoding, finishCallback, true);
  } else if (this.finished) {
    if (typeof callback === 'function') {
      queueEndCallback(this, callback);
    }
    return this;
  } else if (!this._header) {
    if (this[kSocket]) {
      this[kSocket].cork();
    }

    this._contentLength = 0;
    this._implicitHeader();
  }

  if (typeof callback === 'function')
    queueEndCallback(this, callback);

  if (strictContentLength(this) && this[kBytesWritten] !== this._contentLength) {
    throw new ERR_HTTP_CONTENT_LENGTH_MISMATCH(this[kBytesWritten], this._contentLength);
  }

  // Flush buffered chunks before terminating the response.
  if (this[kChunkedBuffer].length !== 0) {
    this[kSocket]?.cork();
    this[kCorked] = 1;
    this.uncork();
  }

  if (finishCallback === null) {
    // If we didn't early finish, send the last data and schedule 'finish' now:
    finishCallback = onFinish.bind(undefined, this);

    if (this._hasBody && this.chunkedEncoding) {
      this._send('0\r\n' + this._trailer + '\r\n', 'latin1', finishCallback);
    } else if (!this._headerSent || this.writableLength || chunk) {
      this._send('', 'latin1', finishCallback);
    } else {
      process.nextTick(finishCallback);
    }
  }

  if (this[kSocket]) {
    // Fully uncork connection on end().
    this[kSocket]._writableState.corked = 1;
    this[kSocket].uncork();
  }
  this[kCorked] = 1;
  this.uncork();

  this.finished = true;

  // There is the first message on the outgoing queue, and we've sent
  // everything to the socket.
  debug('outgoing message end.');
  if (this.outputData.length === 0 &&
      this[kSocket] &&
      this[kSocket]._httpMessage === this) {
    this._finish();
  }

  return this;
};


// This function is called once all user data are flushed to the socket.
// Note that it has a chance that the socket is not drained.
OutgoingMessage.prototype._finish = function _finish() {
  assert(this[kSocket]);
  this.emit('prefinish');
};


// This logic is probably a bit confusing. Let me explain a bit:
//
// In both HTTP servers and clients it is possible to queue up several
// outgoing messages. This is easiest to imagine in the case of a client.
// Take the following situation:
//
//    req1 = client.request('GET', '/');
//    req2 = client.request('POST', '/');
//
// When the user does
//
//   req2.write('hello world\n');
//
// it's possible that the first request has not been completely flushed to
// the socket yet. Thus the outgoing messages need to be prepared to queue
// up data internally before sending it on further to the socket's queue.
//
// This function, _flush(), is called by both the Server and Client
// to attempt to flush any pending messages out to the socket.
OutgoingMessage.prototype._flush = function _flush() {
  const socket = this[kSocket];

  if (socket?.writable) {
    // There might be remaining data in this.output; write it out
    const ret = this._flushOutput(socket);

    if (this.finished) {
      // This is a queue to the server or client to bring in the next this.
      this._finish();
    } else if (this[kNeedDrain] && ret !== false) {
      // Socket accepted all data without backpressure - it won't emit
      // drain, so we emit it since the OM buffer is now clear.
      this[kNeedDrain] = false;
      this.emit('drain');
    }
  }
};

OutgoingMessage.prototype._flushOutput = function _flushOutput(socket) {
  const outputLength = this.outputData.length;
  if (outputLength <= 0)
    return undefined;

  const outputData = this.outputData;
  socket.cork();
  let ret;
  // Retain for(;;) loop for performance reasons
  // Refs: https://github.com/nodejs/node/pull/30958
  for (let i = 0; i < outputLength; i++) {
    const { data, encoding, callback } = outputData[i];
    // Avoid any potential ref to Buffer in new generation from old generation
    outputData[i].data = null;
    ret = socket.write(data, encoding, callback);
  }
  socket.uncork();

  this.outputData = [];
  this._onPendingData(-this.outputSize);
  this.outputSize = 0;

  return ret;
};


OutgoingMessage.prototype.flushHeaders = function flushHeaders() {
  if (!this._header) {
    this._implicitHeader();
  }

  // Force-flush the headers.
  this._send('');
};

OutgoingMessage.prototype.pipe = function pipe() {
  // OutgoingMessage should be write-only. Piping from it is disabled.
  this.emit('error', new ERR_STREAM_CANNOT_PIPE());
};

OutgoingMessage.prototype[EE.captureRejectionSymbol] =
function(err, event) {
  this.destroy(err);
};

module.exports = {
  kHighWaterMark,
  kUniqueHeaders,
  parseUniqueHeadersOption,
  validateHeaderName,
  validateHeaderValue,
  OutgoingMessage,
};
