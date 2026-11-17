#!/usr/bin/env python3
"""Differential testing: run generated JavaScript under several engine configurations and
report every program on which they disagree.

A program is generated from a seed alone, so a failure is reproduced by its seed. Each program
defines a few functions, calls each in a hot loop with stable argument types, then changes the
types, the object shapes and the call targets, printing a checksum after every phase. That is
the pattern a tiering compiler has to get right: specialise on what the loop saw, then give the
specialisation up. The phases, in order: hot, types, target stable, target mixed, late throw (a
hot function throws, through the frames between, into a caller's loop), late after, proto
stable, proto changed, again, end.

Function bodies cover arithmetic, comparisons, property and element reads, calls, closures
(captured variables read and written, closures made in loops over let and var bindings, one
closure whose state lives across the whole program), property writes (properties added in an
order that depends on the arguments, element writes, writes into the arguments, deletes),
exceptions (thrown and caught by callers, caught locally and rethrown, finally blocks that
override the result), and typed arrays (nine element kinds, NaN, -0, out-of-range and non-index
stores, arguments of other kinds and lengths, BigInt64Array, an aliasing view). Values a
function stores pass through __clamp, so strings stay short and no object cycle forms. Nothing
engine-defined is compared: no timing, no error message text, no stack traces.

    python3 scripts/differential.py                          # 200 programs, plain vs observed
    python3 scripts/differential.py --seed 7 --count 1 --show    # print one program
    python3 scripts/differential.py --configs plain,observed,node
    python3 scripts/differential.py --configs plain,observed,jit,jit-stress,node
    python3 scripts/differential.py --self-test              # check the harness itself

Configurations are command templates; `{engine}` is the engine executable, `{jit}` the JIT
executable (modules/jit/shell: $SILKJS_JIT or this host's release build of silkjs-jit-shell),
`{node}` the Node reference, `{file}` the program and `{stats}` a file the run may write one
line of `name value` counters to; the counters are summed per configuration and printed. The first configuration named is the baseline the others
are compared with.

  plain      {engine} {file}                    the interpreter's ordinary dispatch loop
  observed   {engine} --debug-observed {file}   the instruction-observing loop of the debugger
  node       {node} {file}                      a reference engine ($NODE_REFERENCE or `node`)
  jit        {jit} --jit ... {file}             hot functions compiled to x86-64 (docs/jit/compiled-entry.md)
  jit-stress {jit} --jit --jit-stress=3 ...     the same, every function hot at its first entry and
                                                every third guard check deoptimizing, never unlinked
  jit-calls  {jit} --jit --jit-calls ...        jit, also compiling functions that make calls
  jit-calls-stress                              jit-stress with --jit-calls

Adding a configuration: for a one-off run pass `--config NAME=TEMPLATE` (repeatable; the name is
appended to --configs). To make it permanent, add NAME: TEMPLATE to BUILTIN in this script, and
add NAME to REFERENCES when it is another engine rather than a SilkJS configuration. A JIT tier
or a deoptimization-stress mode is a SilkJS configuration: any disagreement with plain is a
mismatch.

A reference engine that is not installed is reported as skipped, never as passing. A program on
which two SilkJS configurations agree and only a reference engine differs is counted apart, as
`reference`, because it is a conformance question and not a tiering bug.

Exit status: 0 when every compared configuration agreed, 1 on a mismatch, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

BUILTIN = {
    "plain": "{engine} {file}",
    "observed": "{engine} --debug-observed {file}",
    "node": "{node} {file}",
    "jit": "{jit} --jit --jit-threshold=20 --jit-stats={stats} {file}",
    "jit-stress": "{jit} --jit --jit-threshold=1 --jit-stress=3 --jit-deopt-limit=0 --jit-stats={stats} {file}",
    "jit-calls": "{jit} --jit --jit-calls --jit-threshold=20 --jit-stats={stats} {file}",
    "jit-calls-stress": "{jit} --jit --jit-calls --jit-threshold=1 --jit-stress=3 --jit-deopt-limit=0 --jit-stats={stats} {file}",
}
REFERENCES = {"node"}

PRELUDE = """\
var __out = typeof print === 'function' ? print : console.log;
var __sum = 0;
var __fin = 0;
var __long = 0;
var __at = -1;
var __g = 0;
function __sumthis(n) { var t = 0; for (var i = 0; i < n; i++) { t = t + this.x + this.y; } return t; }
function __show(v) {
  if (typeof v === 'number') return Object.is(v, -0) ? '-0' : String(v);
  if (typeof v === 'string') return JSON.stringify(v);
  if (typeof v === 'function') return 'function';
  if (v === null || typeof v !== 'object') return String(v);
  var keys = Object.keys(v).map(function (k) { return k + ':' + __show(v[k]); });
  if (!Array.isArray(v)) return '{' + keys.join(',') + '}';
  var named = keys.slice(Object.keys(v).filter(function (k) { return k === String(k >>> 0); }).length);
  return '[' + v.map(__show).join(',') + ']' + (named.length ? '{' + named.join(',') + '}' : '');
}
function __mix(v) {
  var s = __show(v);
  for (var i = 0; i < s.length; i++) __sum = (Math.imul(__sum, 31) + s.charCodeAt(i)) | 0;
}
function __err(e) { return e instanceof Error ? e.constructor.name : 'value ' + __show(e); }
function __try(f, a, b) {
  try { __mix(f(a, b)); } catch (e) { __mix('thrown ' + __err(e)); }
}
function __clamp(v) {
  if (typeof v === 'string') return v.slice(0, 6);
  if (v !== null && typeof v === 'object') return 'o';
  return v;
}
function __phase(name) { __out(name + ' ' + __sum + ' ' + __fin); }
"""
# Why the prelude is shaped like this:
# - __show defines the checksum from values alone; error messages and stack traces are left out.
# - __clamp is applied to every value a generated function stores (captured variables, properties,
#   elements, thrown values): strings stay short, so nothing grows without bound across a hot loop,
#   and objects are never stored, so no cycle can reach __show.
# - __fin counts finally blocks run, __at is the argument at which guarded functions throw.

TYPED = ["Int8Array", "Uint8Array", "Uint8ClampedArray", "Int16Array", "Uint16Array",
         "Int32Array", "Uint32Array", "Float32Array", "Float64Array"]

# How a generated function's body is built; repeated entries weight the pick.
FLAVORS = ["plain", "loop", "branch", "closure", "closures", "writes", "writes", "throws", "catches", "typed",
           "intloop", "intloop", "intnest", "intbranch", "numloop", "numloop", "intops", "intops", "counters",
           "calls", "calls", "fields", "elements", "globals", "method", "tests", "shuffles", "instanceof", "tries", "tries", "tdz",
           "literals", "operators", "classes"]

# Each area of the generator: a pattern that marks a program exercising it, and a source
# rewrite that stands in for a miscompile there. The self-test runs the rewrite as a broken
# configuration, so it shows that the checksums observe the area, not only that a planted
# output change is caught.
AREAS = {
    "prototypes": (r"delete proto\.x", r"delete proto\.x;", ";"),  # the delete is lost
    "closures": (r"\bc0 = __clamp\(", r"\bc0 = __clamp\(", "void __clamp("),  # captured writes are lost
    "property writes": (r"\.\w+ = __clamp\(", r"\b[oab]\.\w+ = __clamp\(", "void __clamp("),  # named stores are lost
    "exceptions": (r"\bthrow ", r"\bthrow ", "return "),  # a throw returns instead
    "typed arrays": (r"\bvar ta = new ", r"\bvar ta = new \w+\(", "var ta = new Float64Array("),  # wrong element kind
    "number loops": (r"\bvar d = ", r"\bd = d \+ ", "d = d - "),  # a double add becomes a subtract
    "int operators": (r"\bvar u = ", r"\bvar u = a \| 0;", "var u = (a | 0) ^ 1;"),  # the first operand is off by one bit
}


class Generator:
    """One program per seed. Every statement is one line, so the minimizer can delete lines."""

    def __init__(self, seed: int, hot: int):
        self.random = random.Random(seed)
        self.seed = seed
        self.hot = hot
        self.functions = 0
        self.reads: list[str] = []  # variables in scope besides a and b
        self.typed = self.pick(TYPED)  # the element kind of the stable typed-array arguments
        self.guarded: list[str] = []  # functions that throw when a === __at

    def pick(self, values):
        return self.random.choice(values)

    def integer(self) -> str:
        return str(self.pick([0, 1, 2, 3, 7, -1, -8, 31, 32, 255, 65535, 1073741823, 2147483647, -2147483648]))

    def atom(self, depth: int) -> str:
        choices = ["a", "b", "a", "b", self.integer(), "a.x", "b.y", "a[0]", "b.length", "a.x"] + self.reads * 2
        if self.functions and depth < 2:
            choices.append(f"f{self.random.randrange(self.functions)}(b, a)")
        return self.pick(choices)

    def expression(self, depth: int = 0) -> str:
        if depth >= 3 or self.random.random() < 0.25:
            return self.atom(depth)
        kind = self.random.random()
        left, right = self.expression(depth + 1), self.expression(depth + 1)
        if kind < 0.55:
            op = self.pick(["+", "-", "*", "/", "%", "|", "&", "^", "<<", ">>", ">>>", "+", "-", "*"])
            return f"({left} {op} {right})"
        if kind < 0.75:
            op = self.pick(["<", "<=", ">", ">=", "==", "===", "!=", "!=="])
            return f"({left} {op} {right} ? {self.expression(depth + 1)} : {self.expression(depth + 1)})"
        if kind < 0.85:
            # A negative literal gets parentheses: `--1` would not parse.
            operand = f"({left})" if left[0] in "-+" else left
            return f"({self.pick(['-', '~', '!', '+', 'typeof '])}{operand})"
        if kind < 0.93:
            return f"Math.{self.pick(['abs', 'floor', 'sqrt', 'trunc', 'fround'])}({left})"
        return f"({left} {self.pick(['&&', '||', '??'])} {right})"

    def using(self, names: list[str], depth: int = 1) -> str:
        """An expression that may also read `names`."""
        saved = self.reads
        self.reads = saved + names
        try:
            return self.expression(depth)
        finally:
            self.reads = saved

    def clamped(self, names: list[str] | None = None) -> str:
        return f"__clamp({self.using(names or [])})"

    def thrown(self) -> str:
        return self.pick(["new RangeError('r')", "new TypeError('t')", "new Error('e')", self.integer(),
                          "'s'", f"{{code: {self.integer()}}}", self.clamped(), "undefined", "null"])

    def condition(self, names: list[str] | None = None) -> str:
        return self.pick(["typeof a === 'string'", "b === undefined", "a === null",
                          f"(({self.using(names or [])}) & 15) === 3", f"({self.using(names or [])})"])

    def body(self, flavor: str) -> str:
        if flavor == "plain":
            return f"return {self.expression()};"
        if flavor == "loop":
            return (f"var t = {self.expression()}; for (var i = 0; i < {self.pick([1, 2, 3, 5])}; i++) "
                    f"{{ t = {self.pick(['t + i', 't ^ i', '(t * 3) | 0', 't + a', 't - b'])}; }} return t;")
        if flavor == "branch":
            return f"if ({self.expression(1)}) {{ return {self.expression(1)}; }} return {self.expression(1)};"
        if flavor == "closure":
            # An inner function that writes a variable of its parent, which the parent then reads.
            return (f"var c0 = {self.clamped()}; function g(x) {{ c0 = {self.clamped(['c0', 'x'])}; "
                    f"return {self.using(['c0', 'x'])}; }} var t = __clamp(g(b)); return [t, __clamp(g(a)), c0];")
        if flavor == "closures":
            # Closures created in a loop, over a per-iteration (let) or shared (var) binding.
            binding = self.pick(["let", "var"])
            return (f"var fs = []; for ({binding} j = 0; j < {self.pick([1, 2, 3])}; j++) {{ let c0 = {self.clamped(['j'])}; "
                    f"fs.push(function (x) {{ c0 = {self.clamped(['c0', 'j', 'x'])}; return {self.using(['c0', 'j', 'x'])}; }}); }} "
                    f"var t = []; for (var k = 0; k < fs.length; k++) {{ t.push(__clamp(fs[k](a)), __clamp(fs[(k + 1) % fs.length](b))); }} "
                    f"return t;")
        if flavor == "writes":
            # Writes that add properties in an order that depends on the arguments, element
            # writes, writes into the arguments, and deletes.
            literal = self.pick(["{}", "{x: 1}", "{y: 2, x: 3}", "[]", "[1, 2]", f"new {self.typed}(3)"])
            first, second = self.pick(["x", "y", "z", "w0"]), self.pick(["x", "y", "z", "w1"])
            key = self.pick([f"'k' + (({self.using(['o.x'])}) & 3)", f"({self.using(['o.x'])}) & 3"])
            parts = [f"var o = {literal};", f"o.{first} = {self.clamped()};",
                     f"if ({self.using(['o.x', 'o.y'])}) {{ o.{second} = {self.clamped(['o.x'])}; }} else {{ o[{key}] = {self.clamped()}; }}"]
            parts += self.random.sample([
                f"a.{self.pick(['x', 'y', 'w2'])} = {self.clamped(['o.x', 'o.y'])};",
                f"b[({self.using(['o.x'])}) & 7] = {self.clamped(['o.y'])};",
                f"a[0] = {self.clamped(['o[0]'])};",
                f"a.length = ({self.expression(2)}) & 3;",
                f"delete o.{self.pick(['x', 'y', 'z'])};",
            ], self.random.randrange(1, 4))
            # The arguments are part of the result, so that writes into them are observed.
            parts.append(f"return [{self.pick(['o', self.using(['o.x', 'o.y', 'o[0]'])])}, a, b];")
            return " ".join(parts)
        if flavor == "throws":
            return f"if ({self.condition()}) throw {self.thrown()}; return {self.expression()};"
        if flavor == "catches":
            if self.random.random() < 0.6:
                # Caught inside the function, sometimes rethrown, always counted by finally.
                rethrow = self.pick(["", "if (j === 2) throw e; "])
                return (f"var t = {self.clamped()}; for (var j = 0; j < {self.pick([1, 3, 4])}; j++) {{ "
                        f"try {{ if ({self.condition(['t', 'j'])}) throw {self.thrown()}; t = {self.clamped(['t', 'j'])}; }} "
                        f"catch (e) {{ {rethrow}t = __clamp(__err(e) + j); }} finally {{ __fin = (__fin + 1) | 0; }} }} return t;")
            # A finally that may override the return value or the exception in flight.
            return (f"var t = {self.clamped()}; try {{ if ({self.condition(['t'])}) throw {self.thrown()}; return t; }} "
                    f"finally {{ __fin = (__fin + 1) | 0; if ({self.condition(['t'])}) return [t]; }}")
        if flavor == "typed":
            # Stores that convert, wrap, clamp or round; out-of-range and non-index stores that
            # do nothing; then a loop over whatever the argument's length is.
            kind = self.pick(TYPED)
            return (f"var ta = new {kind}(4); ta[0] = {self.expression(1)}; ta[1] = NaN; ta[2] = -0; "
                    f"ta[{self.pick(['4', '-1', '1.5', 'ta.length'])}] = {self.expression(1)}; "
                    f"ta[({self.expression(2)}) & 7] = {self.using(['ta[0]'])}; var t = 0; "
                    f"for (var j = 0; j < a.length; j++) {{ t = {self.clamped(['t', 'a[j]', 'ta[j & 3]'])}; }} "
                    f"return [t, ta];")
        if flavor == "intloop":
            # Integer arithmetic in a counted loop, the subset the first compiler takes: the
            # bound comes from an argument, the update may overflow int32 (a deopt).
            update = self.pick(["t + i", "t - a", "t * 3 + i", "t + a * i", "a - t + i", "t * t - b", "t + i * i - b"])
            return (f"var t = {self.pick(['0', 'a', 'b', str(self.random.randrange(-9, 10))])}; var n = b; "
                    f"if (n > {self.pick([5, 20, 70])}) n = {self.pick([3, 20, 70])}; "
                    f"for (var i = 0; i < n; i++) {{ t = {update}; }} return t;")
        if flavor == "intnest":
            return (f"var t = a; for (var i = 0; i < {self.pick([2, 4])}; i++) {{ for (var j = i; j < {self.pick([3, 6])}; j++) "
                    f"{{ t = {self.pick(['t + i * j - b', 't - j + a', 't * 2 - i'])}; }} }} return t;")
        if flavor == "calls":
            # Calls from a loop: a method of the argument (bytecode or native), the same function
            # taken out and called without a receiver, through call and apply, and an argument
            # that is not callable at all (a TypeError) once the types change.
            call = self.pick(["a.f(i, b)", "a.g(i, b)", "h(i)", "a.f.call(a, b, i)", "a.f.apply(a, [i, b])", "a.f(a.f(i), i)",
                              "b(i)", "a.k(i)"])
            return (f"var t = {self.pick(['0', 'b', '1'])}; var h = a.f; for (var i = 0; i < {self.pick([2, 3, 6])}; i++) "
                    f"{{ t = {self.pick(['t + ' + call, '(t ^ ' + call + ')', '__clamp(t * 2 + ' + call + ')'])}; }} return t;")
        if flavor == "intbranch":
            return (f"var t = a; for (var i = 0; i < {self.pick([4, 9])}; i++) {{ if (t {self.pick(['>', '<', '>=', '==='])} b) "
                    f"t = t - {self.pick(['i', '1', 'a'])}; else t = t + {self.pick(['2 * i', 'b', '3'])}; }} return t;")
        if flavor == "fields":
            # Named reads and stores in a counted loop, the J subset: same-shape stores to
            # existing fields compile, reads of the arguments' fields deopt on a miss.
            literal = self.pick(["{x: 1, y: 2}", "{y: 2, x: 1}", "{x: a, y: b}"])
            # No update feeds o.x back into itself through t: a string would double each round.
            update = self.pick(["o.x + i", "o.x - o.y", "o.y * 2 - i", "i - o.y"])
            return (f"var o = {literal}; var t = 0; var n = b; if (n > {self.pick([5, 20])}) n = {self.pick([3, 20])}; "
                    f"for (var i = 0; i < n; i++) {{ o.x = {update}; o.y = o.x - o.y; t = t + {self.pick(['a.x', 'b.y', 'o.x', 'a.y'])}; }} "
                    f"return [o.x, o.y, t];")
        if flavor == "elements":
            # Element reads and stores of a fast Array in a loop over its length; an append and
            # the arguments' elements deopt.
            tail = self.pick(["", "arr[arr.length] = t; ", "arr[-1] = t; "])
            return (f"var arr = [a, b, {self.integer()}, 2, 3]; var t = 0; "
                    f"for (var i = 0; i < arr.length; i++) {{ t = t + arr[i]; arr[i] = {self.pick(['t - i', 'i', 'a', 'arr[i] + 1'])}; }} "
                    f"{tail}for (var j = 0; j < {self.pick(['a.length', 'b.length', '2'])}; j++) {{ t = t + a[j]; }} return [t, arr];")
        if flavor == "globals":
            # A global read and stored in a loop.
            return (f"var t = 0; var n = b; if (n > 20) n = {self.pick([3, 20])}; "
                    f"for (var i = 0; i < n; i++) {{ __g = {self.pick(['__g + i', '__g - a', 'i'])}; t = t + __g; }} "
                    f"if (__g > 1000) __g = 0; if (__g < -1000) __g = 0; return t;")
        if flavor == "method":
            # `this` reads in a hot prelude function, on objects of several shapes.
            return (f"var o = {self.pick(['{x: a, y: b}', '{y: b, x: a}', '{x: a, y: b, m: 1}'])}; "
                    f"return __sumthis.call(o, {self.pick([2, 5])}) + __sumthis.call(a, 1);")
        if flavor == "numloop":
            # A double accumulator in a counted loop (docs/jit/doubles.md): it starts as an Int or
            # a double, so an int add may overflow or meet a double and deoptimize, after which
            # the recompiled function carries it as f64. Starts, steps and tests meet NaN, -0 and the infinities.
            # A numeric start: a string a would double in length each time round.
            start = self.pick(["0", "0.5", "+a", "-0", "b / 2", "2147483600", "NaN", "Infinity", "-Infinity", "a / 0"])
            step = self.pick(["d + i * 0.5", "d + 1073741824", "d / 3 + i", "d * 1.5 - b", "d + Math.sqrt(i)",
                              "Math.floor(d / 2) + i", "Math.abs(d - a) + 0.25", "-d + i", "d + (i | 0) / 7", "d * 0 + i", "d - Infinity"])
            # Every branch form meets NaN: the negations (!(d < b) is not d >= b) and ToBoolean.
            test = self.pick(["d < b", "d >= 0", "d !== d", "d === 0", "d > 1e9", "!(d <= a)", "!(d < b)",
                              "!(d > -0)", "d != b", "d == -0", "d", "!d", "d <= Infinity"])
            return (f"var d = {start}; var n = b; if (n > {self.pick([5, 20, 70])}) n = {self.pick([3, 20, 70])}; "
                    f"var c = 0; for (var i = 0; i < n; i++) {{ d = d + {step}; if ({test}) c++; }} "
                    f"return [d, c, d | 0, d >>> 0];")
        if flavor == "intops":
            # The int32 operators beyond add, sub and mul, with the cases where the interpreter
            # makes a double: >>> past the int32 maximum, % with a -0 result or a non-positive
            # divisor, - of 0 or the minimum.
            update = self.pick(["(u ^ (i << 3)) | a", "u >>> 1", "(u % 7) - i", "~u + (i & 3)", "-u + b",
                                "(u >> (i & 31)) & 0xffff", "(u << 5) - u", "u % (b | 0)", "Math.imul(u, 31) + i",
                                "(u & a) | (u ^ b)", "-(u % 3)"])
            check = self.pick(["u === 3", "u !== -1", "u === undefined", "typeof u === 'number'", "!u", "u === null"])
            return (f"var u = a | 0; var n = b; if (n > {self.pick([6, 30])}) n = {self.pick([4, 30])}; var c = 0; "
                    f"for (var i = 0; i < n; i++) {{ u = {update}; if ({check}) c = c + 1; else c = c - (u & 1); }} "
                    f"return [u, c];")
        if flavor == "counters":
            # Increments in every form, on locals and on values kept on the stack (x++ in an
            # expression), and logical operators that keep their operand.
            form = self.pick(["k++", "++k", "k--", "--k", "k += 2", "k -= a", "k = k + 1"])
            keep = self.pick(["(k && b) || 1", "k || a", "(a && k) || 0", "k ?? b"])
            return (f"var k = {self.pick(['a', '0', 'b', '2147483646'])}; var s = 0; "
                    f"for (var i = 0; i < {self.pick([3, 8, 40])}; i++) {{ {form}; s = s + (k++ & 7) + ({keep}); }} "
                    f"return [k, s];")
        if flavor == "tries":
            # Try regions in hot code (stream P): the region holds arithmetic, a property read,
            # a call that may throw or a throwing getter; it throws a primitive, an object or an
            # Error at an iteration that depends on the arguments; finally blocks see return,
            # break and continue; handlers rethrow into an outer try.
            n = self.pick([3, 6, 20])
            thrown = self.thrown()
            body = self.pick([
                f"t = {self.clamped(['t', 'j'])};",
                f"t = __clamp(t + a.x + j);",
                f"t = __clamp(t + {self.pick(['a.f(j, b)', 'a.k(j)', 'b(j)', 'a.g(j, b)'])});",
                f"t = __clamp(t + {self.pick(['{get x() { throw new TypeError(\'g\'); }}', '{get x() { return j; }}', '{x: j}'])}.x);",
            ])
            when = self.pick(["j === (b & 7)", "(t & 15) === 3", "j === 2 && a === b", f"({self.using(['t', 'j'])}) === 1"])
            shape = self.pick(["catch", "catch", "finally", "nested", "return", "jumps", "rethrow", "header", "header"])
            head = f"var t = {self.pick(['0', 'b', '1'])}; "
            if shape == "header":
                # A long loop inside the try region on the first calls (__long): its header
                # has the marker under it, so on-stack replacement enters with it.
                inner, close = self.pick([("", ""), ("try { ", "} finally { __fin = (__fin + 1) | 0; } ")])
                return (f"var n = __long < 3 ? 12000 : {n}; __long = __long + 1; " + head +
                        f"try {{ {inner}for (var j = 0; j < n; j++) {{ t = (t + (j & 7)) | 0; if (j === n - 1 - (b & 3) && {self.pick(['true', 'a === b', '(t & 1) === 0'])}) {self.pick([f'throw {thrown};', 'return [t, j];', 'break;'])} }} "
                        f"{close}}} catch (e) {{ t = __clamp(__err(e) + t); }} return t;")
            if shape == "catch":
                return (head + f"for (var j = 0; j < {n}; j++) {{ try {{ {body} if ({when}) throw {thrown}; }} "
                        f"catch (e) {{ t = __clamp(__err(e) + j); }} }} return t;")
            if shape == "finally":
                return (head + f"for (var j = 0; j < {n}; j++) {{ try {{ {body} if ({when}) throw {thrown}; }} "
                        f"finally {{ __fin = (__fin + 1) | 0; t = __clamp(t + 1); }} }} return t;")
            if shape == "nested":
                return (head + f"for (var j = 0; j < {n}; j++) {{ try {{ try {{ {body} if ({when}) throw {thrown}; }} "
                        f"catch (e) {{ if (j & 1) throw e; t = __clamp(t - j); }} }} catch (f) {{ t = __clamp(__err(f) + t); }} }} return t;")
            if shape == "return":
                return (head + f"for (var j = 0; j < {n}; j++) {{ try {{ {body} if ({when}) return [t, j]; }} "
                        f"{self.pick(['catch (e) { return __err(e); }', 'finally { __fin = (__fin + 1) | 0; }'])} }} return t;")
            if shape == "jumps":
                return (head + f"for (var j = 0; j < {n}; j++) {{ try {{ if (j === 1) continue; {body} if ({when}) break; }} "
                        f"finally {{ __fin = (__fin + 1) | 0; t = __clamp(t + j); {self.pick(['', 'if (j === 4) return t;'])} }} }} return t;")
            return (head + f"try {{ for (var j = 0; j < {n}; j++) {{ try {{ {body} if ({when}) throw {thrown}; }} "
                    f"catch (e) {{ t = __clamp(t + 1); throw e; }} }} }} catch (e) {{ return [t, __err(e)]; }} return t;")
        if flavor == "tdz":
            # Lexical slots in a loop long enough for on-stack replacement on its first calls
            # (__long): one read before its initialization at an iteration that depends on the
            # arguments (a ReferenceError, or never), one initialized before the loop, one made
            # per iteration and captured by a closure.
            when = self.pick(["j === n - 1 - (b & 7)", "j === 11000 && a === b", "j < 0", "j > 10000 && (t & 4095) === 77"])
            return (f"var n = __long < 3 ? 12000 : {self.pick([3, 8])}; __long = __long + 1; var t = 0; var h = null; "
                    f"let early = {self.pick(['a', '3', 'b'])}; "
                    f"for (var j = 0; j < n; j++) {{ if ({when}) t = __clamp(t + late); else t = (t + (j & 7)) | 0; "
                    f"{self.pick(['', 't = __clamp(t + early);', 'let c = j & 3; h = function () { return c; }; t = (t + h()) | 0;'])} }} "
                    f"let late = {self.pick(['a', '1'])}; return [t, h ? h() : 0];")
        if flavor == "tests":
            # Nullish, undefined and typeof tests (J2) on values of every type, as branch
            # conditions and as values; `??` keeps its operand on one edge only.
            test = self.pick(["x == null", "x === undefined", "x === null", "x != null", "typeof x === 'undefined'",
                              "typeof x === 'function'", "typeof x === 'string'", "typeof x === 'object'",
                              "typeof x === 'number'", "(x ?? 7) === 7", "x !== undefined"])
            value = self.pick(["typeof x", "x ?? i", "x == null", "typeof x === 'boolean'", "x === null || x === undefined"])
            return (f"var vs = [a, b, null, undefined, {{x: 1}}, 'x', 0, NaN, __sumthis, true, [1], -0]; var c = 0; var w = []; "
                    f"for (var i = 0; i < vs.length; i++) {{ var x = vs[i]; if ({test}) c = c + i + 1; w[w.length] = {value}; }} "
                    f"return [c, w.length, String(w[{self.pick([0, 1, 3, 7])}])];")
        if flavor == "shuffles":
            # Compound assignments to properties and elements, postfix updates, chained stores
            # and optional chaining: the stack shuffle opcodes (insert, perm, rot, swap).
            step = self.pick(["o.x += i", "o.x -= b", "arr[i & 3]++", "s += o.y++", "s += arr[i & 3]--",
                              "o.z = o.w = i", "p = q = i - a", "arr[i & 3] *= 1", "o.y ^= i"])
            other = self.pick(["s += p + q", "s += o?.x", "s += (o.x -= 1)", "s += o.z", "s += arr[1]"])
            return (f"var o = {{x: a, y: b, z: 0, w: 0}}; var arr = [a, b, 1, 2]; var s = 0; var p = 0; var q = 0; "
                    f"for (var i = 0; i < {self.pick([3, 8, 30])}; i++) {{ {step}; {other}; }} "
                    f"return [s, o.x, o.y, o.z, arr[0], arr[1], arr[2], arr[3], p, q];")
        if flavor == "instanceof":
            # instanceof on classes and subclasses, primitives on the left, and right operands
            # that decline the fast path: a bound function, a custom Symbol.hasInstance.
            right = self.pick(["P", "Q", "Object", "Array", "Function", "P", "Q", "P.bind(null)", "H"])
            return (f"class P {{}} class Q extends P {{}} class H {{ static [Symbol.hasInstance](v) {{ return v === 1; }} }} "
                    f"var C = {right}; var vs = [a, b, new P(), new Q(), {{}}, [1], 1, 's', null, undefined, __sumthis]; var c = 0; "
                    f"for (var i = 0; i < vs.length; i++) {{ if (vs[i] instanceof C) c = c + i + 1; if (vs[i] instanceof P) c = c * 2 + 1; }} "
                    f"return c;")
        if flavor == "literals":
            # Object, array and regexp literals and string constants in a hot function (generic
            # instruction exits): fields from the arguments, computed keys, deletes.
            key = self.pick(["'k'", "'k' + (a & 1)", "typeof b"])
            regexp = self.pick(["/a+/g", "/[0-9]/", "/x/y"])
            return (f"var o = {{x: {self.clamped()}, y: 's', [{key}]: b}}; var r = {regexp}; var arr = [a, o.x, 'z']; "
                    f"var t = 0; for (var i = 0; i < {self.pick([2, 5])}; i++) {{ t = t + (r.test('aa' + i + a) ? 1 : 0) + arr.length; }} "
                    f"delete o.y; return [__clamp(o.x), 'y' in o ? 1 : 0, {key} in o ? 1 : 0, t, r.lastIndex, arr[2]];")
        if flavor == "operators":
            # typeof, in, instanceof, delete and ** on mixed types, with the throwing forms
            # (in and instanceof of a primitive right side) caught in the function.
            target = self.pick(["a", "b", "[a]", "{p: a}", "null", "Object(b)"])
            ctor = self.pick(["Object", "Array", "Number", "b", "{}"])
            # Integer exponents of small bases only: pow of other operands differs from V8 in
            # the last place (the interpreter's, too), which is not what this flavour tests.
            power = self.pick(["a ** 2", "((a | 0) % 7) ** ((b | 0) % 4)", "2 ** -1", "(-0) ** 3", "((b | 0) & 15) ** 3"])
            return (f"var v = {target}; var w = 0; for (var i = 0; i < {self.pick([1, 3, 6])}; i++) {{ "
                    f"try {{ w = w + ('p' in v ? 1 : 2); }} catch (e) {{ w = w + 10; }} "
                    f"try {{ w = w + (v instanceof {ctor} ? 100 : 200); }} catch (e) {{ w = w + 1000; }} }} "
                    f"var d = {{p: 1, q: 2}}; delete d[typeof a === 'number' ? 'p' : 'q']; "
                    f"return [typeof v, w, __clamp({power}), 'p' in d ? 1 : 0, typeof (v && v.p)];")
        if flavor == "classes":
            # Methods with private fields, `#p in`, computed method names (the class is made
            # once, below, so its methods run hot).
            return (f"var k = new __K{self.functions}(a); var s = 0; for (var i = 0; i < {self.pick([1, 4])}; i++) {{ "
                    f"s = s + __clamp(k.add(i)); }} return [__clamp(k.get()), s, __K{self.functions}.has(k) ? 1 : 0, "
                    f"__K{self.functions}.has({{}}) ? 1 : 0, k['m' + (b & 1)]()];")
        raise ValueError(flavor)

    def function(self) -> str:
        name = f"f{self.functions}"
        flavor = self.pick(FLAVORS)
        body = self.body(flavor)
        if flavor == "throws" or self.random.random() < 0.25:
            # Throws only in the "late throw" phase, after the function has run hot.
            body = f"if (a === __at) throw {self.thrown()}; " + body
            self.guarded.append(name)
        self.functions += 1
        if flavor == "classes":
            klass = (f"var __K{self.functions - 1} = class {{ #p; constructor(v) {{ this.#p = __clamp(v); }} get() {{ return this.#p; }} "
                     f"add(x) {{ this.#p = __clamp(this.#p + x); return this.#p; }} static has(o) {{ return #p in o; }} "
                     f"m0() {{ return 0; }} ['m' + 1]() {{ return typeof this.#p; }} }};")
            return f"{klass} function {name}(a, b) {{ {body} }}"
        if flavor == "closure" and self.random.random() < 0.5:
            # A closure made once, whose captured state lives across every call of the program.
            return (f"var {name} = (function () {{ var c0 = {self.integer()}, c1 = 0; return function (a, b) {{ "
                    f"c1 = (c1 + 1) | 0; c0 = {self.clamped(['c0', 'c1'])}; {body} }}; }})();")
        return f"function {name}(a, b) {{ {body} }}"

    def value(self, kind: str) -> str:
        if kind == "int":
            return self.pick(["i", "i + 1", "i * 3", "i & 7", "(i << 3) | 1", "100 - i"])
        if kind == "big":
            return self.pick(["2147483647 - i", "i * 1073741824", "-2147483648 + i", "4294967295 + i"])
        if kind == "double":
            return self.pick(["i + 0.5", "i / 3", "-0", "0.1 * i", "1e300 * (i + 1)", "NaN", "Infinity"])
        if kind == "string":
            return self.pick(["'s' + i", "''", "String(i)", "'12'", "'x'.repeat(i % 5)"])
        if kind == "objectA":
            return "{x: i, y: i + 1}"
        if kind == "objectB":
            return self.pick(["{y: i, x: i * 2}", "{x: i + 0.5, y: 's', z: 1}", "{x: 'p' + i}"])
        if kind == "array":
            return self.pick(["[i, i + 1]", "[i + 0.5]", "[]", "[, i]", "['a', i]"])
        if kind == "typed":
            return f"new {self.typed}([i, -i, i * 3])"
        if kind == "typedB":
            other = self.pick(TYPED)
            return self.pick([f"new {other}([i + 0.5, -0, NaN, 300, -129])", f"new {other}({self.pick([0, 1, 8])})",
                              "new BigInt64Array([1n, -2n])", f"new {other}([i, i]).subarray(1)",
                              "new Uint8Array(new Float64Array([i + 0.5]).buffer)"])
        if kind == "withf":
            # Methods: a closure reading its receiver (sloppy, so a missing receiver is the global
            # object), a native, and one that throws for some inputs.
            return self.pick(["{x: i, f: function (v, w) { return (v * 3 + (this.x | 0)) | 0; }, g: Math.max, "
                              "k: function (v) { if (v > 4) throw new RangeError('k' + v); return v; }}",
                              "{x: i, f: Math.min, g: function (v) { return typeof v; }, k: Math.abs}"])
        if kind == "odd":
            return self.pick(["null", "undefined", "true", "{valueOf: function () { return i; }}", "Symbol.iterator"])
        raise ValueError(kind)

    def loop(self, phase: str, count: int, target: str, kinds: tuple[str, str]) -> list[str]:
        a, b = self.value(kinds[0]), self.value(kinds[1])
        return [f"for (var i = 0; i < {count}; i++) {{ __try({target}, {a}, {b}); }}", f"__phase('{phase}');"]

    def longLoops(self, stable: tuple[str, str]) -> list[str]:
        """Loops long enough for an interrupt poll (every 10000 back edges and calls) to land in
        them: on-stack replacement into a running frame, called once from the top level and
        from another function's loop (an inline frame), with stable and then changed argument
        types. Heap values in locals cross the entry and the exits; an update can overflow
        int32, and statements outside the first subset make side exits (docs/jit/osr.md)."""
        update = self.pick(["t + i", "t - a", "t * 3 + i", "t + a * i", "a - t + i", "t + i * i - b", "t + 3"])
        side = self.pick(["", "", "o.x = o.x + 1; ", "t = t | 0; ", "if ((i & 1023) === 0) s = s + i; ",
                          "if (i === n - 2) o = [t]; ", "u = u + 0.5; "])
        lines = [f"function long0(a, b, n) {{ var t = {self.pick(['0', 'a', 'b', '1'])}; var o = {{x: 1}}; var s = 's'; var u = 0; "
                 f"for (var i = 0; i < n; i++) {{ t = {update}; if (t > 100000 || t < -100000) t = {self.pick(['0', 'b', 't % 7'])}; {side}}} "
                 f"return [t, o.x, o.length, s.length, u]; }}",
                 f"function long1(a, b, n) {{ var r = 0; for (var k = 0; k < 3; k++) {{ r = __clamp(r + long0(a, b, n + k)[0]); }} return r; }}",
                 f"function long2(n) {{ var t = 0; while (n > 0) {{ var j = 0; do {{ t = t + j; j = j + 1; }} while (j < 50); "
                 f"if (t > 1000000) t = t - 1000000; n = n - 1; }} return t; }}"]
        a, b = re.sub(r"\bi\b", "7", self.value(stable[0])), re.sub(r"\bi\b", "3", self.value(stable[1]))
        changed = re.sub(r"\bi\b", "5", self.value(self.pick(["double", "string", "objectA", "odd", "big"])))
        calls = [(f"long0({a}, {b}, {self.pick([12000, 25000])})", "long loop"), (f"long1({a}, {b}, {self.pick([4000, 9000])})", "long inline"),
                 (f"long2({self.pick([300, 700])})", "long nested"), (f"long0({changed}, {b}, 12000)", "long changed")]
        for call, phase in calls:
            lines += [f"try {{ __mix({call}); }} catch (e) {{ __mix('threw ' + __err(e)); }}", f"__phase('{phase}');"]
        return lines

    def program(self) -> str:
        lines = [f"// differential.py seed {self.seed} hot {self.hot}"]
        count = self.random.randrange(2, 6)
        for _ in range(count):
            lines.append(self.function())
        names = [f"f{n}" for n in range(count)]
        stable = self.pick([("int", "int"), ("int", "int"), ("objectA", "objectA"), ("double", "double"),
                            ("array", "int"), ("typed", "int"), ("int", "typed"), ("withf", "int")])
        # Stable types, hot enough for a tiering engine to specialise each function.
        for name in names:
            lines += self.loop(f"hot {name}", self.hot, name, stable)
        # Changed types and shapes: what was specialised must be given up.
        kinds = ["int", "big", "double", "string", "objectA", "objectB", "array", "typed", "typedB", "odd", "withf"]
        for name in names:
            changed = (self.pick(kinds), self.pick(kinds))
            lines += self.loop(f"types {name}", self.pick([3, 17, 64]), name, changed)
        # Changed call targets: a call site that saw one function sees others.
        lines.append(f"var table = [{', '.join(self.random.sample(names, len(names)))}];")
        lines += [f"for (var i = 0; i < {self.hot}; i++) {{ __try(table[0], {self.value(stable[0])}, {self.value(stable[1])}); }}",
                  "__phase('target stable');"]
        lines += [f"for (var i = 0; i < 64; i++) {{ __try(table[i % table.length], {self.value(stable[0])}, {self.value(stable[1])}); }}",
                  "__phase('target mixed');"]
        # A throw from a hot function, through any frames between, into a caller's loop.
        victim = self.pick(self.guarded or names)
        lines.append(f"function catcher(n) {{ var t = 0, i = 0; try {{ for (i = 0; i < n; i++) {{ "
                     f"t = __clamp({victim}(i, {self.value(stable[1])})); }} }} catch (e) {{ __mix('late ' + i + ' ' + __err(e)); }} "
                     f"finally {{ __fin = (__fin + 1) | 0; }} return t; }}")
        lines += [f"__at = {self.hot - self.pick([1, 7, 40])}; __mix(catcher({self.hot}));", "__phase('late throw');",
                  f"__at = -1; __mix(catcher({self.hot}));", "__phase('late after');"]
        # Changed objects: prototype, accessor and deleted properties behind the same sites,
        # read by a function that reads x or y where there is one.
        sources = dict(zip(names, lines[1:1 + count]))
        victim = self.pick([name for name in names if re.search(r"\b[ab]\.[xy]\b", sources[name])] or names)
        # `reads` keeps the same property reads hot, so a read that misses the change is seen
        # even when the victim's arithmetic washes the value out.
        lines.append(f"var proto = {{x: 5, y: 6}}; var holder = Object.create(proto); holder.length = 2; holder[0] = 9;")
        lines.append("function reads(a, b) { return [a.x, b.y, a[0], b.length]; }")
        lines += [f"for (var i = 0; i < {self.hot}; i++) {{ __try({victim}, holder, holder); __try(reads, holder, holder); }}",
                  "__phase('proto stable');"]
        lines.append(self.pick([
            "proto.x = 'changed';",
            "Object.defineProperty(proto, 'x', {get: function () { return __sum & 3; }, configurable: true});",
            "delete proto.x;",
            "holder.x = 1.5;",
            "Object.setPrototypeOf(holder, {x: [1], y: null});",
        ]))
        lines += [f"for (var i = 0; i < 32; i++) {{ __try({victim}, holder, holder); __try(reads, holder, holder); }}",
                  "__phase('proto changed');"]
        # Back to the stable types: code that deoptimised must still be right, and may tier up again.
        for name in names[:2]:
            lines += self.loop(f"again {name}", self.hot, name, stable)
        lines += self.longLoops(stable)
        lines.append("__phase('end');")
        return PRELUDE + "\n".join(lines) + "\n"


def classify(returncode: int | None, stderr: str) -> str:
    """The comparable part of how a run ended. Error text differs between engines; its class is kept."""
    if returncode is None:
        return "timeout"
    if returncode < 0:
        return "signal " + signal.Signals(-returncode).name
    if returncode == 0:
        return "ok"
    for word in ("SyntaxError", "ReferenceError", "TypeError", "RangeError", "InternalError", "Error"):
        if word in stderr:
            return "uncaught " + word
    return f"exit {returncode}"


def run(command: list[str], timeout: float) -> tuple[str, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, errors="replace",
                                env={**os.environ, "SILKJS_PREPARSE_THREADS": "0"})
        return classify(result.returncode, result.stderr), result.stdout
    except subprocess.TimeoutExpired as expired:
        output = expired.stdout or b""
        return "timeout", output.decode(errors="replace") if isinstance(output, bytes) else output


def outcomes(configs: dict[str, list[str]], path: Path, timeout: float,
             counters: dict[str, dict[str, int]] | None = None) -> dict[str, tuple[str, str]]:
    """Runs path under each configuration. With counters, each configuration's {stats} file is
    read into counters[name], and counters[name]["programs-compiled"] counts runs with a compiled run."""
    results = {}
    for name, template in configs.items():
        stats = path.with_suffix(f".{name}.stats")
        stats.unlink(missing_ok=True)
        results[name] = run([part.replace("{file}", str(path)).replace("{stats}", str(stats)) for part in template], timeout)
        if counters is not None and any("{stats}" in part for part in template):
            seen: dict[str, int] = {}
            read_stats(stats, seen)
            into = counters.setdefault(name, {})
            for key, value in seen.items():
                into[key] = into.get(key, 0) + value
            if seen.get("runs", 0) > 0:
                into["programs-compiled"] = into.get("programs-compiled", 0) + 1
            if seen.get("deopts", 0) > 0:
                into["programs-deopted"] = into.get("programs-deopted", 0) + 1
    return results


def disagreements(results: dict[str, tuple[str, str]]) -> list[str]:
    names = list(results)
    return [name for name in names[1:] if results[name] != results[names[0]]]


def minimize(source: str, differs, budget: int = 400) -> str:
    """Delta debugging over lines: delete chunks while `differs` still holds."""
    lines = source.splitlines()
    chunk = max(1, len(lines) // 2)
    spent = 0
    while chunk >= 1 and spent < budget:
        index, changed = 0, False
        while index < len(lines) and spent < budget:
            candidate = lines[:index] + lines[index + chunk:]
            spent += 1
            if candidate and differs("\n".join(candidate) + "\n"):
                lines, changed = candidate, True
            else:
                index += chunk
        if not changed:
            chunk //= 2
    return "\n".join(lines) + "\n"


def default_jit() -> Path:
    sys.path.insert(0, str(ROOT / "scripts"))
    import toolchain
    return toolchain.release_binary().parent / "silkjs-jit-shell"


def read_stats(path: Path, into: dict[str, int]) -> None:
    """Adds the `name value` pairs a run wrote to path (one line) into into."""
    try:
        words = [word for word in path.read_text().split() if not word.endswith(":")]
    except OSError:
        return
    for name, value in zip(words[::2], words[1::2]):
        if value.isdigit():
            into[name] = into.get(name, 0) + int(value)


def default_engine() -> Path:
    sys.path.insert(0, str(ROOT / "scripts"))
    import toolchain
    return toolchain.release_binary()


def self_test(engine: Path, timeout: float, programs: int = 40) -> int:
    """The harness must find a planted disagreement in each area and reduce it, and must not invent one."""
    failed = False
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        # A stand-in "engine" that runs the program with one area rewritten.
        broken = work / "broken.py"
        broken.write_text(
            "import re, subprocess, sys\n"
            "pattern, replacement, engine, path = sys.argv[1:5]\n"
            "source = open(path).read()\n"
            "open(path + '.broken.js', 'w').write(re.sub(pattern, replacement, source))\n"
            "result = subprocess.run([engine, path + '.broken.js'], capture_output=True, text=True)\n"
            "sys.stdout.write(result.stdout); sys.stderr.write(result.stderr); sys.exit(result.returncode)\n")
        paths = []
        for seed in range(programs):
            path = work / f"{seed}.js"
            path.write_text(Generator(seed, 50).program())
            paths.append(path)
        plain = {"plain": [str(engine), "{file}"]}
        clean = sum(1 for path in paths if not disagreements(outcomes({**plain, "again": plain["plain"]}, path, timeout)))
        if clean != programs:
            print(f"self-test: FAIL the engine disagreed with itself on {programs - clean} of {programs} programs")
            failed = True
        for area, (pattern, mutation, replacement) in AREAS.items():
            configs = {**plain, "broken": [sys.executable, str(broken), mutation, replacement, str(engine), "{file}"]}
            found = [path for path in paths if disagreements(outcomes(configs, path, timeout))]
            exercising = [path for path in paths if re.search(pattern, path.read_text())]
            if not found or len(found) == programs or not set(found) <= set(exercising):
                print(f"self-test: FAIL {area}: planted bug seen in {len(found)} of {programs} programs, "
                      f"{len(exercising)} exercise the area; expected some, not all, and only those")
                failed = True
                continue

            def differs(text: str) -> bool:
                probe = work / "probe.js"
                probe.write_text(text)
                return bool(disagreements(outcomes(configs, probe, timeout)))

            original = found[0].read_text()
            reduced = minimize(original, differs)
            before, after = len(original.splitlines()), len(reduced.splitlines())
            if not re.search(pattern, reduced) or after >= before / 2:
                print(f"self-test: FAIL {area}: minimizer kept {after} of {before} lines")
                failed = True
                continue
            print(f"self-test: {area}: planted bug found in {len(found)} of {programs} programs "
                  f"({len(exercising)} exercise the area), reduced {before} lines to {after}")
        same = Generator(3, 50).program() == Generator(3, 50).program()
        other = Generator(3, 50).program() != Generator(4, 50).program()
        if not same or not other:
            print("self-test: FAIL generation is not a function of the seed")
            failed = True
    print("self-test: FAIL" if failed else "self-test: PASS")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", help="the SilkJS engine executable (default: $SILKJS_ENGINE, else this host's release build)")
    parser.add_argument("--configs", default="plain,observed", help="comma-separated configurations; the first is the baseline")
    parser.add_argument("--config", action="append", default=[], metavar="NAME=TEMPLATE",
                        help="define a configuration, e.g. jit='{engine} --jit {file}'; repeatable")
    parser.add_argument("--seed", type=int, default=1, help="first seed (default 1)")
    parser.add_argument("--count", type=int, default=200, help="number of programs (default 200)")
    parser.add_argument("--hot", type=int, default=300, help="iterations of each stable loop (default 300)")
    parser.add_argument("--timeout", type=float, default=20.0, help="seconds per run (default 20)")
    parser.add_argument("--out", default=str(ROOT.parents[1] / "build/differential"),
                        help="where failing programs are written (default build/differential)")
    parser.add_argument("--no-minimize", action="store_true", help="keep failing programs as generated")
    parser.add_argument("--show", action="store_true", help="print the generated programs instead of running them")
    parser.add_argument("--self-test", action="store_true", help="check that the harness finds and reduces a planted bug in each area")
    parser.add_argument("--self-test-programs", type=int, default=40, help="programs per self-test area (default 40)")
    args = parser.parse_args()

    if args.show:
        for seed in range(args.seed, args.seed + args.count):
            sys.stdout.write(Generator(seed, args.hot).program())
        return 0

    engine = Path(args.engine or os.environ.get("SILKJS_ENGINE") or default_engine())
    if not engine.exists():
        print(f"differential.py: no engine at {engine}; build it with `silk build --release` or pass --engine", file=sys.stderr)
        return 2
    if args.self_test:
        return self_test(engine, args.timeout, args.self_test_programs)

    templates = dict(BUILTIN)
    for definition in args.config:
        name, _, template = definition.partition("=")
        if not template:
            print(f"differential.py: --config {definition!r} is not NAME=TEMPLATE", file=sys.stderr)
            return 2
        templates[name] = template
        if name not in args.configs.split(","):
            args.configs += "," + name
    node = os.environ.get("NODE_REFERENCE") or "node"
    jit = os.environ.get("SILKJS_JIT") or str(default_jit())
    configs: dict[str, list[str]] = {}
    skipped: dict[str, str] = {}
    for name in args.configs.split(","):
        if name not in templates:
            print(f"differential.py: unknown configuration {name!r}; known: {', '.join(templates)}", file=sys.stderr)
            return 2
        command = [part.replace("{engine}", str(engine)).replace("{node}", node).replace("{jit}", jit) for part in shlex.split(templates[name])]
        if shutil.which(command[0]) is None and not Path(command[0]).exists():
            skipped[name] = f"{command[0]} is not installed"
            continue
        configs[name] = command
    if len(configs) < 2:
        print(f"differential.py: need two runnable configurations; skipped: {skipped}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    baseline = next(iter(configs))
    tally = {"agree": 0, "mismatch": 0, "reference": 0}
    endings: dict[str, int] = {}
    failures = []
    counters: dict[str, dict[str, int]] = {}
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for seed in range(args.seed, args.seed + args.count):
            path = work / f"seed-{seed}.js"
            path.write_text(Generator(seed, args.hot).program())
            results = outcomes(configs, path, args.timeout, counters)
            endings[results[baseline][0]] = endings.get(results[baseline][0], 0) + 1
            wrong = disagreements(results)
            if not wrong:
                tally["agree"] += 1
                continue
            kind = "reference" if all(name in REFERENCES for name in wrong) else "mismatch"
            tally[kind] += 1
            source = path.read_text()
            if not args.no_minimize:
                pair = {baseline: configs[baseline], wrong[0]: configs[wrong[0]]}

                def differs(text: str) -> bool:
                    probe = work / "probe.js"
                    probe.write_text(text)
                    return bool(disagreements(outcomes(pair, probe, args.timeout)))

                source = minimize(source, differs)
            saved = out / f"seed-{seed}.js"
            saved.write_text(source)
            (out / f"seed-{seed}.json").write_text(json.dumps({
                "seed": seed, "hot": args.hot, "kind": kind, "baseline": baseline, "differs": wrong,
                "commands": {name: " ".join(command) for name, command in configs.items()},
                "results": {name: {"ending": ending, "stdout": stdout} for name, (ending, stdout) in results.items()},
            }, indent=2) + "\n")
            failures.append((seed, kind, wrong, saved))
            print(f"seed {seed}: {kind}: {', '.join(wrong)} differ from {baseline}; {saved}")

    print(f"{args.count} programs, seeds {args.seed}..{args.seed + args.count - 1}, hot {args.hot}, configurations: {', '.join(configs)}")
    for name, reason in skipped.items():
        print(f"skipped {name}: {reason}")
    print(f"baseline endings: {', '.join(f'{count} {ending}' for ending, count in sorted(endings.items()))}")
    for name, values in counters.items():
        print(f"counters {name}: " + ", ".join(f"{key} {value}" for key, value in sorted(values.items())))
    print(f"agree {tally['agree']}, mismatch {tally['mismatch']}, reference-only {tally['reference']}")
    return 1 if tally["mismatch"] else 0


if __name__ == "__main__":
    sys.exit(main())
