#!/usr/bin/env python3
"""Week 1 tests. Missing LLVM tools fail smoke/full; --suite isa is local-only."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.backend import TOOLS, LAYOUT, TRIPLE, compile_ir, execute, check_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("isa", "scalar", "backend", "smoke", "full"), default="smoke")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    out = ROOT / "build/logs" / ("test-" + stamp)
    out.mkdir(parents=True)
    print(f"Evidence: {out}", flush=True)
    manifest = {"command": [sys.executable, *sys.argv], "suite": args.suite,
                "timestamp_utc": stamp, "host": platform.platform(), "seed": 583,
                "step_limit": 100000, "passed": [], "failed": [], "unrun": []}
    def record(name, action):
        try:
            detail = action()
            manifest["passed"].append({"name": name, "detail": detail})
            print(f"PASS {name}: {detail}", flush=True)
        except Exception as e:
            manifest["failed"].append({"name": name, "error": str(e)})
            print(f"FAIL {name}: {e}", flush=True)
    def isa():
        suite = unittest.TestLoader().discover(str(ROOT / "tests/isa"))
        with (out / "isa.log").open("w") as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        if not result.wasSuccessful() or not result.testsRun: raise AssertionError("see isa.log; suite must be nonempty")
        return f"{result.testsRun} tests"
    record("ISA", isa)
    def runner():
        suite = unittest.TestLoader().discover(str(ROOT / "tests/runner"))
        with (out / "runner.log").open("w") as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        if not result.wasSuccessful() or not result.testsRun: raise AssertionError("see runner.log; suite must be nonempty")
        return f"{result.testsRun} tests"
    record("wrapper", runner)
    if args.suite != "isa":
        required = ("llc", "llvm-config") if args.suite in ("scalar", "backend") else ("llc", "opt", "clang", "llvm-config", "lc2k-prepare")
        missing = [str(TOOLS / t) for t in required if not (TOOLS / t).is_file()]
        if missing:
            manifest["failed"].append({"name": "pinned tools", "error": "missing: " + ", ".join(missing)})
            manifest["unrun"].append({"name":"backend acceptance", "reason":"required pinned tools missing"})
            print("FAIL pinned tools: build required", flush=True)
        else:
            version = subprocess.run([str(TOOLS / "llc"), "--version"], capture_output=True, text=True)
            manifest["llvm_version"] = version.stdout
            git = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
            manifest["dirty"] = bool(git.stdout)
            revision = subprocess.run(["git", "rev-parse", "HEAD"],cwd=ROOT,capture_output=True,text=True)
            manifest["repository_commit"] = revision.stdout.strip() if not revision.returncode else None
            manifest["toolchain"] = json.loads((ROOT / "configs/toolchain.json").read_text())
            rng = random.Random(583)
            edges = [0, 1, 0xffffffff, 0x7fffffff, 0x80000000, 0xaaaaaaaa, 0x55555555]
            count = 1000 if args.suite == "full" else 100
            vectors = [(x, y, x ^ y) for x in edges for y in edges]
            vectors += [tuple(rng.getrandbits(32) for _ in range(3)) for _ in range(count)]
            manifest["inputs"] = vectors
            specs = [("identity", lambda x,y,z:x), ("add", lambda x,y,z:x+y),
                     ("nor", lambda x,y,z:~(x|y))]
            if args.suite in ("backend", "smoke", "full"):
                specs += [("branch", lambda x,y,z:x+z if x==y else y+z+17),
                          ("branch-ne", lambda x,y,z:~z if x!=y else z+23),
                          ("memory", lambda x,y,z:x+11+33+44+33+91)]
            for name, expected in specs:
                def kernel(name=name, expected=expected):
                    source = ROOT / "tests/backend" / (name + ".ll")
                    manifest.setdefault("source_hashes", {})[str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
                    assembly = compile_ir(source, out / (name + ".as"))
                    for values in vectors:
                        result, program = execute(assembly, values)
                        check_result(result.registers[1], expected(*values))
                        if name == "memory":
                            for symbol, val in (("g0",11),("g1",values[0]),("g2",33),("g3",44),("g4",91)):
                                check_result(result.memory[program.symbols[symbol]], val)
                    return f"{len(vectors)} runtime vectors"
                record(name, kernel)
            def constants():
                for val in edges:
                    signed = val if val < 0x80000000 else val - 0x100000000
                    path = out / f"constant-{val}.ll"
                    path.write_text(TRIPLE + LAYOUT + f"define i32 @kernel() {{ ret i32 {signed} }}\n")
                    assembly = compile_ir(path, path.with_suffix(".as"))
                    result, _ = execute(assembly)
                    check_result(result.registers[1], val)
                return f"{len(edges)} bit-pattern edges"
            record("constants", constants)
            def checker_negative():
                try: check_result(1, 2)
                except AssertionError: return "wrong expected result rejected"
                raise AssertionError("checker accepted wrong output")
            record("output checker negative", checker_negative)
            if args.suite in ("backend", "smoke", "full"):
                def rejections():
                    valid = TRIPLE + LAYOUT + "define i32 @kernel(i32 %x) { ret i32 %x }\n"
                    cases = {
                        "foreign-layout": valid.replace("p:32:32","p:64:64"),
                        "foreign-triple": valid.replace("lc2k-unknown-none","riscv32-unknown-unknown-elf"),
                        "mul": TRIPLE + LAYOUT + "define i32 @kernel(i32 %x) { %r = mul i32 %x, 7\n ret i32 %r }\n",
                        "byte": TRIPLE + LAYOUT + "@b = global i8 7\ndefine i32 @kernel(i32 %x) { ret i32 %x }\n",
                    }
                    records = []
                    for name, source in cases.items():
                        path = out / ("reject-" + name + ".ll")
                        path.write_text(source)
                        command = [str(TOOLS / "llc"), "-march=lc2k",str(path),"-o",str(path.with_suffix(".as"))]
                        result = subprocess.run(command,capture_output=True,text=True)
                        records.append({"command":command,"exit_code":result.returncode,"stderr":result.stderr})
                        if result.returncode == 0 or "LC2K unsupported IR:" not in result.stderr:
                            raise AssertionError(f"{name} was not rejected with an explicit LC2K diagnostic")
                    path = ROOT / "tests/backend/add.ll"
                    command = [str(TOOLS / "llc"),"-march=lc2k","-filetype=obj",str(path),"-o",str(out / "unsupported.o")]
                    result = subprocess.run(command,capture_output=True,text=True)
                    records.append({"command":command,"exit_code":result.returncode,"stderr":result.stderr})
                    if result.returncode == 0: raise AssertionError("object output unexpectedly accepted")
                    (out / "rejections.json").write_text(json.dumps(records,indent=2)+"\n")
                    return "foreign triple/layout, multiply, bytes, and object output rejected"
                record("backend rejection", rejections)
                def pressure():
                    assembly = compile_ir(ROOT / "tests/backend/pressure.ll", out / "pressure.as")
                    spills = assembly.count("# allocator spill")
                    reloads = assembly.count("# allocator reload")
                    if not spills or not reloads:
                        raise AssertionError("pressure case did not demonstrate actual spills and reloads")
                    cases = [(x, [i*17+3 for i in range(64)]) for x in edges]
                    # Random mutable globals are runtime inputs. They prevent
                    # repeated NOR from masking a wrong spill value on all
                    # fixed edge patterns.
                    cases += [(rng.getrandbits(32), [rng.getrandbits(32) for _ in range(64)]) for _ in range(count)]
                    # Sensitize each leaf separately: all sibling subtrees on
                    # its path produce zero, so six NORs preserve that leaf.
                    def uniform_output(size, ones):
                        if size == 1: return [0xffffffff if ones else 0]
                        if ones: return uniform_output(size//2, False) * 2
                        return uniform_output(size//2, True) + uniform_output(size//2, False)
                    def sensitized(size, leaf, value):
                        if size == 1: return [value]
                        half = size//2
                        if leaf < half: return sensitized(half, leaf, value) + uniform_output(half, False)
                        return uniform_output(half, False) + sensitized(half, leaf-half, value)
                    for leaf in range(64):
                        cases.append((0, sensitized(64, leaf, rng.getrandbits(32))))
                    manifest["pressure_inputs"] = [{"x":x,"words":data} for x,data in cases]
                    for x, data in cases:
                        expected = [(v+x) & 0xffffffff for v in data]
                        while len(expected) > 1:
                            expected = [(~(a | b)) & 0xffffffff for a,b in zip(expected[::2], expected[1::2])]
                        result, program = execute(assembly, (x,), global_words={f'g{i}':v for i,v in enumerate(data)})
                        check_result(result.registers[1], expected[0])
                        for i in range(64):
                            check_result(result.memory[program.symbols[f'g{i}']], data[i])
                    mutated = assembly.splitlines()
                    for i, line in enumerate(mutated):
                        fields = line.split()
                        if fields[:2] == ["sw","5"]:
                            fields[2] = "0"
                            mutated[i] = "        " + " ".join(fields)
                            break
                    corrupt = "\n".join(mutated) + "\n"
                    (out / "pressure-wrong-spill.as").write_text(corrupt)
                    for leaf, (_,data) in enumerate(cases[-64:]):
                        bad, _ = execute(corrupt,(0,),global_words={f'g{i}':v for i,v in enumerate(data)})
                        # Six inversions preserve the selected leaf because
                        # every sibling subtree on its path is zero.
                        if bad.registers[1] != data[leaf]:
                            (out / "pressure-wrong-spill.json").write_text(json.dumps({
                                "detected":True,"leaf":leaf,"expected":data[leaf],
                                "actual":bad.registers[1]},indent=2)+"\n")
                            break
                    else: raise AssertionError("pressure harness failed to detect a wrong spill value")
                    compile_ir(ROOT / "tests/backend/pressure.ll", out / "pressure.mir", extra=("-stop-after=greedy",))
                    return f"{spills} static spill stores, {reloads} reloads; {len(cases)} runtime vectors; wrong-spill negative detected; MIR saved"
                record("register pressure", pressure)
                def loop():
                    assembly = compile_ir(ROOT / "tests/backend/loop.ll", out / "loop.as")
                    for n in (0,1,2,7,31):
                        for x in edges:
                            result, _ = execute(assembly, (n,x))
                            check_result(result.registers[1], n*x)
                    return "35 bounded runs, including zero/one/several iterations"
                record("loop", loop)
                def nonterminating():
                    assembly = (out / "loop.as").read_text()
                    try: execute(assembly, (0xffffffff,1), max_steps=100)
                    except AssertionError as e:
                        if "timeout" in str(e): return "backend loop instruction-limit failure detected"
                        raise
                    raise AssertionError("nonterminating case passed unexpectedly")
                record("backend timeout negative", nonterminating)
                def frontend():
                    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests/frontend"))
                    with (out / "frontend.log").open("w") as log:
                        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
                    if not result.wasSuccessful() or not result.testsRun: raise AssertionError("see frontend.log; suite must be nonempty")
                    return f"{result.testsRun} validator tests"
                if args.suite != "backend": record("frontend validator", frontend)
                else: manifest["unrun"].append({"name":"C path", "reason":"focused backend-only suite"})
                c_specs = () if args.suite == "backend" else (("identity",lambda x,y,z:x,1),
                        ("add",lambda x,y,z:x+y,2), ("not",lambda x,y,z:~x,1),
                        ("nor",lambda x,y,z:~(x|y),2), ("globals",lambda x,y,z:x+14,1))
                for name, expected, arity in c_specs:
                    def c_kernel(name=name, expected=expected, arity=arity):
                        destination = out / f"c-{name}.as"
                        command = [sys.executable, str(ROOT / "scripts/compile_c.py"),
                            str(ROOT / f"tests/frontend/{name}.c"), "-o", str(destination)]
                        result = subprocess.run(command, text=True, capture_output=True)
                        (out / f"c-{name}.log").write_text(json.dumps({"command":command,
                            "exit_code":result.returncode,"stdout":result.stdout,"stderr":result.stderr},indent=2))
                        if result.returncode: raise AssertionError(f"C pipeline failed; see c-{name}.log")
                        assembly = destination.read_text()
                        for values in vectors:
                            final, program = execute(assembly, values[:arity])
                            check_result(final.registers[1], expected(*values))
                            if name == "globals":
                                for symbol,val in (("g0",5),("g1",values[0]),("g2",9)):
                                    check_result(final.memory[program.symbols[symbol]],val)
                        return f"{len(vectors)} C runtime vectors"
                    record("C " + name, c_kernel)
    manifest["exit_code"] = int(bool(manifest["failed"]))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{len(manifest['passed'])} groups passed, {len(manifest['failed'])} failed; exit {manifest['exit_code']}")
    return manifest["exit_code"]

if __name__ == "__main__":
    raise SystemExit(main())
