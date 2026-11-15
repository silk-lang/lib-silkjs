/* The reference side of the Brotli differential tests: the same driver as ../tool/src/main.silk,
   on the C library (google/brotli v1.2.0 with upstream 0ed4268's decoder, as Node 24 bundles it).
   build.sh compiles it from a checkout of the pinned sources. It is a test oracle only; nothing
   here is linked into the runtime.

   Input on stdin, output on stdout, one trace line for each library call on stderr.
   Environment: BR_MODE (0 compress, 1 decompress), BR_PARAMS ("id=value,id=value"),
   BR_IN (input bytes given to one call), BR_OUT (output capacity of one call),
   BR_FLUSH (compress: every n-th input chunk ends with BROTLI_OPERATION_FLUSH; 0 never),
   BR_META (compress: every n-th input chunk is sent as EMIT_METADATA, at most 16 bytes; 0 never),
   BR_DICT (path of a raw dictionary to attach), BR_TRACE (0 turns the trace off). */
#include <brotli/decode.h>
#include <brotli/encode.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static long env(const char* name, long fallback) {
  const char* v = getenv(name);
  return v && *v ? atol(v) : fallback;
}
static uint8_t* slurp(FILE* f, size_t* size) {
  size_t cap = 1 << 20, used = 0; uint8_t* data = malloc(cap);
  for (;;) {
    if (cap - used < 65536) { cap *= 2; data = realloc(data, cap); }
    size_t n = fread(data + used, 1, cap - used, f);
    if (n == 0) break;
    used += n;
  }
  *size = used; return data;
}
static void put(const uint8_t* p, size_t n) {
  while (n) { ssize_t w = write(1, p, n); if (w <= 0) exit(90); p += w; n -= (size_t)w; }
}

int main(void) {
  size_t length, dict_length = 0; uint8_t* input = slurp(stdin, &length); uint8_t* dict = NULL;
  long mode = env("BR_MODE", 0), in_chunk = env("BR_IN", 1 << 30), out_cap = env("BR_OUT", 65536);
  long flush_every = env("BR_FLUSH", 0), meta_every = env("BR_META", 0), trace = env("BR_TRACE", 1);
  const char* params = getenv("BR_PARAMS"); const char* dict_path = getenv("BR_DICT");
  uint8_t* out = malloc((size_t)out_cap + 1);
  if (dict_path && *dict_path) { FILE* f = fopen(dict_path, "rb"); if (!f) return 91; dict = slurp(f, &dict_length); fclose(f); }
  if (mode == 0) {
    BrotliEncoderState* s = BrotliEncoderCreateInstance(NULL, NULL, NULL);
    BrotliEncoderPreparedDictionary* prepared = NULL;
    for (const char* p = params; p && *p;) {
      char* end; long k = strtol(p, &end, 10); long v = strtol(end + 1, &end, 10);
      int ok = BrotliEncoderSetParameter(s, (BrotliEncoderParameter)k, (uint32_t)v);
      if (trace) fprintf(stderr, "P %ld %ld %d\n", k, v, ok);
      p = *end ? end + 1 : end;
    }
    if (dict) {
      prepared = BrotliEncoderPrepareDictionary(BROTLI_SHARED_DICTIONARY_RAW, dict_length, dict, BROTLI_MAX_QUALITY, NULL, NULL, NULL);
      int ok = prepared ? BrotliEncoderAttachPreparedDictionary(s, prepared) : 0;
      if (trace) fprintf(stderr, "D %d\n", ok);
    }
    size_t pos = 0; long index = 0;
    for (;;) {
      size_t take = length - pos; int op = BROTLI_OPERATION_FINISH;
      if (take > (size_t)in_chunk) {
        take = (size_t)in_chunk; op = BROTLI_OPERATION_PROCESS;
        if (flush_every && index % flush_every == flush_every - 1) op = BROTLI_OPERATION_FLUSH;
        if (meta_every && index % meta_every == meta_every - 1) { op = BROTLI_OPERATION_EMIT_METADATA; if (take > 16) take = 16; }
      }
      size_t avail_in = take; const uint8_t* next_in = input + pos;
      for (;;) {
        size_t avail_out = (size_t)out_cap; uint8_t* next_out = out;
        size_t before = avail_in;
        int ok = BrotliEncoderCompressStream(s, (BrotliEncoderOperation)op, &avail_in, &next_in, &avail_out, &next_out, NULL);
        size_t written = (size_t)out_cap - avail_out;
        int more = BrotliEncoderHasMoreOutput(s), finished = BrotliEncoderIsFinished(s);
        if (trace) fprintf(stderr, "E %d %d %zu %zu %d %d\n", op, ok, before - avail_in, written, more, finished);
        put(out, written);
        if (!ok) return 3;
        if (avail_in == 0 && !more && (op != BROTLI_OPERATION_FINISH || finished)) break;
        if (written == 0 && before == avail_in && out_cap == 0) return 92;
      }
      pos += take; index++;
      if (op == BROTLI_OPERATION_FINISH) break;
    }
    BrotliEncoderDestroyInstance(s);
    if (prepared) BrotliEncoderDestroyPreparedDictionary(prepared);
    return 0;
  }
  BrotliDecoderState* s = BrotliDecoderCreateInstance(NULL, NULL, NULL);
  for (const char* p = params; p && *p;) {
    char* end; long k = strtol(p, &end, 10); long v = strtol(end + 1, &end, 10);
    int ok = BrotliDecoderSetParameter(s, (BrotliDecoderParameter)k, (uint32_t)v);
    if (trace) fprintf(stderr, "P %ld %ld %d\n", k, v, ok);
    p = *end ? end + 1 : end;
  }
  if (dict) {
    int ok = BrotliDecoderAttachDictionary(s, BROTLI_SHARED_DICTIONARY_RAW, dict_length, dict);
    if (trace) fprintf(stderr, "D %d\n", ok);
  }
  size_t pos = 0;
  for (;;) {
    size_t take = length - pos; if (take > (size_t)in_chunk) take = (size_t)in_chunk;
    size_t avail_in = take; const uint8_t* next_in = input + pos;
    for (;;) {
      size_t avail_out = (size_t)out_cap; uint8_t* next_out = out; size_t before = avail_in;
      BrotliDecoderResult r = BrotliDecoderDecompressStream(s, &avail_in, &next_in, &avail_out, &next_out, NULL);
      size_t written = (size_t)out_cap - avail_out;
      if (trace) fprintf(stderr, "X %d %zu %zu %d %d\n", (int)r, before - avail_in, written, BrotliDecoderHasMoreOutput(s), r == BROTLI_DECODER_RESULT_ERROR ? (int)BrotliDecoderGetErrorCode(s) : 0);
      put(out, written);
      if (r == BROTLI_DECODER_RESULT_ERROR) return 1;
      if (r == BROTLI_DECODER_RESULT_SUCCESS) { if (trace) fprintf(stderr, "T %zu\n", avail_in + (length - pos - take)); return 0; }
      if (r == BROTLI_DECODER_RESULT_NEEDS_MORE_INPUT) break;
    }
    pos += take;
    if (pos == length) { if (trace) fprintf(stderr, "U\n"); return 2; }
  }
}
