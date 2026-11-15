#!/usr/bin/env python3
"""Generates src/enc/dictionary_tests.silk: fixed vectors of prepared (raw) dictionaries from the
C library.

  tools/gen_dictionary_tests.py REF BROTLI_CHECKOUT > src/enc/dictionary_tests.silk

REF is the C reference driver (tests/reference/build.sh's output); it gives the output of the
encoder with a dictionary attached (BR_DICT), at every quality. BROTLI_CHECKOUT is the pinned
google/brotli checkout: its encoder is compiled into a temporary shared library, and
`BrotliEncoderPrepareDictionary` there gives the hash tables of `CreatePreparedDictionary`, read
from the returned structure (the layout of `compound_dictionary.h`).
"""
import ctypes, glob, hashlib, os, struct, subprocess, sys, tempfile


def lcg_bytes(count, seed, alphabet):
    # The generator `dictionaryBytes` of the tests repeats: letters from 'a'.
    state = seed
    out = bytearray()
    for _ in range(count):
        state = (state * 1103515245 + 12345) & 0x7fffffff
        out.append(97 + (state >> 16) % alphabet)
    return bytes(out)


def dictionary_bytes(size):
    # A part over 4 letters (buckets past their limit of 32), a run of zeros (one key), and the
    # rest over 16 letters.
    a = lcg_bytes(min(size, 30000), 7, 4)
    b = bytes(min(max(size - len(a), 0), 2000))
    c = lcg_bytes(max(size - len(a) - len(b), 0), 11, 16)
    return a + b + c


def text_input():
    words = ['the', 'of', 'and', 'compression', 'window', 'brotli', 'dictionary', 'stream', 'über',
             '{"name":', '"value"', '</div>', '<p class="x">', '\n', ', ', '. ']
    state = 4242
    out = []
    size = 0
    while size < 3000:
        state = (state * 1103515245 + 12345) & 0x7fffffff
        piece = (words[(state >> 8) % len(words)] + ' ').encode('utf-8')
        out.append(piece)
        size += len(piece)
    return b''.join(out)[:3000]


def library(checkout, folder):
    out = os.path.join(folder, 'libbrotlienc.so')
    sources = glob.glob(os.path.join(checkout, 'c/common/*.c')) + glob.glob(os.path.join(checkout, 'c/enc/*.c'))
    subprocess.run(['cc', '-O2', '-w', '-shared', '-fPIC', '-I', os.path.join(checkout, 'c/include')] + sources + ['-lm', '-o', out], check=True)
    lib = ctypes.CDLL(out)
    lib.BrotliEncoderPrepareDictionary.restype = ctypes.c_void_p
    lib.BrotliEncoderPrepareDictionary.argtypes = [ctypes.c_int, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    lib.BrotliEncoderDestroyPreparedDictionary.argtypes = [ctypes.c_void_p]
    return lib


def tables(lib, data):
    managed = lib.BrotliEncoderPrepareDictionary(0, len(data), data, 11, None, None, None)
    # The prepared dictionary is the last field of `ManagedDictionary`, after its memory manager:
    # the first pointer after the magic that points to a lean prepared dictionary.
    pointer = None
    for offset in range(8, 1 << 20, 8):
        candidate = ctypes.c_void_p.from_address(managed + offset).value
        if candidate and candidate > 4096 and ctypes.c_uint32.from_address(candidate).value == 0xDEBCEDE3:
            pointer = candidate
            break
    magic, num_items, source_size, hash_bits, bucket_bits, slot_bits = struct.unpack('<6I', ctypes.string_at(pointer, 24))
    assert magic == 0xDEBCEDE3 and source_size == len(data)
    at = pointer + 24
    slot_offsets = ctypes.string_at(at, 4 << slot_bits); at += 4 << slot_bits
    heads = ctypes.string_at(at, 2 << bucket_bits); at += 2 << bucket_bits
    items = ctypes.string_at(at, 4 * num_items)
    lib.BrotliEncoderDestroyPreparedDictionary(managed)
    return dict(num_items=num_items, hash_bits=hash_bits, bucket_bits=bucket_bits, slot_bits=slot_bits,
                slot_offsets=hashlib.sha256(slot_offsets).digest(), heads=hashlib.sha256(heads).digest(),
                items=hashlib.sha256(items).digest())


def run(ref, data, params, dictionary, folder):
    path = os.path.join(folder, 'dictionary')
    with open(path, 'wb') as f:
        f.write(dictionary)
    p = subprocess.run([ref], input=data, capture_output=True, env={'BR_MODE': '0', 'BR_PARAMS': params, 'BR_TRACE': '0', 'BR_DICT': path})
    assert p.returncode == 0, (params, p.returncode)
    return p.stdout


def array(digest):
    return '[' + ', '.join('0x%02x' % b for b in digest) + ']'


def main():
    ref, checkout = sys.argv[1], sys.argv[2]
    data = text_input()
    with tempfile.TemporaryDirectory() as folder:
        lib = library(checkout, folder)
        table_vectors = [(size, tables(lib, dictionary_bytes(size))) for size in [0, 1, 7, 8, 15, 16, 4096, 70000, 2200000]]
        # The dictionary of the encoder vectors: the input's second half, so that there is much to
        # find in it, and some bytes of the generator.
        dictionary = data[1500:] + dictionary_bytes(500)
        encode_vectors = []
        for q in range(12):
            for params in [f'1={q}', f'1={q},2=16', f'1={q},2=26,6=1', f'1={q},9=100']:
                encode_vectors.append((params, run(ref, data[:1500] + data[100:900], params, dictionary, folder)))
    print('//! Tests of prepared (raw) dictionaries against fixed vectors of google/brotli v1.2.0: the hash')
    print('//! tables of `CreatePreparedDictionary` and the output of the encoder with a dictionary at every')
    print('//! quality, and the results of attaching dictionaries.')
    print()
    print('// THIS FILE IS GENERATED by tools/gen_dictionary_tests.py from the C library. Do not edit it.')
    print('''import silk.collections.list { List }
import silk.collections.slice { Slice }
import silk.core.effect { Effect }
import silk.crypto.sha2 { Sha256 }
import silk.mem.allocator { Allocator, OutOfMemoryError }
import silk.num.u16
import silk.num.u32
import silk.num.usize
import silk.testing.testing { AssertionError, Testing }
import encode { BrotliEncoder, OPERATION_FINISH, PreparedDictionary, SHARED_DICTIONARY_RAW, SHARED_DICTIONARY_SERIALIZED }
import enc.compound_dictionary { RawPreparedDictionary, createPreparedDictionary }

// The letters from 'a' of a linear congruential generator, as tools/gen_dictionary_tests.py makes.
effect fn lcgBytes(out: &mut List<u8>, count: usize, seed: u32, alphabet: u32) -> () ! OutOfMemoryError ? &mut Allocator {
  let mut state = seed
  let mut i: usize = 0
  while i < count {
    state = u32.wrappingAdd(u32.wrappingMultiply(state, 1103515245), 12345) & 0x7fffffff
    run List<u8>.append(&mut out, u32.wrappingToU8(97 + u32.shiftRight(state, 16) % alphabet))
    i = i + 1
  }
}

// `dictionary_bytes` of the generator.
effect fn dictionaryBytes(size: usize) -> List<u8> ! OutOfMemoryError ? &mut Allocator {
  let mut out = List<u8>.make()
  let a = if size < 30000 { size } else { 30000 }
  run lcgBytes(&mut out, a, 7, 4)
  let rest = size - a
  let b = if rest < 2000 { rest } else { 2000 }
  run List<u8>.appendRepeated(&mut out, 0, b)
  run lcgBytes(&mut out, rest - b, 11, 16)
  return move out
}

fn sameDigest(a: &[u8; 32], b: &[u8; 32]) -> bool {
  let mut i: usize = 0
  while i < 32 {
    if a[i] != b[i] { return false }
    i = i + 1
  }
  return true
}

fn digestWords(values: &[u32]) -> [u8; 32] {
  let mut state = Sha256.make()
  let mut i: usize = 0
  while i < values.length {
    let v = values[i]
    let bytes: [u8; 4] = [u32.wrappingToU8(v), u32.wrappingToU8(u32.shiftRight(v, 8)), u32.wrappingToU8(u32.shiftRight(v, 16)), u32.wrappingToU8(u32.shiftRight(v, 24))]
    state.update(&bytes)
    i = i + 1
  }
  return state.finish()
}

fn digestHalfwords(values: &[u16]) -> [u8; 32] {
  let mut state = Sha256.make()
  let mut i: usize = 0
  while i < values.length {
    let v = values[i]
    let bytes: [u8; 2] = [u16.wrappingToU8(v), u16.wrappingToU8(u16.shiftRight(v, 8))]
    state.update(&bytes)
    i = i + 1
  }
  return state.finish()
}

effect fn expectTables(size: usize, numItems: u32, bucketBits: u32, slotBits: u32, slotOffsets: &[u8; 32], heads: &[u8; 32], items: &[u8; 32]) -> () ! AssertionError<'static> | OutOfMemoryError ? &mut Allocator {
  let source = run dictionaryBytes(size)
  let prepared = run createPreparedDictionary(List<u8>.asSlice(&source))
  run Testing.expect(prepared.sourceSize == usize.wrappingToU32(size) && prepared.hashBits == 40, "the size and hash bits")
  run Testing.expect(prepared.numItems == numItems && prepared.bucketBits == bucketBits && prepared.slotBits == slotBits, "the table sizes")
  run Testing.expect(sameDigest(&digestWords(RawPreparedDictionary.slotOffsetTable(&prepared)), slotOffsets), "slot_offsets")
  run Testing.expect(sameDigest(&digestHalfwords(RawPreparedDictionary.headTable(&prepared)), heads), "heads")
  run Testing.expect(sameDigest(&digestWords(RawPreparedDictionary.itemTable(&prepared)), items), "items")
  run Testing.expect(sameDigest(&Sha256.hash(RawPreparedDictionary.sourceBytes(&prepared)), &Sha256.hash(List<u8>.asSlice(&source))), "the copy of the source")
}
''')
    print('effect fn tableVectors() -> () ! AssertionError<\'static> | OutOfMemoryError ? &mut Allocator {')
    for size, t in table_vectors:
        print(f'  run expectTables({size}, {t["num_items"]}, {t["bucket_bits"]}, {t["slot_bits"]}, &{array(t["slot_offsets"])}, &{array(t["heads"])}, &{array(t["items"])})')
    print('}')
    print('''
test effect fn preparesTheHashTablesOfTheCLibrary() -> () ! AssertionError<'static> | OutOfMemoryError {
  let mut allocator = Allocator.systemAllocatorProvider()
  run tableVectors() |> Effect.provideMut<Allocator>(&mut allocator)
}

// The input of the encoder vectors and the dictionary attached to them.
effect fn input() -> List<u8> ! OutOfMemoryError ? &mut Allocator {
  let mut out = List<u8>.make()
  run List<u8>.appendSlice(&mut out, Slice.view<u8>(TEXT, 0, 1500))
  run List<u8>.appendSlice(&mut out, Slice.view<u8>(TEXT, 100, 800))
  return move out
}

effect fn dictionary() -> List<u8> ! OutOfMemoryError ? &mut Allocator {
  let mut out = List<u8>.make()
  run List<u8>.appendSlice(&mut out, Slice.view<u8>(TEXT, 1500, TEXT.length - 1500))
  let tail = run dictionaryBytes(500)
  run List<u8>.appendSlice(&mut out, List<u8>.asSlice(&tail))
  return move out
}

// Compresses `input` in one call with `params` and the dictionary attached, as the reference
// driver does, and compares the length and the SHA-256 of the output.
effect fn expectEncoded(params: &[[u32; 2]], length: usize, digest: &[u8; 32], label: string<'static>) -> () ! AssertionError<'static> | OutOfMemoryError ? &mut Allocator {
  let data = run input()
  let dict = run dictionary()
  let mut encoder = run BrotliEncoder.make()
  let mut i: usize = 0
  while i < params.length {
    run Testing.expect(BrotliEncoder.setParameter(&mut encoder, params[i][0], params[i][1]), "the parameter is accepted")
    i = i + 1
  }
  let prepared = run PreparedDictionary.prepare(SHARED_DICTIONARY_RAW, List<u8>.asSlice(&dict), 11)
  run Testing.expect(run BrotliEncoder.attachPreparedDictionary(&mut encoder, move prepared), "the dictionary is attached")
  let mut out = List<u8>.make()
  run List<u8>.appendRepeated(&mut out, 0, 65536)
  let step = run BrotliEncoder.compressStream(&mut encoder, OPERATION_FINISH, List<u8>.asSlice(&data), List<u8>.asMutSlice(&mut out))
  run Testing.expect(step.ok && step.consumed == List<u8>.length(&data) && BrotliEncoder.isFinished(&encoder), "the stream is finished in one call")
  run Testing.expect(step.written == length, label)
  run Testing.expect(sameDigest(&Sha256.hash(Slice.view<u8>(List<u8>.asSlice(&out), 0, step.written)), digest), "the SHA-256 of the output")
}
''')
    print(f'const TEXT: &\'static [u8] = {literal(data)}')
    print()
    print('effect fn encodeVectors() -> () ! AssertionError<\'static> | OutOfMemoryError ? &mut Allocator {')
    for n, (params, out) in enumerate(encode_vectors):
        pairs = [p.split('=') for p in params.split(',')]
        print(f'  let p{n}: [[u32; 2]; {len(pairs)}] = [{", ".join(f"[{a}, {b}]" for a, b in pairs)}]')
        print(f'  run expectEncoded(&p{n}, {len(out)}, &{array(hashlib.sha256(out).digest())}, "{params}")')
    print('}')
    print('''
test effect fn encodesWithADictionaryLikeTheCLibrary() -> () ! AssertionError<'static> | OutOfMemoryError {
  let mut allocator = Allocator.systemAllocatorProvider()
  run encodeVectors() |> Effect.provideMut<Allocator>(&mut allocator)
}

// `BrotliEncoderAttachPreparedDictionary` of the plain C build: at most 15 raw dictionaries, also
// after the stream started; a serialized dictionary cannot be prepared.
effect fn attaching() -> () ! AssertionError<'static> | OutOfMemoryError ? &mut Allocator {
  let serialized = run PreparedDictionary.prepare(SHARED_DICTIONARY_SERIALIZED, b"abc", 11)
  run Testing.expect(!PreparedDictionary.isValid(&serialized), "a serialized dictionary is not prepared")
  let mut encoder = run BrotliEncoder.make()
  run Testing.expect(!run BrotliEncoder.attachPreparedDictionary(&mut encoder, move serialized), "nor attached")
  let empty = run PreparedDictionary.prepare(SHARED_DICTIONARY_RAW, b"", 11)
  run Testing.expect(PreparedDictionary.isValid(&empty), "an empty raw dictionary is prepared")
  run Testing.expect(run BrotliEncoder.attachPreparedDictionary(&mut encoder, move empty), "and attached")
  let mut out = List<u8>.make()
  run List<u8>.appendRepeated(&mut out, 0, 1024)
  let step = run BrotliEncoder.compressStream(&mut encoder, 0, b"some input", List<u8>.asMutSlice(&mut out))
  run Testing.expect(step.ok, "the stream started")
  let mut i: usize = 1
  while i < 15 {
    let more = run PreparedDictionary.prepare(SHARED_DICTIONARY_RAW, b"0123456789abcdef", 11)
    run Testing.expect(run BrotliEncoder.attachPreparedDictionary(&mut encoder, move more), "up to 15 dictionaries, also after the start")
    i = i + 1
  }
  let last = run PreparedDictionary.prepare(SHARED_DICTIONARY_RAW, b"0123456789abcdef", 11)
  run Testing.expect(!run BrotliEncoder.attachPreparedDictionary(&mut encoder, move last), "not a 16th")
}

test effect fn attachesLikeTheCLibrary() -> () ! AssertionError<'static> | OutOfMemoryError {
  let mut allocator = Allocator.systemAllocatorProvider()
  run attaching() |> Effect.provideMut<Allocator>(&mut allocator)
}''')


def literal(data):
    out = []
    for b in data:
        c = chr(b)
        out.append(c if (b < 128 and c.isalnum()) or c in ' !#$%&()*+,-./:;<=>?@[]^_`|~' else '\\x%02x' % b)
    return 'b"' + ''.join(out) + '"'


if __name__ == '__main__':
    main()
