/* A 16-byte block aligned to 64 bytes placed right before js_vm.executeLoop
 * in startup.order, so executeLoop starts at +16 mod 64 and its 18-byte
 * indirect-jump dispatch header (+0x130) lands at 0 mod 64 instead of
 * straddling a 32-byte DSB or 64-byte cache-line boundary. Without this,
 * unrelated size changes before executeLoop flipped its alignment and swung
 * tight loops (Crypto, NavierStokes, Richards, ab.py loops) by 8-35% at equal
 * instruction counts. Never called; retained against section GC. */
#if defined(__wasm__)
typedef int silkjs_text_align_unused;
#elif defined(__APPLE__)
__asm__(".section __TEXT,__text,regular,pure_instructions\n"
        ".p2align 6\n"
        ".globl _silkjs_text_align\n"
        ".no_dead_strip _silkjs_text_align\n"
        "_silkjs_text_align:\n"
        ".fill 16,1,0xcc\n"
        ".text\n");
#elif defined(_WIN32)
__asm__(".section .text$silkjs_text_align,\"xr\"\n"
        ".p2align 6\n"
        ".globl silkjs_text_align\n"
        "silkjs_text_align:\n"
        ".fill 16,1,0xcc\n"
        ".text\n");
#else
__asm__(".section .text.silkjs_text_align,\"axR\",@progbits\n"
        ".p2align 6\n"
        ".globl silkjs_text_align\n"
        ".type silkjs_text_align,@function\n"
        "silkjs_text_align:\n"
        ".fill 16,1,0xcc\n"
        ".size silkjs_text_align, 16\n"
        ".text\n");
#endif
