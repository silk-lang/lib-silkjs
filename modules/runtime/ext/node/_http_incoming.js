// Copyright Joyent, Inc. and other Node contributors.
// Adapted from Node.js v24.22.1 lib/_http_incoming.js (primordials replaced by plain calls).
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

const { Readable, finished } = require('stream');
const { Stream } = require('internal/streams/legacy');


const kHeaders = Symbol('kHeaders');
const kHeadersDistinct = Symbol('kHeadersDistinct');
const kHeadersCount = Symbol('kHeadersCount');
const kTrailers = Symbol('kTrailers');
const kTrailersDistinct = Symbol('kTrailersDistinct');
const kTrailersCount = Symbol('kTrailersCount');
const kAbortController = Symbol('kAbortController');
const kAbortSignalSocket = Symbol('kAbortSignalSocket');
const kAbortSignalListener = Symbol('kAbortSignalListener');
const kAbortSignalDetached = Symbol('kAbortSignalDetached');
const kAttachAbortSignal = Symbol('kAttachAbortSignal');
const kDetachAbortSignal = Symbol('kDetachAbortSignal');

function readStart(socket) {
  if (socket && !socket._paused && socket.readable)
    socket.resume();
}

function readStop(socket) {
  if (socket)
    socket.pause();
}

// Lean requests (node:http requests net_native read, see internal/http/native-parser): a
// request with no body whose stream nobody observes needs no Readable state. Its state is
// made, and what the stream went through replayed, on the first read of _readableState,
// which every Readable method and accessor (and every listener added with on) does first.
// Until then `kLean` holds { highWaterMark, ended, dumped }.
const kLean = Symbol('kLean');
let leanNext = false;
function makeLeanNext(value) { leanNext = value; }

/* Abstract base class for ServerRequest and ClientResponse. */
function IncomingMessage(socket) {
  let streamOptions;

  if (socket) {
    streamOptions = {
      highWaterMark: socket.readableHighWaterMark,
    };
  }

  if (leanNext && new.target === IncomingMessage) {
    leanNext = false;
    // Readable's constructor, but its state.
    this._events = { close: undefined, error: undefined, data: undefined, end: undefined, readable: undefined };
    Stream.call(this, streamOptions);
    this[kLean] = { options: streamOptions, ended: false, dumped: false };
  } else {
    leanNext = false;
    Readable.call(this, streamOptions);
    this._readableState.readingMore = true;
  }

  this.socket = socket;

  this.httpVersionMajor = null;
  this.httpVersionMinor = null;
  this.httpVersion = null;
  this.complete = false;
  this[kHeaders] = null;
  this[kHeadersCount] = 0;
  this.rawHeaders = [];
  this[kTrailers] = null;
  this[kTrailersCount] = 0;
  this.rawTrailers = [];
  this.joinDuplicateHeaders = false;
  this.aborted = false;

  this.upgrade = null;

  // request (server) only
  this.url = '';
  this.method = null;

  // response (client) only
  this.statusCode = null;
  this.statusMessage = null;
  this.client = socket;

  this._consuming = false;
  // Flag for when we decide that this message cannot possibly be
  // read by the user, so there's no point continuing to handle it.
  this._dumped = false;
  this[kAbortController] = null;
  this[kAbortSignalSocket] = null;
  this[kAbortSignalListener] = null;
  this[kAbortSignalDetached] = false;
}
Object.setPrototypeOf(IncomingMessage.prototype, Readable.prototype);
Object.setPrototypeOf(IncomingMessage, Readable);

// A lean request's stream state, made when first read (see kLean).
function leanState(message) {
  const lean = message[kLean];
  message[kLean] = undefined;
  const state = new Readable.ReadableState(lean.options, message, false);
  Object.defineProperty(message, '_readableState', { __proto__: null, value: state, writable: true, enumerable: true, configurable: true });
  state.readingMore = true;
  if (lean.ended) Readable.prototype.push.call(message, null);
  if (lean.dumped) {
    // What _dump did on the complete, unread message.
    message.read(0);
  }
  return state;
}
Object.defineProperty(IncomingMessage.prototype, '_readableState', {
  __proto__: null,
  get() { return this[kLean] ? leanState(this) : undefined; },
  set(value) { Object.defineProperty(this, '_readableState', { __proto__: null, value, writable: true, enumerable: true, configurable: true }); },
  configurable: true,
});
// parserOnMessageComplete's push(null) on a request.
function pushEnd(message) {
  const lean = message[kLean];
  if (lean) lean.ended = true;
  else message.push(null);
}
// resOnFinish's test of a resume in flight, and whether the message ended.
function resumeScheduled(message) { return message[kLean] ? false : message._readableState.resumeScheduled; }
function readableEnded(message) { return message[kLean] ? false : message.readableEnded; }
function isLean(message) { return message[kLean] !== undefined; }

Object.defineProperty(IncomingMessage.prototype, 'connection', {
  __proto__: null,
  get: function() {
    return this.socket;
  },
  set: function(val) {
    this.socket = val;
  },
});

const httpNative = require('internal/host').httpParserNative;

Object.defineProperty(IncomingMessage.prototype, 'headers', {
  __proto__: null,
  get: function() {
    if (!this[kHeaders]) {
      if (this._addHeaderLine === _addHeaderLine) {
        this[kHeaders] = httpNative(35, this.rawHeaders, this[kHeadersCount], Boolean(this.joinDuplicateHeaders));
      } else {
        this[kHeaders] = {};
        const src = this.rawHeaders;
        const dst = this[kHeaders];
        for (let n = 0; n < this[kHeadersCount]; n += 2) {
          this._addHeaderLine(src[n + 0], src[n + 1], dst);
        }
      }
    }
    return this[kHeaders];
  },
  set: function(val) {
    this[kHeaders] = val;
  },
});

Object.defineProperty(IncomingMessage.prototype, 'headersDistinct', {
  __proto__: null,
  get: function() {
    if (!this[kHeadersDistinct]) {
      if (this._addHeaderLineDistinct === _addHeaderLineDistinct) {
        this[kHeadersDistinct] = httpNative(36, this.rawHeaders, this[kHeadersCount]);
      } else {
        this[kHeadersDistinct] = { __proto__: null };
        const src = this.rawHeaders;
        const dst = this[kHeadersDistinct];
        for (let n = 0; n < this[kHeadersCount]; n += 2) {
          this._addHeaderLineDistinct(src[n + 0], src[n + 1], dst);
        }
      }
    }
    return this[kHeadersDistinct];
  },
  set: function(val) {
    this[kHeadersDistinct] = val;
  },
});

Object.defineProperty(IncomingMessage.prototype, 'trailers', {
  __proto__: null,
  get: function() {
    if (!this[kTrailers]) {
      if (this._addHeaderLine === _addHeaderLine) {
        this[kTrailers] = httpNative(35, this.rawTrailers, this[kTrailersCount], Boolean(this.joinDuplicateHeaders));
      } else {
        this[kTrailers] = {};
        const src = this.rawTrailers;
        const dst = this[kTrailers];
        for (let n = 0; n < this[kTrailersCount]; n += 2) {
          this._addHeaderLine(src[n + 0], src[n + 1], dst);
        }
      }
    }
    return this[kTrailers];
  },
  set: function(val) {
    this[kTrailers] = val;
  },
});

Object.defineProperty(IncomingMessage.prototype, 'trailersDistinct', {
  __proto__: null,
  get: function() {
    if (!this[kTrailersDistinct]) {
      if (this._addHeaderLineDistinct === _addHeaderLineDistinct) {
        this[kTrailersDistinct] = httpNative(36, this.rawTrailers, this[kTrailersCount]);
      } else {
        this[kTrailersDistinct] = { __proto__: null };
        const src = this.rawTrailers;
        const dst = this[kTrailersDistinct];
        for (let n = 0; n < this[kTrailersCount]; n += 2) {
          this._addHeaderLineDistinct(src[n + 0], src[n + 1], dst);
        }
      }
    }
    return this[kTrailersDistinct];
  },
  set: function(val) {
    this[kTrailersDistinct] = val;
  },
});

Object.defineProperty(IncomingMessage.prototype, 'signal', {
  __proto__: null,
  configurable: true,
  get: function() {
    if (this[kAbortController] === null) {
      const ac = new AbortController();
      this[kAbortController] = ac;
      if (this.destroyed && (!this.readableEnded || !this.complete)) {
        ac.abort();
      } else {
        this[kAttachAbortSignal]();
      }
    }
    return this[kAbortController].signal;
  },
});

IncomingMessage.prototype[kAttachAbortSignal] = function() {
  if (this[kAbortController].signal.aborted ||
      this[kAbortSignalDetached] ||
      this[kAbortSignalListener] !== null) {
    return;
  }

  const socket = this.socket;
  if (!socket) {
    return;
  }

  if (socket.destroyed) {
    abortSignal(this);
    return;
  }

  this[kAbortSignalSocket] = socket;
  this[kAbortSignalListener] = () => {
    abortSignal(this);
  };
  socket.once('close', this[kAbortSignalListener]);
};

IncomingMessage.prototype[kDetachAbortSignal] = function() {
  const socket = this[kAbortSignalSocket];
  const listener = this[kAbortSignalListener];
  this[kAbortSignalDetached] = true;
  this[kAbortSignalSocket] = null;
  this[kAbortSignalListener] = null;
  if (socket !== null && listener !== null) {
    socket.removeListener('close', listener);
  }
};

IncomingMessage.prototype.setTimeout = function setTimeout(msecs, callback) {
  if (callback)
    this.on('timeout', callback);
  this.socket.setTimeout(msecs);
  return this;
};

IncomingMessage.prototype._read = function _read() {
  if (!this._consuming) {
    this._readableState.readingMore = false;
    this._consuming = true;
  }

  // We actually do almost nothing here, because the parserOnBody
  // function fills up our internal buffer directly.  However, we
  // do need to unpause the underlying socket so that it flows.
  if (this.socket.readable)
    readStart(this.socket);
};

// It's possible that the socket will be destroyed, and removed from
// any messages, before ever calling this.  In that case, just skip
// it, since something else is destroying this connection anyway.
IncomingMessage.prototype._destroy = function _destroy(err, cb) {
  if (!this.readableEnded || !this.complete) {
    this.aborted = true;
    this.emit('aborted');
    abortSignal(this);
  }

  // If aborted and the underlying socket is not already destroyed,
  // destroy it.
  // We have to check if the socket is already destroyed because finished
  // does not call the callback when this method is invoked from `_http_client`
  // in `test/parallel/test-http-client-spurious-aborted.js`
  if (this.socket && !this.socket.destroyed && this.aborted) {
    this.socket.destroy(err);
    const cleanup = finished(this.socket, (e) => {
      if (e?.code === 'ERR_STREAM_PREMATURE_CLOSE') {
        e = null;
      }
      cleanup();
      process.nextTick(onError, this, e || err, cb);
    });
  } else if (err == null && !this.aborted) {
    // The message was received completely and is being destroyed cleanly:
    // complete the destroy synchronously. 'close' is still emitted on a
    // later tick by the stream machinery. The deferral below only exists
    // so that 'error' listeners attached right after destroy(err) still
    // receive the error, which cannot matter when there is no error.
    cb();
  } else {
    process.nextTick(onError, this, err, cb);
  }
};

function abortSignal(self) {
  self[kDetachAbortSignal]();
  if (self[kAbortController] !== null) {
    self[kAbortController].abort();
  }
}

IncomingMessage.prototype._addHeaderLines = _addHeaderLines;
function _addHeaderLines(headers, n) {
  if (headers?.length) {
    let dest;
    if (this.complete) {
      this.rawTrailers = headers;
      this[kTrailersCount] = n;
      dest = this[kTrailers];
    } else {
      this.rawHeaders = headers;
      this[kHeadersCount] = n;
      dest = this[kHeaders];
    }

    if (dest) {
      for (let i = 0; i < n; i += 2) {
        this._addHeaderLine(headers[i], headers[i + 1], dest);
      }
    }
  }
}


const SINGLE_VALUE_HEADERS = new Set([
  'age', 'host', 'from', 'etag', 'server', 'referer', 'expires', 'location',
  'user-agent', 'retry-after', 'content-type', 'max-forwards', 'authorization',
  'last-modified', 'content-length', 'if-modified-since',
  'proxy-authorization', 'if-unmodified-since',
]);

// Add the given (field, value) pair to the message (fallback for direct calls
// or subclasses overriding _addHeaderLine; standard headers/trailers getters
// materialize directly in Silk).
IncomingMessage.prototype._addHeaderLine = _addHeaderLine;
function _addHeaderLine(field, value, dest) {
  field = field.toLowerCase();
  if (field === 'set-cookie') {
    if (dest['set-cookie'] !== undefined) {
      dest['set-cookie'].push(value);
    } else {
      dest['set-cookie'] = [value];
    }
  } else if (field === 'cookie') {
    if (typeof dest[field] === 'string') {
      dest[field] += '; ' + value;
    } else {
      dest[field] = value;
    }
  } else if (SINGLE_VALUE_HEADERS.has(field)) {
    if (this.joinDuplicateHeaders) {
      if (dest[field] === undefined) {
        dest[field] = value;
      } else {
        dest[field] += ', ' + value;
      }
    } else if (dest[field] === undefined) {
      dest[field] = value;
    }
  } else if (typeof dest[field] === 'string') {
    dest[field] += ', ' + value;
  } else {
    dest[field] = value;
  }
}

IncomingMessage.prototype._addHeaderLineDistinct = _addHeaderLineDistinct;
function _addHeaderLineDistinct(field, value, dest) {
  field = field.toLowerCase();
  if (!dest[field]) {
    dest[field] = [value];
  } else {
    dest[field].push(value);
  }
}

IncomingMessage.prototype._dumpAndCloseReadable = function _dumpAndCloseReadable() {
  this._dumped = true;
  this._readableState.ended = true;
  this._readableState.endEmitted = true;
  this._readableState.destroyed = true;
  this._readableState.closed = true;
  this._readableState.closeEmitted = true;
};


// Call this instead of resume() if we want to just
// dump all the data to /dev/null
IncomingMessage.prototype._dump = function _dump() {
  // A lean message that ended and that nothing listens to: Node's read(0) would only emit
  // 'end' and 'close' to no one. It stays lean, and replays the read if anything looks.
  const lean = this[kLean];
  if (lean && !this._dumped && lean.ended && this.complete && this._eventsCount === 0) {
    this._dumped = true;
    lean.dumped = true;
    return;
  }
  if (!this._dumped) {
    this._dumped = true;
    // If there is buffered data, it may trigger 'data' events.
    // Remove 'data' event listeners explicitly.
    this.removeAllListeners('data');
    if (this.complete && !this.destroyed && this.readableLength === 0) {
      // The message was fully received and never read: there is nothing to
      // pull off the wire. Go straight to the 'end' emission instead of
      // paying for the resume() and flow() scheduling machinery.
      this.read(0);
    } else {
      this.resume();
    }
  }
};

function onError(self, error, cb) {
  // This is to keep backward compatible behavior.
  // An error is emitted only if there are listeners attached to the event.
  if (self.listenerCount('error') === 0) {
    cb();
  } else {
    cb(error);
  }
}

module.exports = {
  IncomingMessage,
  makeLeanNext,
  pushEnd,
  resumeScheduled,
  readableEnded,
  isLean,
  kDetachAbortSignal,
  readStart,
  readStop,
};
